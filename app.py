from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html

from config import ALLOWED_ORIGINS
from routers.public import router as public_router, health_router
from routers.admin import router as admin_router, login_router

# ── Public sub-app ────────────────────────────────────
public_app = FastAPI(title="Kelu Public API", docs_url="/docs", redoc_url="/redoc")
public_app.include_router(public_router)

# ── Admin sub-app ─────────────────────────────────────
admin_app = FastAPI(title="Kelu Admin API", docs_url="/docs", redoc_url="/redoc")
admin_app.include_router(login_router)  # POST /login  — no auth dependency
admin_app.include_router(admin_router)  # GET/PATCH /leads — admin token required

# ── Root app ──────────────────────────────────────────
app = FastAPI(title="Kelu API", docs_url=None, redoc_url=None)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(health_router)    # GET /health — always accessible

app.mount("/api/admin", admin_app)   # /api/admin/login, /api/admin/leads
app.mount("/api",       public_app)  # /api/formsubmit


@app.get("/", include_in_schema=False)
def root():
    return {"ok": True}


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui():
    return get_swagger_ui_html(
        openapi_url="/api/public/openapi.json",
        title="Kelu API — Docs",
        swagger_favicon_url="/static/favicon.svg",
    )