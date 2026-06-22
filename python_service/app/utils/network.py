import asyncio
import functools
import random
import time
import requests
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Fast-fail keywords: don't waste time retrying these
_NO_RETRY_KEYWORDS = ("Too Many Requests", "Rate limited", "429", "Forbidden")

async def safe_ak_call(func: Callable[..., T], *args, max_retries: int = 2, initial_delay: float = 1.0, **kwargs) -> T:
    """
    Safely execute an AkShare call with retries and exponential backoff.
    Handles RemoteDisconnected and other transient network issues.
    Reduced from 3→2 retries with shorter delays for overseas servers.
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
