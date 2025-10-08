from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional

from fastapi import FastAPI, Request

from api_routes import router
from core.database import initialize_database
from core.error_handlers import (
    value_error_handler,
    runtime_error_handler,
    generic_exception_handler,
)


@dataclass
class AppConfig:
    """Configuration values used when constructing a FastAPI application."""

    title: str
    description: str
    version: str = "1.0.0"
    environment: Optional[str] = None
    root_message: str = "Expense Tracker API"
    log_context: Optional[str] = None

    @property
    def context_label(self) -> str:
        """Return the string used in lifecycle logs."""
        return self.log_context or self.title


def _configure_logging() -> logging.Logger:
    """Configure application logging and return the shared logger."""
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
    )
    logger = logging.getLogger("expense_tracker.api")
    logger.setLevel(level)
    return logger


def create_app(config: AppConfig) -> FastAPI:
    """Create a FastAPI application instance using shared routing."""
    logger = _configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Handle startup and shutdown tasks shared across environments."""
        logger.info("Starting %s", config.context_label)
        try:
            if initialize_database():
                logger.info("Database initialized successfully")
            else:
                logger.error("Failed to initialize database")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Database initialization error: %s", exc)

        yield

        logger.info("Shutting down %s", config.context_label)

    app = FastAPI(
        title=config.title,
        description=config.description,
        version=config.version,
        lifespan=lifespan,
    )

    app.state.config = config

    # Register exception handlers
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(RuntimeError, runtime_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log every incoming request and its response time."""
        start_time = datetime.now(UTC)
        logger.info("Request: %s %s", request.method, request.url)

        response = await call_next(request)

        process_time = (datetime.now(UTC) - start_time).total_seconds()
        logger.info("Response: %s - %.3fs", response.status_code, process_time)

        return response

    app.include_router(router)
    return app
