"""Lightweight drag-and-drop web app for reviewing logs."""
from __future__ import annotations

import base64
import importlib
import importlib.util
import io
import json
import os
import textwrap
import webbrowser
import zipfile
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
    #output-line { margin-top: 1rem; font-weight: 600; color: #0f172a; min-height: 1.5rem; }
    #results { margin-top: 1.25rem; display: none; }
    .card { background: #f8fafc; border-radius: 12px; padding: 1rem; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08); margin-top: 0.75rem; }
    .card h2 { margin: 0 0 0.5rem; font-size: 1.15rem; }
    .muted { color: #475569; }
    .error { color: #b91c1c; }
    footer {
      margin-top: 1.5rem;
      color: #475569;
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
    <section id="results">
      <div class="card">
        <h2>Local summary</h2>
        <p id="summary" class="muted">Drop a file to get started.</p>
      </div>
      <div class="card">
        <h2>ChatGPT recommendations</h2>
        <p id="assistant" class="muted">Waiting for input.</p>
        <p id="assistant-error" class="error" style="display: none;"></p>
      </div>
    </section>
    <footer>
      Drop your logs to see a quick summary of findings. Nothing is uploaded anywhere—everything stays local to this app.
    </footer>
  </main>

  <script>
    const dropZone = document.getElementById('drop-zone');
    const outputLine = document.getElementById('output-line');
    const results = document.getElementById('results');
    const summary = document.getElementById('summary');
    const assistant = document.getElementById('assistant');
    const assistantError = document.getElementById('assistant-error');

    function setMessage(text) {
      outputLine.textContent = text;
    }

    function showResults() {
      results.style.display = 'block';
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
      assistant.textContent = 'Waiting for ChatGPT...';
      assistant.classList.add('muted');
      assistantError.style.display = 'none';
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
        summary.textContent = data.message || 'Analysis complete.';
        summary.classList.remove('muted');
        if (data.assistant) {
          assistant.textContent = data.assistant;
          assistant.classList.remove('muted');
        } else {
          assistant.textContent = data.assistant_error ? 'Unavailable.' : 'Waiting for input.';
          assistant.classList.add('muted');
        }

        if (data.assistant_error) {
          assistantError.textContent = data.assistant_error;
          assistantError.style.display = 'block';
        } else {
          assistantError.style.display = 'none';
        }

        setMessage('Analysis complete.');
        showResults();
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
  </script>
</body>
</html>
"""


def _build_sources(payload: dict) -> Iterable[LogSource]:
    files: List[dict] = payload.get("files") or []
    for item in files:
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


def _assistant_prompt(report: AnalysisReport) -> str:
    header = _summarize(report)
    if not report.findings:
        return textwrap.dedent(
            f"""
            Local summary: {header}

            No explicit error patterns were found in the provided logs. Suggest a short list of health checks or preventative steps the user can take.
            """
        ).strip()

    sample = []
    for finding in report.findings[:8]:
        sample.append(
            f"{finding.source}:{finding.line_no} | {finding.category} | {finding.line[:240]}"
        )

    return textwrap.dedent(
        f"""
        Local summary: {header}

        Here are representative log excerpts:
        {chr(10).join('- ' + line for line in sample)}

        Provide 2-4 concise remediation recommendations tailored to these findings.
        """
    ).strip()


def _assistant_error_from_exception(openai_module, exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "ChatGPT request timed out."

    auth_error = getattr(openai_module, "AuthenticationError", None)
    if auth_error and isinstance(exc, auth_error):
        return "ChatGPT request failed: invalid or missing API key."

    api_error = getattr(openai_module, "APIStatusError", None)
    if api_error and isinstance(exc, api_error):
        status_code = getattr(exc, "status_code", None)
        if status_code:
            return f"ChatGPT request failed (status {status_code})."

    message = str(exc)
    if len(message) > 360:
        message = message[:360] + "..."
    return f"ChatGPT request failed: {message or exc.__class__.__name__}."


def _call_chatgpt(report: AnalysisReport) -> tuple[str | None, str | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "Set OPENAI_API_KEY to enable ChatGPT recommendations."

    if importlib.util.find_spec("openai") is None:
        return None, "Install the 'openai' package to request ChatGPT recommendations."

    openai = importlib.import_module("openai")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    client = openai.OpenAI(api_key=api_key)
    prompt = _assistant_prompt(report)
    try:
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a helpful assistant that explains log issues and prioritizes actionable steps.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            timeout=12,
        )
        message = completion.choices[0].message.content or ""
        return message.strip(), None
    except Exception as exc:  # pragma: no cover - relies on networked API
        return None, _assistant_error_from_exception(openai, exc)


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

        sources = list(_build_sources(payload))
        report = analyze_logs(sources)
        message = _summarize(report)
        assistant, assistant_error = _call_chatgpt(report)
        response = {
            "message": message,
            "assistant": assistant,
            "assistant_error": assistant_error,
        }

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

