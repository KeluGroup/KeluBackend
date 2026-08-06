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
    Lunes: receta de la semana (carrusel). Martes/Jueves/Sábado: dato +
    tendencia (GNews o fallback). Miércoles/Viernes/Domingo: dato curioso.
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
        { "content_type": "midweek_tip_dato", "index": 0 }

    content_type: "weekly_recipe" | "midweek_tip_dato" | "midweek_tip_foto" (default "weekly_recipe")
    index: solo aplica a los dos tipos "midweek_*" (rotación del fallback curado).
    """
    tipo = body.content_type or "weekly_recipe"
    if tipo not in CONTENT_MAP:
        raise build_exception(
            400,
            f"content_type inválido. Debe ser uno de: {', '.join(CONTENT_MAP)}",
            ValueError("invalid content_type"),
        )

    index = body.index if body.index is not None else 0
    try:
        result = CONTENT_MAP[tipo](index)
        return {"success": True, "content_type": tipo, **result}
    except Exception as exc:
        raise build_exception(500, "Failed to publish forced content", exc) from exc
