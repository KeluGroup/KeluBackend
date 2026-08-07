import base64
import logging

from openai import OpenAI

from config import OPENAI_API_KEY

logger = logging.getLogger(__name__)

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
    """
    client = _get_client()
    prompt = f"{description}\n\n{STYLE_GUIDE}"
    result = client.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size="1024x1024",
        quality="medium",
        n=1,
    )
    b64 = result.data[0].b64_json
    return base64.b64decode(b64)
