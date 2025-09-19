import logging
import sys
from pathlib import Path

def setup_logging(log_level: str = "INFO", log_file: str = "bot.log") -> logging.Logger:
    """로깅 설정"""

    # 로그 레벨 설정
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # 로거 설정
    logger = logging.getLogger()
    logger.setLevel(numeric_level)

    # 기존 핸들러 제거
    for handler in logger.handlers:
        logger.removeHandler(handler)

    # 포매터 설정
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger