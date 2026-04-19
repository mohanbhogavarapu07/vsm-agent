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

import logging
import asyncio
import random
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from prisma import Prisma

logger = logging.getLogger(__name__)

_prisma_client: Prisma | None = None


async def connect_prisma() -> None:
    """Connect Prisma client at FastAPI startup."""
    global _prisma_client
    _prisma_client = Prisma()
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            await _prisma_client.connect()
            logger.info("AI Agent: Prisma connected to Supabase")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                delay = (2.0 ** attempt) + random.uniform(0, 1.0)
                logger.warning("AI Agent DB connection attempt %d failed. Retrying in %.2fs... Error: %s", attempt + 1, delay, e)
                await asyncio.sleep(delay)
            else:
                logger.error("AI Agent DB connection failed after %d attempts: %s", attempt + 1, e)
                raise


async def disconnect_prisma() -> None:
    """Disconnect Prisma client at FastAPI shutdown."""
    global _prisma_client
    if _prisma_client and _prisma_client.is_connected():
        await _prisma_client.disconnect()
        logger.info("AI Agent: Prisma disconnected")


def get_prisma() -> Prisma:
    global _prisma_client
    if _prisma_client is None:
        _prisma_client = Prisma()
    
    # We don't check is_connected() here because connect() may be handled 
    # asychronously or via connect_prisma at startup. Downstream nodes
    # will trigger the auto-reconnect logic in get_db_context if needed.
    return _prisma_client


async def get_db() -> Prisma:
    """FastAPI dependency."""
    return get_prisma()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[Prisma, None]:
    """
    Persistent context manager for use in nodes and scripts.
    Reuses the singleton client and handles re-connections with retries.
    """
    client = get_prisma()
    
    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            if not client.is_connected():
                await client.connect()
                logger.info("AI Agent: Worker Prisma connected (Persistent)")
            
            yield client
            return
        except Exception as e:
            error_str = str(e)
            is_conn_error = "P1001" in error_str or "connection" in error_str.lower()
            
            if is_conn_error and attempt < max_retries - 1:
                delay = (base_delay * (2 ** attempt)) + random.uniform(0, 1.0)
                logger.warning("AI Agent context connection failed (Attempt %d/%d). Retrying in %.2fs...", attempt+1, max_retries, delay)
                await asyncio.sleep(delay)
            else:
                logger.error("AI Agent persistent connection failed: %s", e)
                raise

