import json
import logging
from datetime import date

from openai import OpenAI

from config import OPENAI_API_KEY
from services.airtable import create_social_post, get_used_photo_ids
from services.meta_kelu import fetch_foto_unsplash, publish_to_instagram, publish_to_facebook

logger = logging.getLogger(__name__)

# ── Catálogo de productos (Kevin lo actualizará con los productos reales) ──
PRODUCTOS = [
    {
        "nombre": "Arepas de maíz blanco",
        "descripcion": "Arepas colombianas tradicionales de maíz blanco precocido",
        "categoria": "grano",
        "pais": "Colombia",
        "disponible": True,
    },
    {
        "nombre": "Ají amarillo en pasta",
        "descripcion": "Pasta de ají amarillo peruano, base de múltiples platos andinos",
        "categoria": "salsa",
        "pais": "Perú",
        "disponible": True,
    },
    {
        "nombre": "Panela colombiana",
        "descripcion": "Bloque de azúcar de caña sin refinar, típico de Colombia",
        "categoria": "especia",
        "pais": "Colombia",
        "disponible": True,
    },
    {
        "nombre": "Frijoles negros",
        "descripcion": "Frijoles negros secos, base de la cocina cubana y venezolana",
        "categoria": "legumbre",
        "pais": "Cuba/Venezuela",
        "disponible": True,
    },
    {
        "nombre": "Choclo gigante peruano",
        "descripcion": "Maíz de grano grande típico de los Andes peruanos",
        "categoria": "grano",
        "pais": "Perú",
        "disponible": True,
    },
]

# ── Rotación de recetas (14 recetas, 2 semanas sin repetir) ──
RECETAS_BASE = [
    {"nombre": "Arepas rellenas de queso y guayaba", "productos": ["Arepas de maíz blanco", "Panela colombiana"], "keywords_foto": ["arepa cheese colombia food", "latin breakfast plate"], "pais": "Colombia", "tiempo": "20 min", "dificultad": "fácil"},
    {"nombre": "Ceviche peruano con ají amarillo", "productos": ["Ají amarillo en pasta"], "keywords_foto": ["ceviche peru dish", "peruvian seafood plate"], "pais": "Perú", "tiempo": "25 min", "dificultad": "media"},
    {"nombre": "Frijoles negros estilo cubano", "productos": ["Frijoles negros"], "keywords_foto": ["black beans cuban food", "latin american stew"], "pais": "Cuba", "tiempo": "45 min", "dificultad": "fácil"},
    {"nombre": "Choclo con queso crema andino", "productos": ["Choclo gigante peruano"], "keywords_foto": ["peruvian corn cheese", "andean corn dish"], "pais": "Perú", "tiempo": "15 min", "dificultad": "fácil"},
    {"nombre": "Sopa de frijoles negros con plátano", "productos": ["Frijoles negros"], "keywords_foto": ["black bean soup plantain", "latin soup bowl"], "pais": "Venezuela", "tiempo": "40 min", "dificultad": "media"},
    {"nombre": "Cancha serrana crocante", "productos": ["Choclo gigante peruano"], "keywords_foto": ["toasted corn peru snack", "cancha serrana"], "pais": "Perú", "tiempo": "15 min", "dificultad": "fácil"},
    {"nombre": "Arepa de choclo dulce", "productos": ["Arepas de maíz blanco", "Choclo gigante peruano"], "keywords_foto": ["sweet corn arepa", "latin corn cake"], "pais": "Colombia", "tiempo": "30 min", "dificultad": "media"},
    {"nombre": "Ají de gallina casero", "productos": ["Ají amarillo en pasta"], "keywords_foto": ["aji de gallina peru", "creamy chicken peruvian dish"], "pais": "Perú", "tiempo": "50 min", "dificultad": "media"},
    {"nombre": "Agua de panela con limón y jengibre", "productos": ["Panela colombiana"], "keywords_foto": ["panela drink colombia", "latin ginger lemon drink"], "pais": "Colombia", "tiempo": "10 min", "dificultad": "fácil"},
    {"nombre": "Frijolada colombiana completa", "productos": ["Frijoles negros", "Panela colombiana"], "keywords_foto": ["colombian beans plate", "frijolada dish"], "pais": "Colombia", "tiempo": "60 min", "dificultad": "difícil"},
    {"nombre": "Arepas de choclo con queso", "productos": ["Arepas de maíz blanco", "Choclo gigante peruano"], "keywords_foto": ["corn arepa cheese", "latin street food corn"], "pais": "Colombia", "tiempo": "25 min", "dificultad": "fácil"},
    {"nombre": "Tiradito de salmón con ají amarillo", "productos": ["Ají amarillo en pasta"], "keywords_foto": ["tiradito salmon peru", "peruvian raw fish dish"], "pais": "Perú", "tiempo": "20 min", "dificultad": "media"},
    {"nombre": "Mazamorra morada", "productos": ["Panela colombiana"], "keywords_foto": ["mazamorra morada peru", "purple corn dessert"], "pais": "Perú", "tiempo": "40 min", "dificultad": "media"},
    {"nombre": "Pabellón criollo vegano", "productos": ["Frijoles negros"], "keywords_foto": ["pabellon criollo venezuela", "latin rice beans plate"], "pais": "Venezuela", "tiempo": "55 min", "dificultad": "difícil"},
]

_client = None


def _get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY no está configurada")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


SYSTEM_PROMPT = (
    "Eres el equipo de contenido de Kelu GmbH, una tienda online que vende "
    "productos de cocina latina en Suiza. El tono es cálido, cercano y apasionado "
    "por la cocina latina. Hablas a latinos en Suiza que extrañan los sabores de casa. "
    "Nunca uses emojis en exceso — máximo 3 por post. No inventas datos nutricionales "
    "ni tiempos que no conoces."
)


def _build_user_prompt(receta: dict) -> str:
    return f"""Crea un post de Instagram/Facebook para Kelu. Devuelve SOLO JSON válido.

RECETA: {receta['nombre']}
PAÍS DE ORIGEN: {receta['pais']}
TIEMPO: {receta['tiempo']}
DIFICULTAD: {receta['dificultad']}
PRODUCTOS KELU QUE USA: {', '.join(receta['productos'])}

Estructura del post:
1. Gancho: Una línea que despierte el recuerdo o el antojo. Ej: 'Las arepas
   de tu abuela, ahora en tu cocina en Zúrich.'
2. Ingredientes principales en lista corta (4-6 items, incluye el producto Kelu)
3. Pasos simplificados (máximo 4 pasos, cada uno en 1 oración)
4. Cierre: Dónde comprar el producto Kelu + CTA a la tienda
5. Pregunta para comentarios: ¿Cómo la preparas tú en casa?

JSON exacto:
{{
  "titulo": "Gancho de máximo 60 caracteres",
  "cuerpo": "Post completo máximo 220 palabras siguiendo la estructura",
  "hashtags": ["15 hashtags en español e inglés sin símbolo, incluir siempre: kelu, kelusuiza, cocinalatina, latinosensuiza, recetaslatinas, el nombre del país"],
  "keywords_foto": ["variante 1 de 3-4 palabras EN INGLÉS del plato terminado", "variante 2 de 3-4 palabras EN INGLÉS, ángulo o encuadre distinto del mismo plato o ingrediente"]
}}

IMPORTANTE: Devuelve SOLO el JSON. Sin markdown."""


def generar_post_receta(receta: dict) -> dict:
    client = _get_openai_client()
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(receta)},
        ],
        temperature=0.8,
    )
    raw = completion.choices[0].message.content or ""
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"No se pudo parsear la respuesta de GPT-4o como JSON: {exc}") from exc


def publicar_receta_kelu(receta: dict | None = None) -> dict:
    """Genera el post, busca foto, publica en IG + FB y guarda el resultado en Airtable."""
    receta = receta or RECETAS_BASE[date.today().day % len(RECETAS_BASE)]

    try:
        post = generar_post_receta(receta)
        caption = (
            f"{post['titulo']}\n\n{post['cuerpo']}\n\n"
            + " ".join(f"#{h}" for h in post.get("hashtags", []))
        )

        avoid_ids = get_used_photo_ids()
        foto = fetch_foto_unsplash(post.get("keywords_foto") or receta["keywords_foto"], avoid_ids)
        if not foto:
            raise RuntimeError("No se encontró foto en Unsplash para esta receta.")
        foto_url = foto["url"]

        ig_result, ig_error = None, None
        try:
            ig_result = publish_to_instagram(foto_url, caption)
        except Exception as exc:  # noqa: BLE001 — queremos capturar cualquier fallo de Meta
            ig_error = str(exc)
            logger.exception("Fallo publicando en Instagram")

        fb_result, fb_error = None, None
        try:
            fb_result = publish_to_facebook(foto_url, caption)
        except Exception as exc:  # noqa: BLE001
            fb_error = str(exc)
            logger.exception("Fallo publicando en Facebook")

        create_social_post({
            "platform": "kelu_receta_ig",
            "status": "published" if ig_result else "failed",
            "receta": receta["nombre"],
            "caption": caption,
            "hashtags": post.get("hashtags", []),
            "source_url": foto_url,
            "platform_id": ig_result["id"] if ig_result else None,
            "platform_url": ig_result["url"] if ig_result else None,
            "error": ig_error,
        })
        create_social_post({
            "platform": "kelu_receta_fb",
            "status": "published" if fb_result else "failed",
            "receta": receta["nombre"],
            "caption": caption,
            "hashtags": post.get("hashtags", []),
            "source_url": foto_url,
            "platform_id": fb_result["id"] if fb_result else None,
            "platform_url": fb_result["url"] if fb_result else None,
            "error": fb_error,
        })

        return {
            "success": bool(ig_result or fb_result),
            "receta": receta["nombre"],
            "instagram": ig_result,
            "facebook": fb_result,
        }

    except Exception as exc:  # noqa: BLE001 — fallo antes de publicar (GPT, foto, etc.)
        logger.exception("Fallo generando/publicando receta Kelu")
        create_social_post({
            "platform": "kelu_receta_ig",
            "status": "failed",
            "receta": receta["nombre"],
            "error": str(exc),
        })
        return {"success": False, "receta": receta["nombre"], "error": str(exc)}
