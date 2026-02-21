import time
from functools import wraps

def backoff(retries=3, base=0.5):
    def deco(fn):
        @wraps(fn)
        def run(*a, **k):
            for i in range(retries):
                try:
                    return fn(*a, **k)
                except Exception:
                    time.sleep(base * (2**i))
            return fn(*a, **k)
        return run
    return deco
