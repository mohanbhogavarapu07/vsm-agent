"""
VSM AI Agent – FastAPI Application Entry Point (Prisma + Supabase)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_agent_settings
from app.database import connect_prisma, disconnect_prisma
from app.api.infer import router as infer_router
from app.api.feedback import router as feedback_router
from app.api.classify import router as classify_router

settings = get_agent_settings()

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Connecting AI Agent Prisma to Supabase...")
    await connect_prisma()
    logger.info("Prisma connected. AI Agent ready.")
    yield
    await disconnect_prisma()
    logger.info("AI Agent shut down cleanly.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "VSM AI Agent — Autonomous AI Scrum Orchestrator.\n\n"
            "Database: **Supabase (PostgreSQL)** via **Prisma ORM** (direct read access).\n\n"
            "6-node LangGraph pipeline: Events → Signals → Rules → "
            "AI Reasoning → Validation → Execution."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(infer_router)
    app.include_router(feedback_router)
    app.include_router(classify_router)

    @app.get("/health", tags=["health"])
    async def health():
        return {
            "status": "alive",
            "app": settings.app_name,
            "version": settings.app_version,
            "database": "Supabase via Prisma",
        }

    @app.get("/", tags=["root"])
    async def root():
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "orm": "Prisma Client Python",
            "db": "Supabase (PostgreSQL)",
            "graph": "context_builder → signal_interpreter → rule_engine → ai_reasoning → decision_validator → action_executor",
            "docs": "/docs",
        }

    logger.info("VSM AI Agent initialized (LLM=%s, DB=Supabase/Prisma)", settings.llm_provider)
    return app


app = create_app()
