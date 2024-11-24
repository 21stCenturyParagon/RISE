import logging
import sys
from pathlib import Path
from loguru import logger

from pydantic import BaseModel
import json
from datetime import datetime

# Create logs directory if it doesn't exist
LOGS_DIR = Path("logs")
LOGS_DIR.mkdir(exist_ok=True)

class LogConfig(BaseModel):
    """Logging configuration"""
    LOGGER_NAME: str = "tmua_api"
    LOG_FORMAT: str = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    LOG_LEVEL: str = "DEBUG"

    # File configurations
    LOG_FILE_DEBUG: str = str(LOGS_DIR / "debug.log")
    LOG_FILE_ERROR: str = str(LOGS_DIR / "error.log")
    LOG_FILE_INFO: str = str(LOGS_DIR / "info.log")

class InterceptHandler(logging.Handler):
    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )

def setup_logging():
    """Set up logging configuration"""
    # Remove default handlers
    logger.remove()

    # Add handlers for different log levels
    # Debug logs - Contains all logs
    logger.add(
        LogConfig().LOG_FILE_DEBUG,
        rotation="1 day",
        retention="1 week",
        format=LogConfig().LOG_FORMAT,
        level="DEBUG",
        compression="zip"
    )

    # Info logs - Contains info and above
    logger.add(
        LogConfig().LOG_FILE_INFO,
        rotation="1 day",
        retention="1 month",
        format=LogConfig().LOG_FORMAT,
        level="INFO",
        compression="zip",
        filter=lambda record: record["level"].name in ["INFO", "WARNING", "ERROR", "CRITICAL"]
    )

    # Error logs - Contains only error and critical
    logger.add(
        LogConfig().LOG_FILE_ERROR,
        rotation="1 day",
        retention="3 months",
        format=LogConfig().LOG_FORMAT,
        level="ERROR",
        compression="zip",
        filter=lambda record: record["level"].name in ["ERROR", "CRITICAL"]
    )

    # Console output
    logger.add(
        sys.stdout,
        format=LogConfig().LOG_FORMAT,
        level="INFO",
        colorize=True
    )

    # Intercept standard logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0)

    # Intercept FastAPI logging
    for _log in ["uvicorn", "uvicorn.error", "fastapi"]:
        _logger = logging.getLogger(_log)
        _logger.handlers = [InterceptHandler()]

    return logger

# Custom JSON formatter for structured logging
class JsonFormatter:
    def __init__(self, keywords):
        self.keywords = keywords

    @staticmethod
    def format(record):
        json_record = {"timestamp": datetime.utcnow().isoformat(), "level": record["level"].name,
                       "message": record["message"]}

        # Add extra fields if they exist
        if record["extra"]:
            for key, value in record["extra"].items():
                json_record[key] = value

        # Add exception info if it exists
        if record["exception"]:
            json_record["exception"] = str(record["exception"])

        return json.dumps(json_record)

# Create a context manager for operation logging
class OperationLogger:
    def __init__(self, operation_name: str, **kwargs):
        self.operation_name = operation_name
        self.extra = kwargs

    def __enter__(self):
        logger.info(
            f"Starting operation: {self.operation_name}",
            operation=self.operation_name,
            **self.extra
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            logger.error(
                f"Operation failed: {self.operation_name}",
                operation=self.operation_name,
                error=str(exc_val),
                **self.extra
            )
        else:
            logger.info(
                f"Operation completed: {self.operation_name}",
                operation=self.operation_name,
                **self.extra
            )