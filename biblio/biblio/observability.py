from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from biblio.specs import project_root

LOGGER_NAME = "biblio"


def default_log_path(root: Path | None = None) -> Path:
    return (root or project_root()) / "logs" / "biblio.log"


def configure_logging(*, verbose: bool, root: Path | None = None) -> Path:
    log_path = default_log_path(root)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)

    if verbose:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
        logger.addHandler(console_handler)

    logger.debug("logging configured verbose=%s path=%s", verbose, log_path)
    return log_path


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)


def format_elapsed(seconds: float) -> str:
    if seconds >= 10:
        return f"{seconds:.1f}s"
    if seconds >= 1:
        return f"{seconds:.2f}s"
    return f"{seconds:.3f}s"
