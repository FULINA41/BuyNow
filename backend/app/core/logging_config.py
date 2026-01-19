import sys
import logging
from loguru import logger
from pathlib import Path

LOG_DIR=Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

class InterceptHandler(logging.Handler):
    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())

def setup_logging():
    # 1. clear all default handlers
    logger.remove()

    # 2. configure console log (for development environment)
    logger.add(
        sys.stdout,
        enqueue=True,
        backtrace=True,
        level="DEBUG",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )

    # 3. configure full log file (by day, auto compress)
    logger.add(
        str(LOG_DIR / "app_all_{time:YYYY-MM-DD}.log"),
        rotation="00:00",    # create new file every day at midnight
        retention="10 days", # keep last 10 days
        compression="zip",   # compress old files
        level="INFO",
        enqueue=True         # async write, not block main thread
    )

    # 4. configure error log file (only record ERROR level)
    logger.add(
        str(LOG_DIR / "app_error.log"),
        rotation="50 MB",
        level="ERROR",
        backtrace=True,
        diagnose=True,
        encoding="utf-8"
    )

    # 5. intercept third-party library logs
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    
    # if you want to disable a specific library, you can write:
    # logging.getLogger("uvicorn.access").handlers = [] 

    return logger