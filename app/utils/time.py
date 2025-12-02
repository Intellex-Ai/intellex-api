import time

def now_ms() -> int:
    """
    Return the current time in milliseconds.
    Centralized helper to keep timestamp generation consistent across modules.
    """
    return int(time.time() * 1000)
