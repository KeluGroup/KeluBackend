import hmac
import hashlib
import base64
import time
import bcrypt
from fastapi import HTTPException, Request
from config import API_SECRET, ADMIN_PASSWORD, ADMIN_PASSWORD_HASH, CRON_SECRET


def verify_api_key(request: Request) -> None:
    key = request.headers.get("x-api-key")
    if not key or key != API_SECRET:
        raise HTTPException(
            status_code=403,
            detail={"success": False, "status_code": 403, "message": "Forbidden"}
        )


def _make_token(hour_offset: int = 0) -> str:
    slot = str(int(time.time()) // 3600 + hour_offset)
    sig  = hmac.new(ADMIN_PASSWORD.encode(), slot.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(sig).decode()


def verify_admin_token(request: Request) -> None:
    token = request.headers.get("x-admin-token", "")
    if not token or not ADMIN_PASSWORD:
        raise HTTPException(status_code=403, detail="Forbidden")
    valid = any(hmac.compare_digest(token, _make_token(offset)) for offset in [0, -1])
    if not valid:
        raise HTTPException(status_code=403, detail="Forbidden")


def verify_password(plain: str) -> bool:
    if not ADMIN_PASSWORD_HASH:
        raise HTTPException(status_code=503, detail="Admin not configured — set ADMIN_PASSWORD_HASH env var")
    return bcrypt.checkpw(plain.encode("utf-8"), ADMIN_PASSWORD_HASH)


def verify_cron_secret(request: Request) -> None:
    """
    Acepta el secreto vía header 'Authorization: Bearer <secret>' o
    vía query param '?secret=<secret>' (Vercel Cron llama por GET sin headers custom).
    """
    if not CRON_SECRET:
        raise HTTPException(status_code=503, detail="Cron not configured — set CRON_SECRET env var")

    auth_header = request.headers.get("authorization", "")
    header_ok = auth_header == f"Bearer {CRON_SECRET}"

    query_secret = request.query_params.get("secret")
    query_ok = bool(query_secret) and hmac.compare_digest(query_secret, CRON_SECRET)

    if not (header_ok or query_ok):
        raise HTTPException(status_code=403, detail="Forbidden")