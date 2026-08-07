import base64
import logging
import re
import time

from openai import OpenAI, RateLimitError

from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

MAX_RETRIES = 5
DEFAULT_RETRY_SECONDS = 15.0
_RETRY_HINT_RE = re.compile(r"try again in ([\d.]+)s")


def _retry_wait_seconds(message: str, attempt: int) -> float:
    m = _RETRY_HINT_RE.search(message)
    if m:
        return float(m.group(1)) + 1.0
    return DEFAULT_RETRY_SECONDS * (attempt + 1)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY no está configurada")
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


# Guía de estilo aplicada a toda foto generada, para que el feed se vea
# cohesivo — una identidad visual latina cálida y profesional, no un
# batiburrillo de estilos sueltos entre posts.
STYLE_GUIDE = (
    "Fotografía gastronómica profesional, estilo editorial de revista de cocina "
    "latinoamericana de alta gama. Iluminación cálida y natural. Paleta de tonos "
    "tierra: terracota, mostaza, verde oliva. Props auténticos: tablas de madera "
    "rústica, textiles tejidos coloridos, cerámica artesanal, hojas verdes tropicales "
    "desenfocadas de fondo. Composición cercana y apetitosa, alta definición, poca "
    "profundidad de campo. Sin texto, sin logos, sin marcas de agua, sin manos ni "
    "personas en cuadro."
)


def generate_dish_photo(description: str) -> bytes:
    """
    Genera con IA una foto fotorrealista y fiel a `description`, con la
    identidad visual consistente de Kelu — evita el problema de bancos de
    fotos genéricos (Unsplash) sin cobertura real de platos latinos específicos.

    La cuenta tiene un límite bajo de gpt-image-1 (5 img/min), y un carrusel
    de receta genera 8 fotos en paralelo — reintenta con backoff ante 429
    en vez de fallar la publicación entera por una foto.
    """
    client = _get_client()
    prompt = f"{description}\n\n{STYLE_GUIDE}"
    for attempt in range(MAX_RETRIES):
        try:
            result = client.images.generate(
                model="gpt-image-1",
                prompt=prompt,
                size="1024x1024",
                quality="medium",
                n=1,
            )
            b64 = result.data[0].b64_json
            return base64.b64decode(b64)
        except RateLimitError as exc:
            if attempt == MAX_RETRIES - 1:
                raise
            wait = _retry_wait_seconds(str(exc), attempt)
            logger.warning(
                "Rate limit de gpt-image-1, reintentando en %.1fs (intento %s/%s)",
                wait, attempt + 1, MAX_RETRIES,
            )
            time.sleep(wait)
