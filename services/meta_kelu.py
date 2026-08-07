import json
import time

import requests
from config import (
    KELU_IG_ACCESS_TOKEN,
    KELU_IG_ACCOUNT_ID,
    KELU_FB_PAGE_ID,
    KELU_FB_PAGE_TOKEN,
)

GRAPH_VERSION = "v19.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def _wait_for_ig_container(creation_id: str, max_wait_seconds: int = 60, interval: int = 2) -> None:
    """
    Instagram procesa cada media container de forma asíncrona (descarga la
    imagen, la valida, etc.). Publicar antes de que el status_code sea
    FINISHED falla con "Media ID is not available" — así que esperamos.
    """
    elapsed = 0
    while elapsed < max_wait_seconds:
        resp = requests.get(
            f"{GRAPH_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": KELU_IG_ACCESS_TOKEN},
            timeout=15,
        )
        data = resp.json()
        status_code = data.get("status_code")
        if status_code == "FINISHED":
            return
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram no pudo procesar el media container {creation_id}: {data}")
        time.sleep(interval)
        elapsed += interval
    raise RuntimeError(f"Timeout esperando que el media container IG {creation_id} esté listo")


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
    _wait_for_ig_container(creation_id)

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
        child_id = data["id"]
        _wait_for_ig_container(child_id)
        child_ids.append(child_id)

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

    _wait_for_ig_container(container_data["id"])

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
