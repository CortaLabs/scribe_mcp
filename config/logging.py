"""Centralized logging configuration for Scribe MCP server.

Provides a single ``configure_logging()`` entry-point that should be called
once at server startup (before any other module-level logger is used).

The log level is controlled by the ``SCRIBE_LOG_LEVEL`` environment variable
(default: ``WARNING``).
"""

from __future__ import annotations

import logging
import logging.config
import os

LOGGING_CONFIG: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "stderr": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stderr",
        },
    },
    "loggers": {
        "scribe_mcp": {
            "level": os.environ.get("SCRIBE_LOG_LEVEL", "WARNING"),
            "handlers": ["stderr"],
            "propagate": False,
        },
    },
    "root": {
        "level": "WARNING",
        "handlers": ["stderr"],
    },
}


def configure_logging() -> None:
    """Initialize logging configuration. Call once at server startup."""
    logging.config.dictConfig(LOGGING_CONFIG)
