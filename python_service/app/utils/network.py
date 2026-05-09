import asyncio
import functools
import random
import time
import requests
from typing import Any, Callable, TypeVar

T = TypeVar("T")

async def safe_ak_call(func: Callable[..., T], *args, max_retries: int = 3, initial_delay: float = 2.0, **kwargs) -> T:
    """
    Safely execute an AkShare call with retries and exponential backoff.
    Handles RemoteDisconnected and other transient network issues.
    """
    last_error = None
    delay = initial_delay
    
    for attempt in range(max_retries):
        try:
            # AkShare is mostly synchronous, but we often call it in an executor
            # If func is already wrapped in a thread-pool by the caller, we just call it
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                # If it's a standard sync function, we use the default executor to not block the event loop
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, functools.partial(func, *args, **kwargs))
        except Exception as e:
            last_error = e
            # Log common disconnection errors
            err_msg = str(e)
            is_network = "RemoteDisconnected" in err_msg or "Connection aborted" in err_msg or "Connection reset" in err_msg
            if is_network:
                print(f"Network issue during AkShare call (Attempt {attempt+1}/{max_retries}): {e}")
                # Reset urllib3 connection pools to recover from stale connections
                try:
                    import urllib3
                    urllib3.disable_warnings()
                    requests.Session().close()
                except Exception:
                    pass
            else:
                print(f"Error during AkShare call (Attempt {attempt+1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                await asyncio.sleep(delay + random.uniform(0, 1))
                delay *= 2
            else:
                break
    
    raise last_error
