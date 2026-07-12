import logging

logger = logging.getLogger(__name__)

# Monkey patch requests to always use a timeout.
# Prevents calls without a timeout from hanging forever.
import requests as _requests
_original_request = _requests.Session.request
def _patched_request(self, method, url, **kwargs):
    if kwargs.get("timeout") is None:
        kwargs["timeout"] = 15.0
    return _original_request(self, method, url, **kwargs)
_requests.Session.request = _patched_request
