import json
from datetime import datetime, timezone
from pyairtable import Api
from config import (
    AIRTABLE_API_KEY,
    AIRTABLE_BASE_ID,
    AIRTABLE_TABLE_NAME,
    AIRTABLE_SOCIALPOSTS_TABLE_NAME,
    AIRTABLE_RECIPES_TABLE_NAME,
)


def get_airtable_table(table_name: str = AIRTABLE_TABLE_NAME):
    if not AIRTABLE_API_KEY or not AIRTABLE_BASE_ID or not table_name:
        raise RuntimeError("Airtable configuration is missing")
    return Api(AIRTABLE_API_KEY).table(AIRTABLE_BASE_ID, table_name)


def create_lead(data: dict) -> dict:
    table  = get_airtable_table()
    record = table.create({
        "Name":    data.get("name"),
        "Email":   data.get("email"),
        "Company": data.get("company"),
        "Message": data.get("message"),
        "Service": data.get("service")
    })
    return {"id": record.get("id"), "status": "created", "received": record.get("fields", {})}



def fetch_all_leads() -> list:
    records = get_airtable_table().all()
    leads   = [
        {
            "id":        r["id"],
            "name":      r["fields"].get("Name", ""),
            "email":     r["fields"].get("Email", ""),
            "company":   r["fields"].get("Company", ""),
            "message":   r["fields"].get("Message", ""),
            "status":    r["fields"].get("Status", "Nuevo"),
            "createdAt": r.get("createdTime", ""),
        }
        for r in records
    ]
    return sorted(leads, key=lambda x: x["createdAt"], reverse=True)


def update_lead(record_id: str, status: str) -> None:
    get_airtable_table().update(record_id, {"Status": status})


# ── SocialPosts (automatización de contenido v2) ──────────────────
#
# Tabla Airtable "SocialPosts" con columnas:
#   PostType   (single line text)  "weekly_recipe" | "midweek_tip_dato" | "midweek_tip_foto"
#   Topic      (single line text)  tema/título del post
#   Caption    (long text)
#   Angulo     (single line text)  ángulo de tendencia usado, si hubo
#   Fuente     (single line text)  "gnews" | "fallback"
#
# Solo se crea un registro cuando la publicación fue exitosa — esta tabla
# es el registro de lo publicado, no un log de intentos.

def get_socialposts_table():
    return get_airtable_table(AIRTABLE_SOCIALPOSTS_TABLE_NAME)


def create_social_post(post_type: str, topic: str, caption: str,
                        angulo: str = "", fuente: str = "") -> dict:
    fields = {
        "PostType": post_type,
        "Topic":    topic,
        "Caption":  caption,
        "Angulo":   angulo,
        "Fuente":   fuente,
    }
    fields = {k: v for k, v in fields.items() if v}
    record = get_socialposts_table().create(fields)
    return {"id": record.get("id"), "fields": record.get("fields", {})}


def has_published_today() -> bool:
    """Guard diario: ¿ya se publicó exitosamente algo hoy?"""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    formula = f"IS_SAME(CREATED_TIME(), '{today}', 'day')"
    records = get_socialposts_table().all(formula=formula, max_records=1)
    return len(records) > 0


# ── Recipes (recetas semanales, fuente de la tabla de carruseles) ────
#
# Tabla Airtable "Recipes" con columnas:
#   Category         (single line text)  país/categoría, rota semanalmente
#   Title            (single line text)
#   Description      (long text)
#   IngredientsJson  (long text)  JSON: lista de strings
#   StepsJson        (long text)  JSON: lista de {titulo, contenido}
#   Distributed      (checkbox)   si ya se publicó el carrusel correspondiente

def get_recipes_table():
    return get_airtable_table(AIRTABLE_RECIPES_TABLE_NAME)


def get_next_recipe() -> dict | None:
    """
    Próxima receta no distribuida (se respeta el orden de creación, que define
    la rotación semanal de categorías). Si ya se distribuyeron todas, recicla
    el pool completo en vez de quedarse sin contenido.
    """
    table = get_recipes_table()
    pending = table.all(formula="NOT({Distributed})")
    if not pending:
        all_records = table.all()
        if not all_records:
            return None
        for r in all_records:
            table.update(r["id"], {"Distributed": False})
        pending = all_records

    record = pending[0]
    fields = record.get("fields", {})
    return {
        "id": record["id"],
        "category": fields.get("Category", ""),
        "title": fields.get("Title", ""),
        "description": fields.get("Description", ""),
        "ingredients": json.loads(fields.get("IngredientsJson") or "[]"),
        "steps": json.loads(fields.get("StepsJson") or "[]"),
    }


def mark_recipe_distributed(record_id: str) -> None:
    get_recipes_table().update(record_id, {"Distributed": True})


# ── ImageHost (alojamiento temporal de imágenes compuestas) ──────────
#
# Instagram/Facebook exigen una URL pública para publicar. Las imágenes con
# texto superpuesto se generan on-the-fly (no tienen URL propia), así que se
# suben como attachment a esta tabla y se usa la URL que devuelve Airtable.

def upload_image_and_get_url(image_bytes: bytes, filename: str, label: str = "") -> str:
    table = get_airtable_table("ImageHost")
    record = table.create({"Name": label or filename})
    result = table.upload_attachment(
        record["id"], "Image", filename, content=image_bytes, content_type="image/jpeg"
    )
    attachments = result.get("fields", {}).get("Image", [])
    if not attachments:
        raise RuntimeError("No se pudo subir la imagen a Airtable (ImageHost)")
    return attachments[-1]["url"]