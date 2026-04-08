"""
VSM AI Agent – Prisma Client (Supabase, Read-Optimized)

Provides DB access for the context_builder node.
The AI agent reads task context directly from Supabase
instead of making HTTP calls to vsm-backend API.
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from prisma import Prisma

logger = logging.getLogger(__name__)

_prisma_client: Prisma | None = None


async def connect_prisma() -> None:
    """Connect Prisma client at FastAPI startup."""
    global _prisma_client
    _prisma_client = Prisma()
    await _prisma_client.connect()
    logger.info("AI Agent: Prisma connected to Supabase")


async def disconnect_prisma() -> None:
    """Disconnect Prisma client at FastAPI shutdown."""
    global _prisma_client
    if _prisma_client and _prisma_client.is_connected():
        await _prisma_client.disconnect()
        logger.info("AI Agent: Prisma disconnected")


def get_prisma() -> Prisma:
    if _prisma_client is None or not _prisma_client.is_connected():
        raise RuntimeError("Prisma not connected — call connect_prisma() first")
    return _prisma_client


async def get_db() -> Prisma:
    """FastAPI dependency."""
    return get_prisma()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[Prisma, None]:
    """Standalone context manager for use outside FastAPI (scripts, tests)."""
    client = Prisma()
    try:
        await client.connect()
        yield client
    finally:
        if client.is_connected():
            await client.disconnect()
