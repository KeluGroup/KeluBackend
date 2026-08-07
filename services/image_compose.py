import io
import logging
import os
import textwrap

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "fonts", "Anton-Regular.ttf")
CANVAS_SIZE = 1080
MAX_TEXT_WIDTH = CANVAS_SIZE - 140  # margen a los costados
GRADIENT_HEIGHT = 620
MIN_FONT_SIZE = 44
MAX_FONT_SIZE = 88


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATH, size)


def _fit_text(draw: ImageDraw.ImageDraw, text: str) -> tuple[str, ImageFont.FreeTypeFont, tuple]:
    """Prueba tamaños de fuente decrecientes hasta que el texto envuelto entre en el ancho disponible."""
    for font_size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -4):
        font = _load_font(font_size)
        # ancho de envoltura aproximado según el tamaño de fuente
        wrap_width = max(10, int(22 * (72 / font_size)))
        wrapped = textwrap.fill(text, width=wrap_width)
        bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=12, align="center")
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        if text_w <= MAX_TEXT_WIDTH and text_h <= GRADIENT_HEIGHT - 100:
            return wrapped, font, bbox
    # último recurso: la fuente más chica, aunque no entre perfecto
    font = _load_font(MIN_FONT_SIZE)
    wrapped = textwrap.fill(text, width=18)
    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=12, align="center")
    return wrapped, font, bbox


def compose_hook_image(source_url: str, hook_text: str) -> bytes:
    """
    Descarga la foto de `source_url`, la recorta a cuadrado y le superpone
    `hook_text` en grande sobre un degradado oscuro en la parte inferior —
    estilo tarjeta editorial (ej. posts de NYT Cooking / cuentas de comida).

    Devuelve los bytes del JPEG resultante.
    """
    resp = requests.get(source_url, timeout=20)
    resp.raise_for_status()

    base = Image.open(io.BytesIO(resp.content)).convert("RGB")
    base = ImageOps.fit(base, (CANVAS_SIZE, CANVAS_SIZE), Image.LANCZOS)
    base = base.convert("RGBA")

    # Degradado negro hacia abajo para que el texto blanco sea legible
    # sin importar qué tan clara sea la foto de fondo.
    gradient = Image.new("L", (1, GRADIENT_HEIGHT))
    for y in range(GRADIENT_HEIGHT):
        alpha = int(215 * (y / GRADIENT_HEIGHT) ** 1.6)
        gradient.putpixel((0, y), alpha)
    gradient = gradient.resize((CANVAS_SIZE, GRADIENT_HEIGHT))
    scrim = Image.new("RGBA", (CANVAS_SIZE, GRADIENT_HEIGHT), (0, 0, 0, 255))
    scrim.putalpha(gradient)
    base.alpha_composite(scrim, (0, CANVAS_SIZE - GRADIENT_HEIGHT))

    canvas = base.convert("RGB")
    draw = ImageDraw.Draw(canvas)

    wrapped, font, bbox = _fit_text(draw, hook_text.upper())
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (CANVAS_SIZE - text_w) / 2 - bbox[0]
    y = CANVAS_SIZE - 90 - text_h - bbox[1]

    draw.multiline_text(
        (x, y), wrapped, font=font, fill="white", align="center",
        spacing=12, stroke_width=4, stroke_fill=(0, 0, 0),
    )

    buf = io.BytesIO()
    canvas.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
