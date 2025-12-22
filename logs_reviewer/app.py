"""Lightweight drag-and-drop web app for reviewing logs."""
from __future__ import annotations

import base64
import io
import json
import webbrowser
import zipfile
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, List

from .analyzer import AnalysisReport, analyze_logs
from .reader import LogSource, TEXT_SUFFIXES


APP_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Itay Logs Reviewer</title>
  <style>
    :root {
      color-scheme: light dark;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    body {
      margin: 0;
      padding: 2rem;
      background: radial-gradient(circle at 20% 20%, #f1f5f9, #cbd5e1);
      min-height: 100vh;
      box-sizing: border-box;
    }
    main {
      max-width: 720px;
      margin: 0 auto;
      background: rgba(255, 255, 255, 0.9);
      padding: 1.5rem;
      border-radius: 16px;
      box-shadow: 0 12px 40px rgba(15, 23, 42, 0.15);
      color: #0f172a;
    }
    h1 {
      margin-top: 0;
      font-size: 1.8rem;
      letter-spacing: -0.02em;
    }
    #drop-zone {
      border: 2px dashed #334155;
      border-radius: 12px;
      padding: 2rem;
      text-align: center;
      background: #f8fafc;
      color: #1e293b;
      transition: all 150ms ease-in-out;
    }
    #drop-zone.hover {
      border-color: #2563eb;
      background: #eff6ff;
      box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.15);
    }
    #output-line {
      margin-top: 1rem;
      font-weight: 600;
      color: #0f172a;
      min-height: 1.5rem;
    }
    #history {
      margin-top: 1.5rem;
      border-top: 1px solid #e2e8f0;
      padding-top: 1rem;
    }
    #history h2 {
      margin: 0 0 0.5rem 0;
      font-size: 1.1rem;
      color: #0f172a;
    }
    #history-list {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 0.5rem;
    }
    .history-item {
      padding: 0.75rem;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      background: #f8fafc;
    }
    .history-meta {
      display: flex;
      justify-content: space-between;
      font-size: 0.9rem;
      color: #475569;
    }
    .history-files {
      margin: 0.3rem 0 0.2rem 0;
      color: #0f172a;
      font-weight: 600;
      font-size: 0.95rem;
    }
    .history-summary {
      margin: 0;
      color: #0f172a;
      font-size: 0.95rem;
    }
  </style>
</head>
<body>
  <main>
    <h1>Itay Logs Reviewer</h1>
    <div id="drop-zone">
      <p style="margin: 0; font-size: 1.1rem;">Drag one or more log files here</p>
      <small>Accepted: .log, .txt, .out, .err, and zip archives</small>
    </div>
    <div id="output-line"></div>
    <section id="history">
      <h2>Recent analyses</h2>
      <ul id="history-list"></ul>
    </section>
    <footer>
      Drop your logs to see a quick summary of findings. Nothing is uploaded anywhere—everything stays local to this app.
    </footer>
  </main>

  <script>
    const dropZone = document.getElementById('drop-zone');
    const outputLine = document.getElementById('output-line');
    const historyList = document.getElementById('history-list');

    function setMessage(text) {
      outputLine.textContent = text;
    }

    ['dragenter', 'dragover'].forEach(eventName => {
      dropZone.addEventListener(eventName, evt => {
        evt.preventDefault();
        evt.stopPropagation();
        dropZone.classList.add('hover');
      });
    });

    ['dragleave', 'drop'].forEach(eventName => {
      dropZone.addEventListener(eventName, evt => {
        evt.preventDefault();
        evt.stopPropagation();
        dropZone.classList.remove('hover');
      });
    });

    dropZone.addEventListener('drop', async evt => {
      const files = Array.from(evt.dataTransfer.files || []);
      if (!files.length) {
        setMessage('No files detected.');
        return;
      }
      setMessage('Processing logs...');
      try {
        const payload = [];
        for (const file of files) {
          if (file.name.toLowerCase().endsWith('.zip')) {
            const buffer = await file.arrayBuffer();
            const binary = bufferToBase64(buffer);
            payload.push({ name: file.name, content: binary, encoding: 'base64' });
          } else {
            const content = await file.text();
            payload.push({ name: file.name, content, encoding: 'text' });
          }
        }
        const response = await fetch('/analyze', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ files: payload }),
        });
        if (!response.ok) {
          setMessage('Could not analyze logs.');
          return;
        }
        const data = await response.json();
        setMessage(data.message || 'Analysis complete.');
        renderHistory(data.history || []);
      } catch (err) {
        console.error(err);
        setMessage('Something went wrong.');
      }
    });

    function bufferToBase64(buffer) {
      let binary = '';
      const bytes = new Uint8Array(buffer);
      const chunk = 0x8000;
      for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
      }
      return btoa(binary);
    }

    function renderHistory(history) {
      historyList.innerHTML = '';
      if (!history.length) {
        const empty = document.createElement('li');
        empty.textContent = 'No analyses yet.';
        empty.style.color = '#475569';
        historyList.appendChild(empty);
        return;
      }

      for (const entry of history) {
        const item = document.createElement('li');
        item.className = 'history-item';

        const meta = document.createElement('div');
        meta.className = 'history-meta';
        const timestamp = document.createElement('span');
        timestamp.textContent = entry.timestamp || '';
        const count = document.createElement('span');
        count.textContent = `${(entry.files || []).length} file(s)`;
        meta.append(timestamp, count);

        const files = document.createElement('div');
        files.className = 'history-files';
        files.textContent = (entry.files || []).join(', ');

        const summary = document.createElement('p');
        summary.className = 'history-summary';
        summary.textContent = entry.message || '';

        item.append(meta, files, summary);
        historyList.appendChild(item);
      }
    }

    renderHistory([]);
  </script>
</body>
</html>
"""


HISTORY_LIMIT = 20
_history: List[dict] = []


def _build_sources(payload: dict) -> Iterable[LogSource]:
    files: List[dict] = payload.get("files") or []
    if not isinstance(files, list):
        return []
    for item in files:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "uploaded.log")
        encoding = (item.get("encoding") or "text").lower()
        raw_content = item.get("content", "")

        if name.lower().endswith(".zip"):
            yield from _sources_from_zip(name, raw_content, encoding)
            continue

        if encoding == "base64":
            try:
                decoded = base64.b64decode(raw_content)
                content = decoded.decode("utf-8", errors="ignore")
            except Exception:
                content = ""
        else:
            content = str(raw_content)

        lines = content.splitlines()
        yield LogSource(name=name, lines=lines)


def _sources_from_zip(name: str, raw_content: str, encoding: str) -> Iterable[LogSource]:
    try:
        if encoding == "base64":
            content_bytes = base64.b64decode(raw_content)
        else:
            content_bytes = raw_content.encode("utf-8", errors="ignore")
    except Exception:
        return

    try:
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                suffix = Path(info.filename).suffix.lower()
                if suffix and suffix not in TEXT_SUFFIXES:
                    continue
                with archive.open(info) as file:
                    content = file.read().decode("utf-8", errors="ignore")
                lines = content.splitlines()
                yield LogSource(name=f"{name}:{info.filename}", lines=lines)
    except Exception:
        return


def _summarize(report: AnalysisReport) -> str:
    parts: List[str] = [f"Scanned {report.scanned_sources} source(s)."]
    if report.total_findings == 0:
        parts.append("No issues detected.")
        return " ".join(parts)

    parts.append(f"Found {report.total_findings} finding(s).")
    if report.totals_by_category:
        category_bits = ", ".join(
            f"{category}: {count}" for category, count in sorted(report.totals_by_category.items())
        )
        parts.append(f"By category: {category_bits}.")
    if report.top_messages:
        top_message, occurrences = report.top_messages[0]
        parts.append(f"Top message appeared {occurrences}x: {top_message[:180]}.")
    return " ".join(parts)


def _record_history(sources: List[LogSource], message: str) -> List[dict]:
    entry = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "files": [source.name for source in sources],
        "message": message,
    }
    _history.insert(0, entry)
    del _history[HISTORY_LIMIT:]
    return list(_history)


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(APP_HTML.encode("utf-8"))

    def do_POST(self):  # noqa: N802
        if self.path != "/analyze":
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return

        if not isinstance(payload, dict):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid payload")
            return

        files = payload.get("files")
        if files is not None and not isinstance(files, list):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid files payload")
            return

        sources = list(_build_sources(payload))

        report = analyze_logs(sources)
        message = _summarize(report)
        history = _record_history(sources, message)
        response = {"message": message, "history": history}

        encoded = json.dumps(response).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):  # noqa: A003
        return


class ReusableAppServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_app(host: str = "127.0.0.1", port: int = 8000) -> None:
    server_address = (host, port)
    with ReusableAppServer(server_address, AppHandler) as httpd:
        url = f"http://{host}:{port}"
        print(f"Serving Itay Logs Reviewer at {url}")
        try:
            webbrowser.open(url)
        except Exception:
            pass

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down app...")
