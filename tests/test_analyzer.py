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


if __name__ == "__main__":
    unittest.main()
