# utils/logger.py
import logging
import sys
from datetime import datetime
from pathlib import Path

def setup_logger(name: str = 'trading_bot'):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Console handler with proper encoding
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    
    # Remove emojis from log messages
    console_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Also add file handler for full logs with emojis
    try:
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler('logs/trading_bot.log', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    except:
        pass
    
    return logger