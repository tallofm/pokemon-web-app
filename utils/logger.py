# utils/logger.py
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = os.path.join(BASE_DIR, "data", "cache_log.txt")


def log_action(message: str) -> None:
    """Append a timestamped message to the cache audit log."""
    try:
        os.makedirs(os.path.dirname(LOG_FILE) or ".", exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as log:
            log.write(f"[{timestamp}] {message}\n")
    except Exception:
        # Logging failure should never crash the main application
        pass
