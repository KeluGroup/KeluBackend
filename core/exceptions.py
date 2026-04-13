import logging
from fastapi import HTTPException

logger = logging.getLogger(__name__)

def build_exception(status_code: int, detail: str, exc: Exception) -> HTTPException:
    if status_code >= 500:
        logger.exception("Server error [%s]: %s", status_code, exc)
    else:
        logger.warning("Client/upstream error [%s]: %s", status_code, exc)
    return HTTPException(status_code=status_code, detail=detail)