from fastapi import APIRouter, Depends, Request, HTTPException
from schemas.models import FormSubmission
from services.airtable import create_lead
from core.auth import verify_api_key
from core.exceptions import build_exception

# ── No auth — always accessible ───────────────────────
health_router = APIRouter()

@health_router.get("/health")
def health():
    return {"status": "healthy"}


# ── Protected — requires API key ──────────────────────
router = APIRouter(dependencies=[Depends(verify_api_key)])

@router.post("/formsubmit")
def form_submit(payload: FormSubmission, request: Request):
    try:
        airtable_response = create_lead(payload.model_dump())
        return {
            "success":     True,
            "status_code": 200,
            "message":     "Form submission received",
            "airtable":    airtable_response,
        }
    except HTTPException:
        raise
    except PermissionError as exc:
        raise build_exception(502, "Submission service authentication failed", exc) from exc
    except TimeoutError as exc:
        raise build_exception(503, "Submission service temporarily unavailable", exc) from exc
    except ConnectionError as exc:
        raise build_exception(503, "Submission service unreachable", exc) from exc
    except ValueError as exc:
        raise build_exception(502, "Submission service rejected the request", exc) from exc
    except Exception as exc:
        raise build_exception(500, "Internal server error", exc) from exc