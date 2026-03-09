from __future__ import annotations

import unittest

import requests

from data_service.akshare_runtime import disable_requests_env_proxy


class DisableRequestsEnvProxyTests(unittest.TestCase):
    def test_context_forces_new_sessions_to_ignore_env_proxy(self) -> None:
        original_init = requests.sessions.Session.__init__

        with disable_requests_env_proxy():
            session = requests.Session()
            self.assertFalse(session.trust_env)
            self.assertIsNot(requests.sessions.Session.__init__, original_init)

        self.assertIs(requests.sessions.Session.__init__, original_init)


if __name__ == "__main__":
    unittest.main()
