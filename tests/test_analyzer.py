import unittest

from logs_reviewer.analyzer import _match_category, analyze_logs, LogFinding
from logs_reviewer.reader import LogSource


class MatchCategoryTests(unittest.TestCase):
    def test_matches_exceptions_ending_with_error(self):
        line = "Encountered ValueError while processing request"
        self.assertEqual(_match_category(line), "exception")

    def test_prefers_error_keyword_over_exception_pattern(self):
        line = "2024-01-01 12:00:00 ERROR Something went wrong"
        self.assertEqual(_match_category(line), "error")


class AnalyzeLogsTests(unittest.TestCase):
    def test_detects_value_error_findings(self):
        source = LogSource(name="app.log", lines=["ValueError: invalid input"])
        report = analyze_logs([source])
        self.assertEqual(report.total_findings, 1)
        finding = report.findings[0]
        self.assertIsInstance(finding, LogFinding)
        self.assertEqual(finding.category, "exception")
        self.assertEqual(finding.line_no, 1)

    def test_collects_resize_actions_and_tails(self):
        uuid = "123e4567-e89b-12d3-a456-426614174000"
        resize_lines = [
            f"{uuid} status=started",
            f"{uuid} status=running",
            f"{uuid} status=progress",
            f"{uuid} status=almost-done",
            f"{uuid} status=finalizing",
            f"{uuid} status=done",
        ]
        collector_lines = [f"collector check {idx}" for idx in range(1, 7)]
        agent_lines = [f"agent log line {idx}" for idx in range(1, 21)]
        sources = [
            LogSource(name="resizeActions.log", lines=resize_lines),
            LogSource(name="collectorHC.log", lines=collector_lines),
            LogSource(name="agent.log", lines=agent_lines),
        ]

        report = analyze_logs(sources)

        self.assertIn(uuid, report.resize_actions)
        self.assertEqual(len(report.resize_actions[uuid]), 5)
        self.assertEqual(report.resize_actions[uuid][-1].status, "done")
        self.assertEqual(report.collector_tail, collector_lines[-5:])
        self.assertEqual(report.agent_tail, agent_lines[-15:])

    def test_unique_errors_are_deduplicated(self):
        sources = [
            LogSource(name="app.log", lines=["ERROR Something failed", "error something failed", "ValueError: boom"]),
            LogSource(name="worker.log", lines=["ERROR Something failed"]),
        ]

        report = analyze_logs(sources)

        self.assertEqual(len(report.unique_errors), 2)
        messages = {finding.normalized_message for finding in report.unique_errors}
        self.assertIn("error something failed", messages)
        self.assertIn("valueerror: boom", messages)


if __name__ == "__main__":
    unittest.main()
