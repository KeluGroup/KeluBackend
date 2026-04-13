from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.middleware.cors import CORSMiddleware
from fastapi import Request
from fastapi.responses import Response

from config import ALLOWED_ORIGINS
from routers.public import router as public_router, health_router
from routers.admin import router as admin_router, login_router

# ── CORS config ───────────────────────────────────────
PUBLIC_ORIGINS = ["*"]
ADMIN_ORIGINS  = ALLOWED_ORIGINS  # ["https://www.kelugroup.ch", "https://kelugroup.ch"]

# ── Public sub-app ────────────────────────────────────
public_app = FastAPI(title="Kelu Public API", docs_url="/docs", redoc_url="/redoc")
public_app.add_middleware(
    CORSMiddleware,
    allow_origins=PUBLIC_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["x-api-key", "Content-Type"],
)
public_app.include_router(public_router)

# ── Admin sub-app ─────────────────────────────────────
admin_app = FastAPI(title="Kelu Admin API", docs_url="/docs", redoc_url="/redoc")
admin_app.add_middleware(
    CORSMiddleware,
    allow_origins=ADMIN_ORIGINS,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "x-admin-token"],
)


@admin_app.options("/{rest_of_path:path}")
async def admin_preflight(rest_of_path: str, request: Request):
    origin = request.headers.get("origin", "")
    allowed = origin if origin in ADMIN_ORIGINS else ""
    return Response(
        status_code=204,
        headers={
            "Access-Control-Allow-Origin":  allowed,
            "Access-Control-Allow-Methods": "GET, POST, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, x-admin-token",
            "Access-Control-Max-Age":       "86400",
        }
    )

admin_app.include_router(login_router)  # POST /login  — no auth dependency
admin_app.include_router(admin_router)  # GET/PATCH /leads — admin token required

# ── Root app ──────────────────────────────────────────
app = FastAPI(title="Kelu API", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=PUBLIC_ORIGINS,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["Content-Type"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(health_router)        # GET /health — no auth, always accessible

app.mount("/api", public_app)     # POST /api/public/formsubmit
app.mount("/api/admin",  admin_app)      # /api/admin/login, /api/admin/leads


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