import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.config import router as config_router
from app.api.dashboard import router as dashboard_router
from app.api.reference import router as reference_router
from app.api.runs import router as runs_router
from app.db import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="PAIGS WildID", version="0.1.0")

# Without this, a frontend running on any other origin (a React dev
# server, a deployed SPA on its own domain) is blocked by the browser
# before a request ever reaches this API -- CORS is enforced client-side,
# not something a request itself can work around. PAIGS_CORS_ORIGINS is a
# comma-separated allowlist for real deployments; the "*" fallback is
# fine for a prototype with no fixed frontend origin yet, and safe
# alongside allow_credentials=False since this API is authenticated via
# a Bearer token in the Authorization header, not cookies (browsers
# reject a wildcard origin combined with allow_credentials=True).
_cors_origins_env = os.environ.get("PAIGS_CORS_ORIGINS", "*")
_cors_origins = (
    ["*"] if _cors_origins_env == "*" else [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router)
app.include_router(reference_router)
app.include_router(config_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(dashboard_router)


@app.get("/health")
def health():
    return {"status": "ok"}
