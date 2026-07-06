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

# Data-parsing errors: upstream returned bad data, retrying won't help
_DATA_ERROR_KEYWORDS = ("NoneType", "KeyError", "IndexError", "KeyError", "list index out of range")

async def safe_ak_call(func: Callable[..., T], *args, max_retries: int = 2, initial_delay: float = 0.3, **kwargs) -> T:
    """
    Safely execute an AkShare call with retries and exponential backoff.
    Handles RemoteDisconnected and other transient network issues.
    Fast retry (0.3s base) for domestic servers where transient resets are common.
    """
    last_error = None
    delay = initial_delay

    for attempt in range(max_retries):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
        except Exception as e:
            last_error = e
            err_msg = str(e)

            # Fast-fail: don't retry rate-limited or forbidden requests
            if any(kw in err_msg for kw in _NO_RETRY_KEYWORDS):
                logger.warning(f"Rate limited/blocked, not retrying AkShare call: {e}")
                break

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
                break

    raise last_error
