from fastapi import APIRouter, Depends

from schemas.models import ContentTrigger
from services.kelu_content import run_kelu_content, CONTENT_MAP
from core.auth import verify_cron_secret
from core.exceptions import build_exception

router = APIRouter(dependencies=[Depends(verify_cron_secret)])


@router.get("/kelu-receta")
def cron_kelu_receta():
    """
    Llamado por el cron de Vercel una vez al día (ver vercel.json).
    Rota entre 4 tipos de contenido: receta de la semana, tendencia gastronómica,
    carrusel de logística/distribución y dato curioso.
    También se puede probar manualmente:
        GET /api/cron/kelu-receta?secret=<CRON_SECRET>
    """
    try:
        result = run_kelu_content()
        return {"success": True, **result}
    except Exception as exc:
        raise build_exception(500, "Failed to run kelu content cron", exc) from exc


@router.post("/kelu-receta")
def cron_kelu_receta_trigger(body: ContentTrigger):
    """
    Fuerza la publicación de un contenido puntual, ignorando el guard diario
    y la rotación automática. Útil para pruebas:
        POST /api/cron/kelu-receta
        Authorization: Bearer <CRON_SECRET>
        { "content_type": "carrusel", "index": 1 }

    content_type: "receta" | "tendencia" | "carrusel" | "dato_curioso" (default "receta")
    """
    tipo = body.content_type or "receta"
    if tipo not in CONTENT_MAP:
        raise build_exception(
            400,
            f"content_type inválido. Debe ser uno de: {', '.join(CONTENT_MAP)}",
            ValueError("invalid content_type"),
        )

    publicar_fn, items = CONTENT_MAP[tipo]
    index = body.index if body.index is not None else 0
    if index >= len(items):
        raise build_exception(
            400,
            f"index inválido para '{tipo}'. Debe estar entre 0 y {len(items) - 1}.",
            ValueError("index out of range"),
        )

    try:
        item = items[index]
        result = publicar_fn(item)
        return {"success": True, "content_type": tipo, **result}
    except Exception as exc:
        raise build_exception(500, "Failed to publish forced content", exc) from exc
