import json
import random

import requests
from config import (
    UNSPLASH_ACCESS_KEY,
    KELU_IG_ACCESS_TOKEN,
    KELU_IG_ACCOUNT_ID,
    KELU_FB_PAGE_ID,
    KELU_FB_PAGE_TOKEN,
)

GRAPH_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def fetch_foto_unsplash(query_variants: list[str], avoid_ids: set | None = None) -> dict | None:
    """
    Busca fotos en Unsplash a partir de varias variantes de búsqueda (cada una en
    inglés, 2-4 palabras, sobre el mismo tema desde ángulos distintos). Junta los
    resultados de todas las variantes en un solo pool y elige uno al azar que no
    esté en `avoid_ids`, para minimizar fotos repetidas entre posts.

    Devuelve {"id": <unsplash photo id>, "url": <regular url>} o None si no hay resultados.
    """
    if not UNSPLASH_ACCESS_KEY:
        raise RuntimeError("UNSPLASH_ACCESS_KEY no está configurada")

    avoid_ids = avoid_ids or set()
    pool = []
    seen_ids = set()

    for query in query_variants:
        resp = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "per_page": 30, "orientation": "squarish"},
            headers={"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"},
            timeout=15,
        )
        resp.raise_for_status()
        for r in resp.json().get("results", []):
            rid = r.get("id")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                pool.append(r)

    if not pool:
        return None

    candidates = [r for r in pool if r.get("id") not in avoid_ids]
    if not candidates:
        # Ya usamos todo el pool disponible para este tema — mejor repetir que fallar.
        candidates = pool

    chosen = random.choice(candidates)
    return {"id": chosen.get("id"), "url": chosen.get("urls", {}).get("regular")}


def publish_to_instagram(image_url: str, caption: str) -> dict:
    """Publica una foto en el feed de Instagram vía Meta Graph API (2 pasos: crear + publicar)."""
    if not KELU_IG_ACCESS_TOKEN or not KELU_IG_ACCOUNT_ID:
        raise RuntimeError("KELU_IG_ACCESS_TOKEN / KELU_IG_ACCOUNT_ID no configurados")

    create_resp = requests.post(
        f"{GRAPH_BASE}/{KELU_IG_ACCOUNT_ID}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": KELU_IG_ACCESS_TOKEN,
        },
        timeout=30,
    )
    create_data = create_resp.json()
    if not create_resp.ok:
        raise RuntimeError(f"Error creando media container IG: {create_data}")

    creation_id = create_data["id"]

    publish_resp = requests.post(
        f"{GRAPH_BASE}/{KELU_IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": creation_id, "access_token": KELU_IG_ACCESS_TOKEN},
        timeout=30,
    )
    publish_data = publish_resp.json()
    if not publish_resp.ok:
        raise RuntimeError(f"Error publicando en IG: {publish_data}")

    post_id = publish_data["id"]
    return {"id": post_id, "url": f"https://www.instagram.com/p/{post_id}"}


def publish_to_facebook(image_url: str, caption: str) -> dict:
    """Publica una foto en la página de Facebook vía Meta Graph API."""
    if not KELU_FB_PAGE_TOKEN or not KELU_FB_PAGE_ID:
        raise RuntimeError("KELU_FB_PAGE_TOKEN / KELU_FB_PAGE_ID no configurados")

    resp = requests.post(
        f"{GRAPH_BASE}/{KELU_FB_PAGE_ID}/photos",
        data={
            "url": image_url,
            "caption": caption,
            "access_token": KELU_FB_PAGE_TOKEN,
        },
        timeout=30,
    )
    data = resp.json()
    if not resp.ok:
        raise RuntimeError(f"Error publicando en FB: {data}")

    post_id = data.get("post_id", data.get("id"))
    return {"id": post_id, "url": f"https://www.facebook.com/{post_id}"}


def publish_carousel_to_instagram(image_urls: list[str], caption: str) -> dict:
    """Publica un carrusel (2-10 fotos) en el feed de Instagram."""
    if not KELU_IG_ACCESS_TOKEN or not KELU_IG_ACCOUNT_ID:
        raise RuntimeError("KELU_IG_ACCESS_TOKEN / KELU_IG_ACCOUNT_ID no configurados")
    if not (2 <= len(image_urls) <= 10):
        raise RuntimeError("Un carrusel de Instagram necesita entre 2 y 10 imágenes")

    child_ids = []
    for image_url in image_urls:
        resp = requests.post(
            f"{GRAPH_BASE}/{KELU_IG_ACCOUNT_ID}/media",
            data={
                "image_url": image_url,
                "is_carousel_item": "true",
                "access_token": KELU_IG_ACCESS_TOKEN,
            },
            timeout=30,
        )
        data = resp.json()
        if not resp.ok:
            raise RuntimeError(f"Error creando slide del carrusel IG: {data}")
        child_ids.append(data["id"])

    container_resp = requests.post(
        f"{GRAPH_BASE}/{KELU_IG_ACCOUNT_ID}/media",
        data={
            "media_type": "CAROUSEL",
            "children": ",".join(child_ids),
            "caption": caption,
            "access_token": KELU_IG_ACCESS_TOKEN,
        },
        timeout=30,
    )
    container_data = container_resp.json()
    if not container_resp.ok:
        raise RuntimeError(f"Error creando contenedor de carrusel IG: {container_data}")

    publish_resp = requests.post(
        f"{GRAPH_BASE}/{KELU_IG_ACCOUNT_ID}/media_publish",
        data={"creation_id": container_data["id"], "access_token": KELU_IG_ACCESS_TOKEN},
        timeout=30,
    )
    publish_data = publish_resp.json()
    if not publish_resp.ok:
        raise RuntimeError(f"Error publicando carrusel IG: {publish_data}")

    post_id = publish_data["id"]
    return {"id": post_id, "url": f"https://www.instagram.com/p/{post_id}"}


def publish_carousel_to_facebook(image_urls: list[str], caption: str) -> dict:
    """Publica un post multi-foto (álbum en el feed) en la página de Facebook."""
    if not KELU_FB_PAGE_TOKEN or not KELU_FB_PAGE_ID:
        raise RuntimeError("KELU_FB_PAGE_TOKEN / KELU_FB_PAGE_ID no configurados")

    media_ids = []
    for image_url in image_urls:
        resp = requests.post(
            f"{GRAPH_BASE}/{KELU_FB_PAGE_ID}/photos",
            data={
                "url": image_url,
                "published": "false",
                "access_token": KELU_FB_PAGE_TOKEN,
            },
            timeout=30,
        )
        data = resp.json()
        if not resp.ok:
            raise RuntimeError(f"Error subiendo foto del carrusel FB: {data}")
        media_ids.append(data["id"])

    feed_data = {
        "message": caption,
        "access_token": KELU_FB_PAGE_TOKEN,
    }
    for i, media_id in enumerate(media_ids):
        feed_data[f"attached_media[{i}]"] = json.dumps({"media_fbid": media_id})

    resp = requests.post(f"{GRAPH_BASE}/{KELU_FB_PAGE_ID}/feed", data=feed_data, timeout=30)
    data = resp.json()
    if not resp.ok:
        raise RuntimeError(f"Error publicando carrusel FB: {data}")

    post_id = data.get("id")
    return {"id": post_id, "url": f"https://www.facebook.com/{post_id}"}
