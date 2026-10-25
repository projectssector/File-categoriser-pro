import logging
import os
import sys
from pathlib import Path


def setup_logging(log_dir: str | Path = "data/logs", level: str | None = None) -> None:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    level = level or os.getenv("LOG_LEVEL", "INFO")

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stderr),
            logging.FileHandler(log_dir / "categorizer.log"),
        ],
    )