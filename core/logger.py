"""
Centralized logging for LoRA Data Toolkit.

Usage anywhere in the project:
    from core.logger import log
    log.info("Scrape complete")
    log.error("Something broke", exc_info=True)

Writes to:
    data/toolkit.log   (rotating, max 5 MB x 3 backups)
    console             (abbreviated)
"""

from __future__ import annotations
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from config import DATA_DIR

LOG_PATH = os.path.join(DATA_DIR, "toolkit.log")
MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
BACKUP_COUNT = 3

# ── Formatter ────────────────────────────────────────────

_FILE_FMT = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_CONSOLE_FMT = logging.Formatter(
    "%(levelname)-8s  %(message)s",
)


def _build_logger() -> logging.Logger:
    """Create the root app logger (called once at import time)."""
    logger = logging.getLogger("toolkit")
    logger.setLevel(logging.DEBUG)

    # File handler (rotating)
    fh = RotatingFileHandler(
        LOG_PATH, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FILE_FMT)
    logger.addHandler(fh)

    # Console handler (INFO+)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(_CONSOLE_FMT)
    logger.addHandler(ch)

    return logger


log = _build_logger()
