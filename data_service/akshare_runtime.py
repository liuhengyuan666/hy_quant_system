from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import requests


@contextmanager
def disable_requests_env_proxy() -> Iterator[None]:
    original_init = requests.sessions.Session.__init__

    def patched_init(self: requests.sessions.Session, *args: object, **kwargs: object) -> None:
        original_init(self, *args, **kwargs)
        self.trust_env = False

    requests.sessions.Session.__init__ = patched_init
    try:
        yield
    finally:
        requests.sessions.Session.__init__ = original_init
