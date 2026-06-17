"""
Monkey-patch for AkShare's requests.Session keep-alive bug.

Root cause: requests.Session sends 'Connection: keep-alive' by default,
but EastMoney servers close the connection immediately, causing
'RemoteDisconnected' errors.

Fix: Override Session.__init__ to add 'Connection: close' header.
"""
import requests
from requests.adapters import HTTPAdapter

_original_session_init = requests.Session.__init__

def _patched_session_init(self, *args, **kwargs):
    _original_session_init(self, *args, **kwargs)
    self.headers.update({"Connection": "close"})

requests.Session.__init__ = _patched_session_init
