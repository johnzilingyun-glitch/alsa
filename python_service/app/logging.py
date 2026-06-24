"""
Structured logging configuration using structlog
"""
import os
import sys
import logging
from typing import Optional

import structlog


def setup_logging(
    log_level: Optional[str] = None,
    json_output: Optional[bool] = None,
    service_name: str = "alsa"
):
    """
    Configure structured logging with structlog.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, output JSON; if False, output human-readable
        service_name: Service name for log context
    """
    if log_level is None:
        log_level = os.getenv("LOG_LEVEL", "INFO")
        
    if json_output is None:
        json_output = (
            os.getenv("JSON_LOGS", "false").lower() in ("true", "1", "yes") or
            os.getenv("LOG_FORMAT", "").lower() == "json"
        )
    
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )
    
    # Shared processors
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]
    
    if json_output:
        # JSON output for production
        renderer = structlog.processors.JSONRenderer()
    else:
        # Human-readable output for development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    
    # Configure formatter for standard library handler
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    
    # Add handler to root logger
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logging.root.handlers.clear()
    logging.root.addHandler(handler)
    logging.root.setLevel(level)
    
    # Set default context
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name)
    
    return structlog.get_logger()


# Default logger instance
logger = setup_logging()


def get_logger(name: Optional[str] = None):
    """
    Get a bound logger with optional name.
    
    Usage:
        from app.logging import get_logger
        log = get_logger("my_module")
        log.info("something happened", key="value")
    """
    if name:
        return structlog.get_logger(name)
    return structlog.get_logger()


def log_llm_call(
    model: str,
    role: str,
    symbol: str,
    latency_ms: int,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_hit: bool = False,
    provider: str = "unknown",
    success: bool = True,
    error: str = None,
):
    """
    Structured logging for LLM API calls.
    
    This provides consistent, queryable logs for:
    - Performance monitoring (latency, tokens)
    - Cost tracking (token usage)
    - Error analysis (failure rates by model/provider)
    - Cache effectiveness
    """
    log = get_logger("llm_gateway")
    extra = {
        "model": model,
        "role": role,
        "symbol": symbol,
        "provider": provider,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "cache_hit": cache_hit,
        "success": success,
    }
    if error:
        extra["error"] = error
        log.error("llm_call_failed", **extra)
    elif cache_hit:
        log.info("llm_call_cache_hit", **extra)
    else:
        log.info("llm_call_completed", **extra)
