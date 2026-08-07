import json
import logging
from datetime import date

from openai import OpenAI

from config import OPENAI_API_KEY
from services.airtable import (
    create_social_post,
    has_published_today,
    get_next_recipe,
    mark_recipe_distributed,
    upload_image_and_get_url,
)
from services.gnews import get_trend
from services.image_compose import compose_hook_image
from services.image_generate import generate_dish_photo
from services.meta_kelu import (
    publish_to_instagram,
    publish_to_facebook,
    publish_carousel_to_instagram,
    publish_carousel_to_facebook,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres el equipo de contenido de Kelu GmbH, distribuidor B2B de productos "
    "latinos en Suiza (arepas, tequeños, empanadas, yuca, pan de bono y más) "
    "para restaurantes, delicatessen y caterers. El tono es cálido, cercano y "
    "apasionado por la cocina latina. Nunca uses emojis en exceso — máximo 3 "
    "por post. No inventes datos que no conoces.\n\n"
    "Formato del campo 'cuerpo': escribilo como se lee un caption profesional "
    "de Instagram, NUNCA como un solo bloque de texto. Cada punto de la "
    "estructura pedida va en su propio párrafo corto (1-3 oraciones), separado "
    "del siguiente por un salto de línea doble (\\n\\n) dentro del string JSON."
)

_client = None


def _get_openai_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY no está configurada")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def _generar_post(user_prompt: str) -> dict:
    client = _get_openai_client()
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
    )
    raw = completion.choices[0].message.content or ""
    cleaned = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"No se pudo parsear la respuesta de GPT-4o como JSON: {exc}") from exc


def _build_caption(post: dict) -> str:
    hashtags = " ".join(f"#{h}" for h in post.get("hashtags", []))
    # Separador visual generoso antes de los hashtags, como en un caption
    # profesional de IG (evita que queden pegados al último párrafo).
    return f"{post['titulo']}\n\n{post['cuerpo']}\n\n.\n.\n{hashtags}"


def _generate_display_image(description: str, hook_text: str, filename_prefix: str) -> str:
    """
    Genera con IA una foto fiel a `description`, le superpone el gancho del
    post (estilo tarjeta editorial) y sube el resultado para tener una URL
    pública — Meta exige una URL, no acepta bytes directamente. Si falla solo
    el paso de superponer texto, cae de vuelta a la foto generada sin texto.
    """
    photo_bytes = generate_dish_photo(description)
    try:
        final_bytes = compose_hook_image(photo_bytes, hook_text)
    except Exception:  # noqa: BLE001
        logger.exception("Fallo componiendo el texto sobre la imagen, se sube la foto sin texto")
        final_bytes = photo_bytes
    return upload_image_and_get_url(final_bytes, f"{filename_prefix}.jpg", label=hook_text)


def _generate_plain_image(description: str, filename_prefix: str) -> str:
    """Genera con IA una foto fiel a `description`, sin texto superpuesto, y la sube."""
    photo_bytes = generate_dish_photo(description)
    return upload_image_and_get_url(photo_bytes, f"{filename_prefix}.jpg")


# ══════════════════════════════════════════════════════════════════
# weekly_recipe — carrusel semanal, sacado de la tabla Recipes
# ══════════════════════════════════════════════════════════════════

def _build_recipe_caption_prompt(recipe: dict) -> str:
    ingredientes = "\n".join(f"- {i}" for i in recipe["ingredients"])
    pasos = "\n".join(f"- {s['titulo']}" for s in recipe["steps"])
    return f"""Crea el caption de un carrusel de Instagram/Facebook para Kelu. Devuelve SOLO JSON válido.

RECETA: {recipe['title']}
PAÍS/CATEGORÍA: {recipe['category']}
DESCRIPCIÓN: {recipe['description']}

INGREDIENTES:
{ingredientes}

PASOS QUE VAN EN CADA SLIDE (en este orden, las fotos son de apoyo sin texto superpuesto):
{pasos}

Estructura del caption (cada número = un párrafo propio, separado por \n\n):
1. Gancho que despierte el antojo o el recuerdo, invitando a deslizar el carrusel.
2. Breve intro a la receta (1-2 oraciones).
3. Lista de ingredientes, cada uno en su propia línea con un guion ("- ingrediente").
4. Menciona brevemente que el carrusel muestra el paso a paso.
5. Cierre con CTA a Kelu (somos distribuidor B2B — la CTA es para restaurantes/caterers que quieran estos productos, no venta directa al consumidor) y pregunta para comentarios.

JSON exacto:
{{
  "titulo": "Gancho de máximo 60 caracteres",
  "cuerpo": "Caption completo máximo 220 palabras, párrafos separados por \\n\\n como se indicó arriba, incluyendo la lista de ingredientes",
  "hashtags": ["12-15 hashtags en español e inglés sin símbolo, incluir siempre: kelu, kelusuiza, cocinalatina, {recipe['category'].lower().replace(' ', '')}"]
}}

IMPORTANTE: Devuelve SOLO el JSON. Sin markdown."""


def generar_caption_receta(recipe: dict) -> dict:
    return _generar_post(_build_recipe_caption_prompt(recipe))


def publicar_receta_semanal() -> dict:
    recipe = get_next_recipe()
    if not recipe:
        return {"success": False, "error": "No hay recetas cargadas en la tabla Recipes."}

    try:
        post = generar_caption_receta(recipe)
        caption = _build_caption(post)

        cover_desc = (
            f"{recipe['title']}, plato tradicional de la cocina de {recipe['category']}. "
            f"{recipe['description']}"
        )
        image_urls = [_generate_display_image(cover_desc, recipe["title"], "receta_cover")]

        for i, step in enumerate(recipe["steps"]):
            step_desc = (
                f"{step['contenido']} — paso de preparación de {recipe['title']}, "
                f"cocina de {recipe['category']}"
            )
            image_urls.append(_generate_plain_image(step_desc, f"receta_step_{i}"))

        ig_result, ig_error = None, None
        try:
            ig_result = publish_carousel_to_instagram(image_urls, caption)
        except Exception as exc:  # noqa: BLE001
            ig_error = str(exc)
            logger.exception("Fallo publicando carrusel de receta en Instagram")

        fb_result, fb_error = None, None
        try:
            fb_result = publish_carousel_to_facebook(image_urls, caption)
        except Exception as exc:  # noqa: BLE001
            fb_error = str(exc)
            logger.exception("Fallo publicando carrusel de receta en Facebook")

        if ig_result or fb_result:
            mark_recipe_distributed(recipe["id"])
            create_social_post(
                post_type="weekly_recipe",
                topic=recipe["title"],
                caption=caption,
            )

        return {
            "success": bool(ig_result or fb_result),
            "titulo": recipe["title"],
            "instagram": ig_result,
            "facebook": fb_result,
            "ig_error": ig_error,
            "fb_error": fb_error,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo generando/publicando la receta semanal")
        return {"success": False, "titulo": recipe["title"], "error": str(exc)}


# ══════════════════════════════════════════════════════════════════
# midweek_tip_dato — tendencia (GNews o fallback) + dato curioso
# ══════════════════════════════════════════════════════════════════

def _build_tip_dato_prompt(trend: dict) -> str:
    return f"""Crea un post de Instagram/Facebook para Kelu tipo 'dato curioso' inspirado en una tendencia gastronómica actual. Devuelve SOLO JSON válido.

TENDENCIA/TEMA: {trend['tema']}
ÁNGULO: {trend['angulo']}

Estructura del post (cada número = un párrafo propio, separado por \n\n):
1. Gancho tipo '¿Sabías que...?' o que conecte con la tendencia.
2. Desarrollo del dato/tendencia en 2-3 oraciones, con tono cercano y educativo, conectándolo con la cocina latina.
3. Conexión breve con Kelu (distribuidor B2B de productos latinos en Suiza) — sin inventar productos específicos si no aplica.
4. Pregunta para comentarios (en su propio párrafo, sola).

JSON exacto:
{{
  "titulo": "Gancho de máximo 60 caracteres",
  "cuerpo": "Post completo máximo 200 palabras, párrafos separados por \\n\\n como se indicó arriba",
  "hashtags": ["12-15 hashtags en español e inglés sin símbolo, incluir siempre: kelu, kelusuiza, cocinalatina, tendenciasgastronomicas"],
  "descripcion_foto": "Descripción vívida y muy específica en español (1-2 oraciones) de una escena o plato de comida latina relacionado al tema, para que una IA genere la foto"
}}

IMPORTANTE: Devuelve SOLO el JSON. Sin markdown."""


def generar_post_tip_dato(trend: dict) -> dict:
    return _generar_post(_build_tip_dato_prompt(trend))


def publicar_tip_dato(fallback_index: int) -> dict:
    trend = get_trend(fallback_index)
    try:
        post = generar_post_tip_dato(trend)
        caption = _build_caption(post)

        descripcion = post.get("descripcion_foto") or f"{trend['tema']}. {trend['angulo']}"
        image_url = _generate_display_image(descripcion, post["titulo"], "tip_dato")

        ig_result, ig_error = None, None
        try:
            ig_result = publish_to_instagram(image_url, caption)
        except Exception as exc:  # noqa: BLE001
            ig_error = str(exc)
            logger.exception("Fallo publicando tip_dato en Instagram")

        fb_result, fb_error = None, None
        try:
            fb_result = publish_to_facebook(image_url, caption)
        except Exception as exc:  # noqa: BLE001
            fb_error = str(exc)
            logger.exception("Fallo publicando tip_dato en Facebook")

        if ig_result or fb_result:
            create_social_post(
                post_type="midweek_tip_dato",
                topic=trend["tema"],
                caption=caption,
                angulo=trend["angulo"],
                fuente=trend["fuente"],
            )

        return {
            "success": bool(ig_result or fb_result),
            "titulo": trend["tema"],
            "instagram": ig_result,
            "facebook": fb_result,
            "ig_error": ig_error,
            "fb_error": fb_error,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo generando/publicando tip_dato")
        return {"success": False, "titulo": trend["tema"], "error": str(exc)}


# ══════════════════════════════════════════════════════════════════
# midweek_tip_foto — dato curioso de producto/cultura (sin dependencia de noticias)
# ══════════════════════════════════════════════════════════════════

DATOS_CURIOSOS_BASE = [
    {
        "tema": "El origen de la panela",
        "dato": "La panela se produce igual que hace siglos: jugo de caña cocido y solidificado sin refinar, conservando minerales que el azúcar blanca pierde en el proceso industrial",
        "producto": "Panela colombiana",
    },
    {
        "tema": "El ají amarillo no es solo picante",
        "dato": "El ají amarillo peruano aporta más color y aroma frutal que picor real — es la base de sabor de platos icónicos como el ají de gallina o la causa limeña",
        "producto": "Ají amarillo en pasta",
    },
    {
        "tema": "El maíz, regalo de Mesoamérica",
        "dato": "El maíz fue domesticado hace más de 9000 años en Mesoamérica y hoy existen miles de variedades — la arepa colombiana y venezolana usa maíz blanco precocido",
        "producto": "Arepas de maíz blanco",
    },
    {
        "tema": "El frijol negro, proteína ancestral",
        "dato": "El frijol negro se cultiva en América Latina desde hace más de 7000 años y es una de las fuentes de proteína vegetal más completas junto al arroz",
        "producto": "Frijoles negros",
    },
    {
        "tema": "La cocina latina no es una sola cocina",
        "dato": "América Latina tiene más de 20 países con tradiciones culinarias propias — lo que llamamos 'comida latina' es en realidad cientos de cocinas regionales distintas",
        "producto": None,
    },
    {
        "tema": "El viaje de un tequeño hasta Suiza",
        "dato": "Cada lote de tequeños viaja congelado en cadena de frío controlada desde origen hasta el almacén en Suiza, para que lleguen a tu cocina con el mismo sabor de siempre",
        "producto": "Tequeños",
    },
    {
        "tema": "La yuca, raíz de 5000 años",
        "dato": "La yuca fue domesticada en Sudamérica hace más de 5000 años y hoy es la base de platos tan distintos como el pan de bono colombiano y el casabe caribeño",
        "producto": "Yuca frita",
    },
]


def _build_tip_foto_prompt(dato: dict) -> str:
    producto_line = (
        f"PRODUCTO KELU RELACIONADO: {dato['producto']}"
        if dato.get("producto")
        else "PRODUCTO KELU RELACIONADO: ninguno en particular, es un dato cultural general"
    )
    return f"""Crea un post de Instagram/Facebook para Kelu tipo 'dato curioso'. Devuelve SOLO JSON válido.

TEMA: {dato['tema']}
DATO CURIOSO: {dato['dato']}
{producto_line}

Estructura del post (cada número = un párrafo propio, separado por \n\n):
1. Gancho tipo '¿Sabías que...?' o similar, que genere curiosidad.
2. El dato curioso desarrollado en 2-3 oraciones, con tono cercano y educativo.
3. Si hay producto Kelu relacionado, mencionarlo brevemente (Kelu es distribuidor B2B, la mención es para restaurantes/caterers, no venta directa). Si no, cerrar con una reflexión o pregunta.

JSON exacto:
{{
  "titulo": "Gancho de máximo 60 caracteres, tipo pregunta",
  "cuerpo": "Post completo máximo 180 palabras, párrafos separados por \\n\\n como se indicó arriba",
  "hashtags": ["12-15 hashtags en español e inglés sin símbolo, incluir siempre: kelu, kelusuiza, datoscuriosos, cocinalatina, culturalatina"],
  "descripcion_foto": "Descripción vívida y muy específica en español (1-2 oraciones) del producto o escena relacionada al tema, para que una IA genere la foto"
}}

IMPORTANTE: Devuelve SOLO el JSON. Sin markdown."""


def generar_post_tip_foto(dato: dict) -> dict:
    return _generar_post(_build_tip_foto_prompt(dato))


def publicar_tip_foto(fallback_index: int) -> dict:
    dato = DATOS_CURIOSOS_BASE[fallback_index % len(DATOS_CURIOSOS_BASE)]
    try:
        post = generar_post_tip_foto(dato)
        caption = _build_caption(post)

        descripcion = post.get("descripcion_foto") or dato["dato"]
        image_url = _generate_display_image(descripcion, post["titulo"], "tip_foto")

        ig_result, ig_error = None, None
        try:
            ig_result = publish_to_instagram(image_url, caption)
        except Exception as exc:  # noqa: BLE001
            ig_error = str(exc)
            logger.exception("Fallo publicando tip_foto en Instagram")

        fb_result, fb_error = None, None
        try:
            fb_result = publish_to_facebook(image_url, caption)
        except Exception as exc:  # noqa: BLE001
            fb_error = str(exc)
            logger.exception("Fallo publicando tip_foto en Facebook")

        if ig_result or fb_result:
            create_social_post(
                post_type="midweek_tip_foto",
                topic=dato["tema"],
                caption=caption,
            )

        return {
            "success": bool(ig_result or fb_result),
            "titulo": dato["tema"],
            "instagram": ig_result,
            "facebook": fb_result,
            "ig_error": ig_error,
            "fb_error": fb_error,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo generando/publicando tip_foto")
        return {"success": False, "titulo": dato["tema"], "error": str(exc)}


# ══════════════════════════════════════════════════════════════════
# Dispatcher semanal
# ══════════════════════════════════════════════════════════════════
#
# Lunes: receta de la semana (carrusel).
# Martes/Jueves/Sábado: dato + tendencia (GNews o fallback).
# Miércoles/Viernes/Domingo: dato curioso de producto/cultura.

CONTENT_MAP = {
    "weekly_recipe": lambda idx: publicar_receta_semanal(),
    "midweek_tip_dato": publicar_tip_dato,
    "midweek_tip_foto": publicar_tip_foto,
}


def _resolve_content_type_and_index(today: date) -> tuple[str, int]:
    weekday = today.weekday()  # Monday = 0 ... Sunday = 6
    # isocalendar() da la semana ISO (alineada a lunes), así que todos los
    # días de una misma semana comparten el mismo número — a diferencia de
    # toordinal() // 7, que puede cortar la semana en cualquier día.
    iso_year, iso_week, _ = today.isocalendar()
    weeks_elapsed = iso_year * 53 + iso_week

    if weekday == 0:
        return "weekly_recipe", 0
    if weekday in (1, 3, 5):  # martes, jueves, sábado
        occurrence_in_week = {1: 0, 3: 1, 5: 2}[weekday]
        return "midweek_tip_dato", weeks_elapsed * 3 + occurrence_in_week
    occurrence_in_week = {2: 0, 4: 1, 6: 2}[weekday]  # miércoles, viernes, domingo
    return "midweek_tip_foto", weeks_elapsed * 3 + occurrence_in_week


def run_kelu_content() -> dict:
    """Guard diario + rotación del tipo de contenido. Punto de entrada del cron."""
    if has_published_today():
        return {"skipped": True, "reason": "Ya se publicó contenido hoy."}

    tipo, index = _resolve_content_type_and_index(date.today())
    result = CONTENT_MAP[tipo](index)
    return {"content_type": tipo, **result}
