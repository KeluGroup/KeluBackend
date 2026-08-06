import logging

import requests

from config import GNEWS_API_KEY

logger = logging.getLogger(__name__)

GNEWS_URL = "https://gnews.io/api/v4/search"

# ── Fallback curado (se usa si GNEWS_API_KEY no está configurada o la API falla) ──
FALLBACK_TRENDS = [
    {"tema": "Fermentados: el regreso de las técnicas ancestrales", "angulo": "La fermentación tradicional latina conecta con la ola mundial de alimentos fermentados"},
    {"tema": "Comfort food con raíces latinas", "angulo": "La comida reconfortante de casa está de moda en toda Europa"},
    {"tema": "Fusión latina-europea en auge", "angulo": "Chefs europeos incorporan ingredientes latinos en platos tradicionales suizos"},
    {"tema": "El boom de los platos crudos y frescos", "angulo": "Ceviches y tiraditos ganan espacio como alternativa fresca y ligera"},
    {"tema": "Snacks saludables con identidad latina", "angulo": "Cancha y choclo tostado como alternativa a los snacks industriales"},
    {"tema": "Superalimentos que ya usaba tu abuela", "angulo": "Maíz morado y frijol negro, hoy vendidos como 'superfood' pero cocina ancestral"},
    {"tema": "Cocinar con cero desperdicio", "angulo": "Técnicas latinas ancestrales alineadas con la tendencia zero-waste"},
    {"tema": "El picante conquista Europa", "angulo": "Crece el interés europeo por especias y ajíes picantes"},
]


def _fetch_from_gnews(query: str) -> dict | None:
    if not GNEWS_API_KEY:
        return None
    try:
        resp = requests.get(
            GNEWS_URL,
            params={"q": query, "lang": "es", "max": 5, "token": GNEWS_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        articles = resp.json().get("articles", [])
        if not articles:
            return None
        article = articles[0]
        titulo = (article.get("title") or "").strip()
        descripcion = (article.get("description") or titulo).strip()
        if not titulo:
            return None
        return {"tema": titulo[:120], "angulo": descripcion, "fuente": "gnews"}
    except Exception:  # noqa: BLE001 — cualquier fallo de red/API cae al fallback
        logger.exception("Fallo consultando GNews, se usa el fallback curado")
        return None


def get_trend(fallback_index: int, query: str = "cocina latina OR gastronomía latina OR tendencias gastronomicas") -> dict:
    """
    Devuelve {"tema", "angulo", "fuente"} — intenta GNews primero (tendencia real),
    y si no hay API key configurada o la consulta falla, usa el listado curado
    rotando por `fallback_index`.
    """
    trend = _fetch_from_gnews(query)
    if trend:
        return trend

    fallback = FALLBACK_TRENDS[fallback_index % len(FALLBACK_TRENDS)]
    return {"tema": fallback["tema"], "angulo": fallback["angulo"], "fuente": "fallback"}
