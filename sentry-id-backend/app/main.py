from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.db.seed import seed_if_empty
from app.routers import ai_testing, audit, documents, face, fraud, identity, intelligence, risk, screen

configure_logging()
logger = logging.getLogger("sentry_id.main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_if_empty()
    logger.info("startup_complete environment=%s", settings.environment)
    yield


app = FastAPI(
    title=settings.app_name,
    description=(
        "Prototype backend for an AI-assisted document & identity screening system. "
        "All AI results are SIMULATED/DEMO unless explicitly stated otherwise, and all "
        "identity data is synthetic. See each service module's docstring for the "
        "intended production model swap-in."
    ),
    version="0.1.0-prototype",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("unhandled_exception path=%s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error. This has been logged."},
    )


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "environment": settings.environment}


app.include_router(documents.router)
app.include_router(face.router)
app.include_router(identity.router)
app.include_router(fraud.router)
app.include_router(intelligence.router)
app.include_router(ai_testing.router)
app.include_router(risk.router)
app.include_router(screen.router)
app.include_router(audit.router)
