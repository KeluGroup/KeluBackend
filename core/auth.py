import hmac
import hashlib
import base64
import time
import bcrypt
from fastapi import HTTPException, Request
from config import API_SECRET, ADMIN_PASSWORD, ADMIN_PASSWORD_HASH


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