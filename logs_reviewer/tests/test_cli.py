import unittest
from datetime import datetime

from logs_reviewer.analyzer import AnalysisReport
from logs_reviewer.cli import format_report
from logs_reviewer.sso import ChatGPTSession


class FormatReportTests(unittest.TestCase):
    def test_includes_chatgpt_section_when_connected(self):
        report = AnalysisReport(findings=[], totals_by_category={}, top_messages=[], scanned_sources=1)
        session = ChatGPTSession(
            account="alice@example.com",
            resources={"models": ["gpt-4o-mini"], "quota": "team"},
            token_hint="***test",
            connected_at=datetime.utcnow(),
        )

        output = format_report(report, session)

        self.assertIn("ChatGPT SSO", output)
        self.assertIn("alice@example.com", output)
        self.assertIn("quota: team", output)


if __name__ == "__main__":
    unittest.main()
