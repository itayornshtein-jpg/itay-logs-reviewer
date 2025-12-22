import sys
import tempfile
import zipfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logs_reviewer.analyzer import analyze_logs  # noqa: E402
from logs_reviewer.reader import collect_sources  # noqa: E402


def create_sample_logs(tmpdir: Path):
    file1 = tmpdir / "app.log"
    file1.write_text(
        """
INFO Something happened
ERROR connection refused at host
Traceback (most recent call last):
ValueError: boom
""".strip()
    )

    file2 = tmpdir / "service.log"
    file2.write_text(
        """
INFO starting
CRITICAL timeout talking to database
""".strip()
    )

    return [file1, file2]


def create_zip(tmpdir: Path, files):
    zip_path = tmpdir / "logs.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for file in files:
            archive.write(file, arcname=file.name)
    return zip_path


class AnalyzerTests(unittest.TestCase):
    def test_analyze_directory_and_zip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            files = create_sample_logs(temp_path)
            zip_path = create_zip(temp_path, files)

            directory_report = analyze_logs(collect_sources(temp_path))
            self.assertEqual(directory_report.scanned_sources, 2)
            self.assertGreaterEqual(directory_report.total_findings, 3)
            self.assertIn("error", directory_report.totals_by_category)

            zip_report = analyze_logs(collect_sources(zip_path))
            self.assertEqual(zip_report.scanned_sources, 2)
            self.assertGreaterEqual(zip_report.total_findings, 3)
            self.assertTrue(any("connection refused" in f.line for f in zip_report.findings))


if __name__ == "__main__":
    unittest.main()
