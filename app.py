from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware

from config import ALLOWED_ORIGINS
from routers.public import router as public_router
from routers.admin import router as admin_router, login_router

app = FastAPI(title="Kelu API", docs_url=None, redoc_url="/redoc")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["x-api-key", "Content-Type", "x-admin-token"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def root():
    return {"ok": True}


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} — Docs",
        swagger_favicon_url="/static/favicon.svg",
    )


app.include_router(public_router, prefix="/api")
app.include_router(login_router, prefix="/api/admin")
app.include_router(admin_router, prefix="/api/admin")