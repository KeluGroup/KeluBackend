import re
from datetime import datetime, timezone
from pyairtable import Api
from config import (
    AIRTABLE_API_KEY,
    AIRTABLE_BASE_ID,
    AIRTABLE_TABLE_NAME,
    AIRTABLE_SOCIALPOSTS_TABLE_NAME,
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


# ── SocialPosts (recetas Kelu en Instagram / Facebook) ────────────
#
# Tabla Airtable "SocialPosts" con columnas:
#   Platform      (single line text)   "kelu_receta_ig" | "kelu_receta_fb"
#   Status        (single line text)   "published" | "failed"
#   Receta        (single line text)   nombre de la receta
#   Caption       (long text)
#   Hashtags      (long text, separados por coma)
#   SourceUrl     (url)                foto usada
#   PlatformId    (single line text)   id del post en IG/FB
#   PlatformUrl   (url)
#   Error         (long text)
#   PublishedAt   (date, con hora)
#   CreatedAt     (date, con hora)     se completa siempre, éxito o fallo

def get_socialposts_table():
    return get_airtable_table(AIRTABLE_SOCIALPOSTS_TABLE_NAME)


def create_social_post(data: dict) -> dict:
    now_iso = datetime.now(timezone.utc).isoformat()
    fields = {
        "Platform":    data.get("platform"),
        "Status":      data.get("status"),
        "Receta":      data.get("receta"),
        "Caption":     data.get("caption"),
        "Hashtags":    ", ".join(data.get("hashtags", []) or []),
        "SourceUrl":   data.get("source_url"),
        "PlatformId":  data.get("platform_id"),
        "PlatformUrl": data.get("platform_url"),
        "Error":       data.get("error"),
        "PublishedAt": data.get("published_at"),
        "CreatedAt":   now_iso,
    }
    # Airtable no acepta valores None en la creación — se limpian
    fields = {k: v for k, v in fields.items() if v is not None}
    record = get_socialposts_table().create(fields)
    return {"id": record.get("id"), "fields": record.get("fields", {})}


def has_published_today(platform: str | None = None) -> bool:
    """Guard diario: ¿ya se publicó exitosamente hoy contenido de Kelu?

    Si se pasa `platform`, chequea esa plataforma puntual. Si no, chequea
    cualquier contenido de Kelu (receta, tendencia, carrusel, dato curioso).
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if platform:
        platform_clause = f"{{Platform}} = '{platform}'"
    else:
        platform_clause = "AND(FIND('kelu_', {Platform}) = 1, FIND('_ig', {Platform}) > 0)"
    formula = (
        f"AND({platform_clause}, "
        f"{{Status}} = 'published', "
        f"IS_SAME({{CreatedAt}}, '{today}', 'day'))"
    )
    records = get_socialposts_table().all(formula=formula, max_records=1)
    return len(records) > 0


def get_used_photo_ids(limit: int = 300) -> set:
    """IDs de fotos de Unsplash ya usadas en posts recientes, para no repetirlas."""
    records = get_socialposts_table().all(
        fields=["SourceUrl"], sort=["-CreatedAt"], max_records=limit
    )
    ids = set()
    for r in records:
        url = r.get("fields", {}).get("SourceUrl")
        if not url:
            continue
        match = re.search(r"photo-([a-zA-Z0-9_-]+)", url)
        if match:
            ids.add(match.group(1))
    return ids