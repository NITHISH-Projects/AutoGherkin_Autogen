# Author: MARRI NITHISH
from __future__ import annotations
import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO") -> None:
    """
    Configure root logging with a sane default formatter.
    Recommended to call once at application startup.
    """

    level_value = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Clear existing handlers to avoid duplicate logs when re-running in dev
    for h in list(root.handlers):
        root.removeHandler(h)

    root.setLevel(level_value)
    root.addHandler(handler)
