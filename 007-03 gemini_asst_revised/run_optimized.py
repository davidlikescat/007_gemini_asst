#!/usr/bin/env python3
"""
최적화된 Discord Task Bot 실행 스크립트
"""

import sys
from pathlib import Path

# src 디렉토리를 Python 경로에 추가
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.main import main

if __name__ == "__main__":
    main()