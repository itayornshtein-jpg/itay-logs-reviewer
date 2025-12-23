import os
import unittest

from logs_reviewer.sso import ChatGPTSession, connect_chatgpt_via_sso


class ChatGPTSSOTests(unittest.TestCase):
    def tearDown(self):
        for key in ["CHATGPT_SSO_TOKEN", "CHATGPT_SSO_RESOURCES", "CHATGPT_SSO_ACCOUNT"]:
            os.environ.pop(key, None)

    def test_requires_token(self):
        os.environ.pop("CHATGPT_SSO_TOKEN", None)
        with self.assertRaises(ValueError):
            connect_chatgpt_via_sso()

    def test_uses_env_token_and_resources(self):
        os.environ["CHATGPT_SSO_TOKEN"] = "secret-token"
        os.environ["CHATGPT_SSO_RESOURCES"] = '{"models": ["gpt-4o-mini"], "quota": "team"}'
        os.environ["CHATGPT_SSO_ACCOUNT"] = "alice@example.com"

        session = connect_chatgpt_via_sso()

        self.assertIsInstance(session, ChatGPTSession)
        self.assertEqual(session.account, "alice@example.com")
        self.assertIn("quota: team", session.resource_summary)
        self.assertTrue(session.token_hint.endswith("oken"))

    def test_explicit_token_overrides_env(self):
        os.environ["CHATGPT_SSO_TOKEN"] = "env-token"
        session = connect_chatgpt_via_sso(token="explicit-token")
        self.assertTrue(session.token_hint.endswith("oken"))


if __name__ == "__main__":
    unittest.main()
