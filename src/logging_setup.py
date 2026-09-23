import logging
from pathlib import Path


def setup_logging(results_dir: str, level: str = "INFO") -> Path:
    log_dir = Path(results_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "run.log"
    logger = logging.getLogger()
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return log_path
