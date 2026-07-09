import asyncio
import functools
import random
import requests
import logging
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

# Monkey patch requests to always use a timeout.
# AkShare frequently makes requests without a timeout, which can hang forever
# and exhaust the Celery worker's asyncio thread pool.
_original_request = requests.Session.request
def _patched_request(self, method, url, **kwargs):
    if kwargs.get("timeout") is None:
        kwargs["timeout"] = 15.0
    return _original_request(self, method, url, **kwargs)
requests.Session.request = _patched_request

T = TypeVar("T")

# Fast-fail keywords: don't waste time retrying these
_NO_RETRY_KEYWORDS = ("Too Many Requests", "Rate limited", "429", "Forbidden")

# Deterministic parse/structure errors: the upstream data or AkShare internals are
# malformed for this call. Retrying is 100% useless and only wastes wall-clock time
# (observed: `invalid escape sequence: \u`, pandas `Length mismatch`, axis mismatch).
# These previously burned 3x retries each — now fail instantly.
_DATA_ERROR_KEYWORDS = (
    "NoneType", "KeyError", "IndexError", "list index out of range",
    "invalid escape sequence", "Length mismatch", "Expected axis",
    "new values have", "could not convert", "cannot convert",
    "invalid literal", "ValueError",
)

async def safe_ak_call(func: Callable[..., T], *args, max_retries: int = 2, initial_delay: float = 0.5, **kwargs) -> T:
    """
    Safely execute an AkShare call with retries and exponential backoff.
    Handles RemoteDisconnected and other transient network issues.
    Returns None on persistent failure instead of raising (graceful degradation).
    """
    last_error = None
    delay = initial_delay

    for attempt in range(max_retries):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                loop = asyncio.get_event_loop()
                return await asyncio.wait_for(
                    loop.run_in_executor(None, functools.partial(func, *args, **kwargs)),
                    timeout=8.0  # Hard per-attempt timeout — fail fast on stalled sockets
                )
        except asyncio.TimeoutError:
            last_error = TimeoutError(f"AkShare call timed out after 8s (attempt {attempt+1})")
            logger.warning(f"Timeout during AkShare call (Attempt {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= 2
            else:
                return None  # Graceful degradation
        except Exception as e:
            last_error = e
            err_msg = str(e)

            # Fast-fail: don't retry rate-limited or forbidden requests
            if any(kw in err_msg for kw in _NO_RETRY_KEYWORDS):
                logger.warning(f"Rate limited/blocked, not retrying AkShare call: {e}")
                return None  # Graceful degradation

            # Data errors: upstream returned empty/null data, retrying won't help
            if any(kw in err_msg for kw in _DATA_ERROR_KEYWORDS):
                logger.warning(f"Data error from AkShare (not retrying): {e}")
                return None

            is_network = "RemoteDisconnected" in err_msg or "Connection aborted" in err_msg or "Connection reset" in err_msg
            if is_network:
                logger.warning(f"Network issue during AkShare call (Attempt {attempt+1}/{max_retries}): {e}")
                try:
                    import urllib3
                    urllib3.disable_warnings()
                    requests.Session().close()
                except Exception:
                    pass
            else:
                logger.error(f"Error during AkShare call (Attempt {attempt+1}/{max_retries}): {e}")

            if attempt < max_retries - 1:
                await asyncio.sleep(delay + random.uniform(0, 0.5))
                delay *= 2
            else:
                return None  # Graceful degradation instead of raising

    return None  # All retries exhausted
