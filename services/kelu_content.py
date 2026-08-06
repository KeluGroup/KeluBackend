import json
import logging
from datetime import date

from openai import OpenAI

from config import OPENAI_API_KEY
from services.airtable import create_social_post, has_published_today, get_used_photo_ids
from services.meta_kelu import (
    fetch_foto_unsplash,
    publish_to_instagram,
    publish_to_facebook,
    publish_carousel_to_instagram,
    publish_carousel_to_facebook,
)
from services.receta_kelu import RECETAS_BASE, publicar_receta_kelu

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Eres el equipo de contenido de Kelu GmbH, una tienda online que vende "
    "productos de cocina latina en Suiza. El tono es cálido, cercano y apasionado "
    "por la cocina latina. Hablas a latinos en Suiza que extrañan los sabores de casa. "
    "Nunca uses emojis en exceso — máximo 3 por post. No inventas datos que no conoces."
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


def _publicar_single_photo(platform_prefix: str, item_nombre: str, post: dict, keywords_foto_fallback: list[str]) -> dict:
    """Publica un post de una sola foto (usado por tendencia y dato curioso)."""
    caption = (
        f"{post['titulo']}\n\n{post['cuerpo']}\n\n"
        + " ".join(f"#{h}" for h in post.get("hashtags", []))
    )

    avoid_ids = get_used_photo_ids()
    foto = fetch_foto_unsplash(post.get("keywords_foto") or keywords_foto_fallback, avoid_ids)
    if not foto:
        raise RuntimeError("No se encontró foto en Unsplash para este contenido.")
    foto_url = foto["url"]

    ig_result, ig_error = None, None
    try:
        ig_result = publish_to_instagram(foto_url, caption)
    except Exception as exc:  # noqa: BLE001
        ig_error = str(exc)
        logger.exception("Fallo publicando en Instagram (%s)", platform_prefix)

    fb_result, fb_error = None, None
    try:
        fb_result = publish_to_facebook(foto_url, caption)
    except Exception as exc:  # noqa: BLE001
        fb_error = str(exc)
        logger.exception("Fallo publicando en Facebook (%s)", platform_prefix)

    create_social_post({
        "platform": f"kelu_{platform_prefix}_ig",
        "status": "published" if ig_result else "failed",
        "receta": item_nombre,
        "caption": caption,
        "hashtags": post.get("hashtags", []),
        "source_url": foto_url,
        "platform_id": ig_result["id"] if ig_result else None,
        "platform_url": ig_result["url"] if ig_result else None,
        "error": ig_error,
    })
    create_social_post({
        "platform": f"kelu_{platform_prefix}_fb",
        "status": "published" if fb_result else "failed",
        "receta": item_nombre,
        "caption": caption,
        "hashtags": post.get("hashtags", []),
        "source_url": foto_url,
        "platform_id": fb_result["id"] if fb_result else None,
        "platform_url": fb_result["url"] if fb_result else None,
        "error": fb_error,
    })

    return {
        "success": bool(ig_result or fb_result),
        "titulo": item_nombre,
        "instagram": ig_result,
        "facebook": fb_result,
    }


# ── Rastreo de tendencias ──────────────────────────────────────────
TENDENCIAS_BASE = [
    {
        "tema": "Fermentados: el regreso de las técnicas ancestrales",
        "angulo": "Cómo la fermentación tradicional latina conecta con la tendencia mundial de alimentos fermentados",
        "keywords_foto": ["fermented food jar latin", "traditional fermentation kitchen"],
    },
    {
        "tema": "Comfort food con raíces latinas",
        "angulo": "Por qué la comida reconfortante de casa está de moda en toda Europa y cómo los sabores latinos encajan ahí",
        "keywords_foto": ["comfort food latin bowl", "warm homemade latin meal"],
    },
    {
        "tema": "Fusión latina-europea en auge",
        "angulo": "Chefs europeos incorporando ingredientes latinos como el ají amarillo o la panela en platos tradicionales suizos",
        "keywords_foto": ["fusion cuisine latin plate", "modern latin european dish"],
    },
    {
        "tema": "El boom de los platos crudos y frescos",
        "angulo": "Ceviches y tiraditos ganando espacio en restaurantes europeos como alternativa fresca y ligera",
        "keywords_foto": ["ceviche fresh dish", "peruvian raw fish plate"],
    },
    {
        "tema": "Snacks saludables con identidad latina",
        "angulo": "Cancha, choclo tostado y otras alternativas latinas a los snacks industriales",
        "keywords_foto": ["healthy latin snack bowl", "roasted corn snack peru"],
    },
    {
        "tema": "Superalimentos que ya usaba tu abuela",
        "angulo": "Ingredientes como el maíz morado o el frijol negro que hoy se venden como 'superfood' pero son cocina ancestral",
        "keywords_foto": ["purple corn superfood", "black beans healthy latin"],
    },
    {
        "tema": "Cocinar con cero desperdicio",
        "angulo": "Técnicas latinas tradicionales para aprovechar cada parte del ingrediente, alineadas con la tendencia zero-waste",
        "keywords_foto": ["zero waste kitchen food", "sustainable cooking latin"],
    },
    {
        "tema": "El picante conquista Europa",
        "angulo": "El creciente interés europeo por especias y ajíes picantes, y el rol del ají amarillo peruano en esa ola",
        "keywords_foto": ["spicy chili pepper latin", "hot sauce ingredients peru"],
    },
]


def _build_tendencia_prompt(tendencia: dict) -> str:
    return f"""Crea un post de Instagram/Facebook para Kelu sobre una tendencia gastronómica. Devuelve SOLO JSON válido.

TEMA DE TENDENCIA: {tendencia['tema']}
ÁNGULO: {tendencia['angulo']}

Estructura del post:
1. Gancho: Una línea que enganche con la tendencia, conectándola con la cocina latina.
2. Desarrollo breve (2-3 oraciones) explicando la tendencia y por qué le importa a la comunidad latina en Suiza.
3. Conexión con Kelu: cómo nuestros productos encajan en esta tendencia (sin inventar productos específicos si no aplica, hablar en general de productos latinos).
4. Pregunta para comentarios.

JSON exacto:
{{
  "titulo": "Gancho de máximo 60 caracteres",
  "cuerpo": "Post completo máximo 200 palabras siguiendo la estructura",
  "hashtags": ["12-15 hashtags en español e inglés sin símbolo, incluir siempre: kelu, kelusuiza, cocinalatina, latinosensuiza, tendenciasgastronomicas"],
  "keywords_foto": ["variante 1 de 3-4 palabras EN INGLÉS relacionada al tema", "variante 2 de 3-4 palabras EN INGLÉS, ángulo distinto del mismo tema"]
}}

IMPORTANTE: Devuelve SOLO el JSON. Sin markdown."""


def generar_post_tendencia(tendencia: dict) -> dict:
    return _generar_post(_build_tendencia_prompt(tendencia))


def publicar_tendencia_kelu(tendencia: dict | None = None) -> dict:
    tendencia = tendencia or TENDENCIAS_BASE[date.today().day % len(TENDENCIAS_BASE)]
    try:
        post = generar_post_tendencia(tendencia)
        return _publicar_single_photo("tendencia", tendencia["tema"], post, tendencia["keywords_foto"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo generando/publicando tendencia Kelu")
        create_social_post({"platform": "kelu_tendencia_ig", "status": "failed", "receta": tendencia["tema"], "error": str(exc)})
        return {"success": False, "titulo": tendencia["tema"], "error": str(exc)}


# ── Dato curioso ────────────────────────────────────────────────────
DATOS_CURIOSOS_BASE = [
    {
        "tema": "El origen de la panela",
        "dato": "La panela se produce igual que hace siglos: jugo de caña cocido y solidificado sin refinar, conservando minerales que el azúcar blanca pierde en el proceso industrial",
        "producto": "Panela colombiana",
        "keywords_foto": ["sugar cane panela block", "raw cane sugar colombia"],
    },
    {
        "tema": "El ají amarillo no es solo picante",
        "dato": "El ají amarillo peruano aporta más color y aroma frutal que picor real — es la base de sabor de platos icónicos como el ají de gallina o la causa limeña",
        "producto": "Ají amarillo en pasta",
        "keywords_foto": ["yellow chili pepper peru", "aji amarillo paste"],
    },
    {
        "tema": "El maíz, regalo de Mesoamérica",
        "dato": "El maíz fue domesticado hace más de 9000 años en Mesoamérica y hoy existen miles de variedades — la arepa colombiana usa maíz blanco precocido, distinto al choclo gigante andino",
        "producto": "Arepas de maíz blanco",
        "keywords_foto": ["corn field latin america", "white corn maize variety"],
    },
    {
        "tema": "El frijol negro, proteína ancestral",
        "dato": "El frijol negro se cultiva en América Latina desde hace más de 7000 años y es una de las fuentes de proteína vegetal más completas junto al arroz",
        "producto": "Frijoles negros",
        "keywords_foto": ["black beans dried bowl", "latin legumes pantry"],
    },
    {
        "tema": "El choclo gigante del Cusco",
        "dato": "El choclo gigante peruano crece exclusivamente en el Valle Sagrado de Cusco gracias a su altitud y suelo únicos — sus granos pueden ser hasta 3 veces más grandes que el maíz común",
        "producto": "Choclo gigante peruano",
        "keywords_foto": ["giant corn peru cusco", "andean corn field"],
    },
    {
        "tema": "La cocina latina no es una sola cocina",
        "dato": "América Latina tiene más de 20 países con tradiciones culinarias propias — lo que llamamos 'comida latina' es en realidad cientos de cocinas regionales distintas",
        "producto": None,
        "keywords_foto": ["latin american food variety", "diverse latin dishes table"],
    },
    {
        "tema": "La caña de azúcar y su viaje a América",
        "dato": "La caña de azúcar llegó a América con los colonizadores en el siglo XVI, pero fueron las técnicas indígenas y afrodescendientes las que crearon la panela como la conocemos hoy",
        "producto": "Panela colombiana",
        "keywords_foto": ["sugar cane field harvest", "cane sugar traditional process"],
    },
]


def _build_dato_curioso_prompt(dato: dict) -> str:
    producto_line = (
        f"PRODUCTO KELU RELACIONADO: {dato['producto']}"
        if dato.get("producto")
        else "PRODUCTO KELU RELACIONADO: ninguno en particular, es un dato cultural general"
    )
    return f"""Crea un post de Instagram/Facebook para Kelu tipo 'dato curioso'. Devuelve SOLO JSON válido.

TEMA: {dato['tema']}
DATO CURIOSO: {dato['dato']}
{producto_line}

Estructura del post:
1. Gancho tipo '¿Sabías que...?' o similar, que genere curiosidad.
2. El dato curioso desarrollado en 2-3 oraciones, con tono cercano y educativo.
3. Si hay producto Kelu relacionado, mencionarlo brevemente con CTA suave a la tienda. Si no, cerrar con una reflexión o pregunta.

JSON exacto:
{{
  "titulo": "Gancho de máximo 60 caracteres, tipo pregunta",
  "cuerpo": "Post completo máximo 180 palabras siguiendo la estructura",
  "hashtags": ["12-15 hashtags en español e inglés sin símbolo, incluir siempre: kelu, kelusuiza, datoscuriosos, cocinalatina, culturalatina"],
  "keywords_foto": ["variante 1 de 3-4 palabras EN INGLÉS relacionada al tema", "variante 2 de 3-4 palabras EN INGLÉS, ángulo distinto del mismo tema"]
}}

IMPORTANTE: Devuelve SOLO el JSON. Sin markdown."""


def generar_post_dato_curioso(dato: dict) -> dict:
    return _generar_post(_build_dato_curioso_prompt(dato))


def publicar_dato_curioso_kelu(dato: dict | None = None) -> dict:
    dato = dato or DATOS_CURIOSOS_BASE[date.today().day % len(DATOS_CURIOSOS_BASE)]
    try:
        post = generar_post_dato_curioso(dato)
        return _publicar_single_photo("datocurioso", dato["tema"], post, dato["keywords_foto"])
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo generando/publicando dato curioso Kelu")
        create_social_post({"platform": "kelu_datocurioso_ig", "status": "failed", "receta": dato["tema"], "error": str(exc)})
        return {"success": False, "titulo": dato["tema"], "error": str(exc)}


# ── Carrusel de logística / distribución ─────────────────────────────
CARRUSELES_BASE = [
    {
        "tema": "De la finca a tu cocina en Suiza",
        "slides": [
            {"tip": "Todo empieza en origen: seleccionamos productores en Colombia, Perú, Cuba y Venezuela", "keywords_foto": ["latin american farm harvest", "tropical crop harvest"]},
            {"tip": "Empaque cuidadoso para proteger el sabor y la frescura durante el viaje", "keywords_foto": ["food packaging warehouse", "export food boxes"]},
            {"tip": "Transporte internacional controlado, cumpliendo normas suizas de importación", "keywords_foto": ["cargo shipping containers food", "international food import"]},
            {"tip": "Control de calidad antes de llegar a nuestro almacén en Suiza", "keywords_foto": ["quality control food warehouse", "food inspection process"]},
            {"tip": "Y de ahí, directo a tu puerta — sabor de casa sin fronteras", "keywords_foto": ["food delivery doorstep", "package delivery home"]},
        ],
    },
    {
        "tema": "Cómo conservar tus productos latinos por más tiempo",
        "slides": [
            {"tip": "La panela: guárdala en un lugar seco y sellada, aguanta meses sin perder sabor", "keywords_foto": ["sugar block storage pantry", "panela wrapped kitchen"]},
            {"tip": "El ají amarillo en pasta: una vez abierto, en la heladera y bien tapado", "keywords_foto": ["chili paste jar fridge", "condiment jar kitchen"]},
            {"tip": "Los frijoles secos: en un frasco hermético, lejos de la humedad", "keywords_foto": ["dried beans jar pantry", "legumes glass jar"]},
            {"tip": "Las arepas: se congelan perfecto, listas para tostar cuando quieras", "keywords_foto": ["frozen food storage kitchen", "corn cakes freezer"]},
        ],
    },
    {
        "tema": "Por qué importar comida latina a Suiza no es tan simple",
        "slides": [
            {"tip": "Cada producto necesita certificaciones sanitarias específicas para entrar a Suiza", "keywords_foto": ["food certification documents", "import paperwork food"]},
            {"tip": "Los tiempos de envío pueden variar entre 3 y 6 semanas según el producto y el origen", "keywords_foto": ["food shipping logistics", "cargo transport timeline"]},
            {"tip": "Trabajamos con productores pequeños, lo que significa lotes más cuidados pero más lentos", "keywords_foto": ["small farm producer latin america", "artisan food producer"]},
            {"tip": "Cada lote pasa control de calidad doble: en origen y al llegar a Suiza", "keywords_foto": ["quality inspection food", "food batch testing"]},
        ],
    },
    {
        "tema": "El viaje de un grano de choclo gigante",
        "slides": [
            {"tip": "Cosechado a mano en el Valle Sagrado de Cusco, a más de 2800 metros de altura", "keywords_foto": ["cusco valley farming", "andean highland agriculture"]},
            {"tip": "Secado y seleccionado grano por grano para asegurar el tamaño característico", "keywords_foto": ["corn selection process", "grain sorting food"]},
            {"tip": "Empacado al vacío para mantener frescura durante el transporte", "keywords_foto": ["vacuum sealed food package", "food preservation packaging"]},
            {"tip": "Más de 10.000 km después, llega a tu mesa en Suiza", "keywords_foto": ["world map food shipping", "global food trade route"]},
        ],
    },
]


def _build_carrusel_prompt(carrusel: dict) -> str:
    tips_list = "\n".join(f"- {slide['tip']}" for slide in carrusel["slides"])
    return f"""Crea el caption de un carrusel de Instagram/Facebook para Kelu. Devuelve SOLO JSON válido.

TEMA DEL CARRUSEL: {carrusel['tema']}
TIPS QUE VAN EN CADA SLIDE (en este orden, las fotos son de apoyo sin texto superpuesto):
{tips_list}

Estructura del caption:
1. Gancho que invite a deslizar el carrusel ('desliza para ver...' o similar).
2. Breve introducción al tema (1-2 oraciones).
3. Lista numerada con los tips, reescritos con el tono cercano de Kelu pero manteniendo la idea de cada uno, en el mismo orden que las fotos (el lector necesita leer el tip acá porque la foto no tiene texto).
4. Cierre con CTA a la tienda y pregunta para comentarios.

JSON exacto:
{{
  "titulo": "Gancho de máximo 60 caracteres",
  "cuerpo": "Caption completo máximo 220 palabras siguiendo la estructura, incluyendo la lista numerada de tips",
  "hashtags": ["12-15 hashtags en español e inglés sin símbolo, incluir siempre: kelu, kelusuiza, logistica, cocinalatina, detrasdeescena"]
}}

IMPORTANTE: Devuelve SOLO el JSON. Sin markdown."""


def generar_post_carrusel(carrusel: dict) -> dict:
    return _generar_post(_build_carrusel_prompt(carrusel))


def publicar_carrusel_kelu(carrusel: dict | None = None) -> dict:
    carrusel = carrusel or CARRUSELES_BASE[date.today().day % len(CARRUSELES_BASE)]
    try:
        post = generar_post_carrusel(carrusel)
        caption = (
            f"{post['titulo']}\n\n{post['cuerpo']}\n\n"
            + " ".join(f"#{h}" for h in post.get("hashtags", []))
        )

        avoid_ids = get_used_photo_ids()
        image_urls = []
        for slide in carrusel["slides"]:
            foto = fetch_foto_unsplash(slide["keywords_foto"], avoid_ids)
            if foto:
                image_urls.append(foto["url"])
                avoid_ids.add(foto["id"])  # no repetir dentro del mismo carrusel tampoco

        if len(image_urls) < 2:
            raise RuntimeError("No se encontraron suficientes fotos para el carrusel (mínimo 2)")

        ig_result, ig_error = None, None
        try:
            ig_result = publish_carousel_to_instagram(image_urls, caption)
        except Exception as exc:  # noqa: BLE001
            ig_error = str(exc)
            logger.exception("Fallo publicando carrusel en Instagram")

        fb_result, fb_error = None, None
        try:
            fb_result = publish_carousel_to_facebook(image_urls, caption)
        except Exception as exc:  # noqa: BLE001
            fb_error = str(exc)
            logger.exception("Fallo publicando carrusel en Facebook")

        create_social_post({
            "platform": "kelu_carrusel_ig",
            "status": "published" if ig_result else "failed",
            "receta": carrusel["tema"],
            "caption": caption,
            "hashtags": post.get("hashtags", []),
            "source_url": image_urls[0] if image_urls else None,
            "platform_id": ig_result["id"] if ig_result else None,
            "platform_url": ig_result["url"] if ig_result else None,
            "error": ig_error,
        })
        create_social_post({
            "platform": "kelu_carrusel_fb",
            "status": "published" if fb_result else "failed",
            "receta": carrusel["tema"],
            "caption": caption,
            "hashtags": post.get("hashtags", []),
            "source_url": image_urls[0] if image_urls else None,
            "platform_id": fb_result["id"] if fb_result else None,
            "platform_url": fb_result["url"] if fb_result else None,
            "error": fb_error,
        })

        return {
            "success": bool(ig_result or fb_result),
            "titulo": carrusel["tema"],
            "instagram": ig_result,
            "facebook": fb_result,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fallo generando/publicando carrusel Kelu")
        create_social_post({"platform": "kelu_carrusel_ig", "status": "failed", "receta": carrusel["tema"], "error": str(exc)})
        return {"success": False, "titulo": carrusel["tema"], "error": str(exc)}


# ── Dispatcher semanal ────────────────────────────────────────────
CONTENT_CYCLE = ["receta", "tendencia", "carrusel", "dato_curioso"]

CONTENT_MAP = {
    "receta": (publicar_receta_kelu, RECETAS_BASE),
    "tendencia": (publicar_tendencia_kelu, TENDENCIAS_BASE),
    "carrusel": (publicar_carrusel_kelu, CARRUSELES_BASE),
    "dato_curioso": (publicar_dato_curioso_kelu, DATOS_CURIOSOS_BASE),
}


def run_kelu_content() -> dict:
    """Guard diario + rotación del tipo de contenido. Punto de entrada del cron."""
    if has_published_today():
        return {"skipped": True, "reason": "Ya se publicó contenido hoy."}

    day_of_year = date.today().timetuple().tm_yday
    cycle_len = len(CONTENT_CYCLE)
    tipo = CONTENT_CYCLE[day_of_year % cycle_len]
    # Cuántas veces salió este tipo hasta hoy (0, 1, 2, ...) — así cada tipo
    # rota por su propia lista de contenidos en vez de repetir siempre el mismo.
    ocurrencia = day_of_year // cycle_len
    publicar_fn, items = CONTENT_MAP[tipo]
    item = items[ocurrencia % len(items)]

    result = publicar_fn(item)
    return {"content_type": tipo, **result}
