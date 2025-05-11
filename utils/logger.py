import logging
import os

def setup_logger():
    """Configure and return a logger for the application."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Create logger
    logger = logging.getLogger("telegram_bot")
    logger.setLevel(getattr(logging, log_level))
    
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level))
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    return logger 