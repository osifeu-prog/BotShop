import logging, os, structlog

def setup_logging():
    level = getattr(logging, os.getenv("LOG_LEVEL","INFO").upper(), logging.INFO)
    logging.basicConfig(level=level)
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    return structlog.get_logger("Botshop")