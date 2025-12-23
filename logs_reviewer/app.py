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
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Iterable, List

from .analyzer import AnalysisReport, analyze_logs
from .coralogix import CoralogixError, search_logs
from .reader import LogSource, TEXT_SUFFIXES
from .sso import ChatGPTSession, connect_chatgpt_via_sso


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
      --page-bg: radial-gradient(circle at 20% 20%, #f1f5f9, #cbd5e1);
      --panel-bg: rgba(255, 255, 255, 0.9);
      --panel-shadow: 0 12px 40px rgba(15, 23, 42, 0.15);
      --text-strong: #0f172a;
      --text-body: #1f2937;
      --text-muted: #475569;
      --border-color: #e2e8f0;
      --input-border: #c7d2fe;
      --input-bg: #fff;
      --input-text: #111827;
      --accent: #4f46e5;
      --accent-hover: #4338ca;
      --accent-disabled: #cbd5e1;
      --pill-bg: #e0f2fe;
      --pill-text: #075985;
      --drop-border: #334155;
      --drop-bg: #f8fafc;
      --drop-text: #1e293b;
      --drop-hover-bg: #eff6ff;
      --drop-hover-border: #2563eb;
      --card-bg: #f8fafc;
      --card-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
      --error: #b91c1c;
      --footer-border: #e2e8f0;
    }

    :root[data-theme="dark"] {
      --page-bg: radial-gradient(circle at 20% 20%, #0f172a, #1e293b);
      --panel-bg: rgba(15, 23, 42, 0.9);
      --panel-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
      --text-strong: #e2e8f0;
      --text-body: #cbd5e1;
      --text-muted: #94a3b8;
      --border-color: #1f2937;
      --input-border: #334155;
      --input-bg: #0f172a;
      --input-text: #e2e8f0;
      --accent: #8b5cf6;
      --accent-hover: #7c3aed;
      --accent-disabled: #475569;
      --pill-bg: #312e81;
      --pill-text: #c7d2fe;
      --drop-border: #475569;
      --drop-bg: #0f172a;
      --drop-text: #e2e8f0;
      --drop-hover-bg: #1e293b;
      --drop-hover-border: #60a5fa;
      --card-bg: #0f172a;
      --card-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
      --error: #fca5a5;
      --footer-border: #1f2937;
    }

    body {
      margin: 0;
      padding: 2rem;
      background: var(--page-bg);
      min-height: 100vh;
      box-sizing: border-box;
      color: var(--text-body);
    }
    main {
      max-width: 720px;
      margin: 0 auto;
      background: var(--panel-bg);
      padding: 1.5rem;
      border-radius: 16px;
      box-shadow: var(--panel-shadow);
      color: var(--text-body);
    }
    .page-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }
    .page-header button {
      background: none;
      border: 1px solid var(--border-color);
      color: var(--text-body);
      border-radius: 999px;
      padding: 0.4rem 0.9rem;
      cursor: pointer;
      font-weight: 600;
      transition: border-color 120ms ease-in-out, transform 120ms ease-in-out;
    }
    .page-header button:hover {
      border-color: var(--accent);
      transform: translateY(-1px);
    }
    p {
      color: var(--text-body);
      line-height: 1.5;
    }
    h1 {
      margin-top: 0;
      font-size: 1.8rem;
      letter-spacing: -0.02em;
      color: var(--text-strong);
    }
    #session-card {
      border: 1px solid var(--border-color);
      border-radius: 12px;
      background: linear-gradient(180deg, color-mix(in srgb, var(--panel-bg), transparent 10%), var(--panel-bg));
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 8px 24px rgba(79, 70, 229, 0.08);
    }
    #session-card h2 {
      margin: 0 0 0.5rem 0;
      font-size: 1.2rem;
      color: var(--text-strong);
    }
    #session-card form {
      display: grid;
      gap: 0.5rem;
      margin-top: 0.75rem;
    }
    #session-card label {
      font-weight: 600;
      color: var(--text-strong);
    }
    #session-card input[type="text"] {
      padding: 0.6rem 0.75rem;
      border: 1px solid var(--input-border);
      border-radius: 10px;
      font-size: 1rem;
      background: var(--input-bg);
      color: var(--input-text);
    }
    #session-card button {
      background: var(--accent);
      color: var(--card-bg);
      border: none;
      border-radius: 10px;
      padding: 0.7rem 1rem;
      font-size: 1rem;
      cursor: pointer;
      transition: background 120ms ease-in-out, transform 120ms ease-in-out;
    }
    #session-card button:disabled {
      background: var(--accent-disabled);
      cursor: not-allowed;
    }
    #session-card button:hover:not(:disabled) {
      background: var(--accent-hover);
      transform: translateY(-1px);
    }
    #session-status {
      margin: 0.25rem 0 0 0;
      color: var(--text-muted);
      font-size: 0.95rem;
    }
    .pill {
      display: inline-block;
      padding: 0.25rem 0.6rem;
      border-radius: 999px;
      background: var(--pill-bg);
      color: var(--pill-text);
      font-weight: 600;
      font-size: 0.9rem;
      margin-top: 0.25rem;
    }
    #drop-zone {
      border: 2px dashed var(--drop-border);
      border-radius: 12px;
      padding: 2rem;
      text-align: center;
      background: var(--drop-bg);
      color: var(--drop-text);
      transition: all 150ms ease-in-out;
    }
    #drop-zone.hover {
      border-color: var(--drop-hover-border);
      background: var(--drop-hover-bg);
      box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.15);
    }
    #output-line { margin-top: 1rem; font-weight: 600; color: var(--text-strong); min-height: 1.5rem; }
    #results { margin-top: 1.25rem; display: none; }
    .card { background: var(--card-bg); border-radius: 12px; padding: 1rem; box-shadow: var(--card-shadow); margin-top: 0.75rem; color: var(--text-body); }
    .muted { color: var(--text-muted); }
    .error { color: var(--error); }
    footer {
      margin-top: 1.5rem;
      border-top: 1px solid var(--footer-border);
      padding-top: 1rem;
      color: var(--text-muted);
    }
    #history h2 {
      margin: 0 0 0.5rem 0;
      font-size: 1.1rem;
      color: var(--text-strong);
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
      border: 1px solid var(--border-color);
      border-radius: 10px;
      background: var(--card-bg);
    }
    .history-meta {
      display: flex;
      justify-content: space-between;
      font-size: 0.9rem;
      color: var(--text-muted);
    }
    .history-files {
      margin: 0.3rem 0 0.2rem 0;
      color: var(--text-strong);
      font-weight: 600;
      font-size: 0.95rem;
    }
    .history-summary {
      margin: 0;
      color: var(--text-strong);
      font-size: 0.95rem;
    }
  </style>
</head>
<body>
  <main>
    <div class="page-header">
      <h1>Itay Logs Reviewer</h1>
      <button type="button" id="theme-toggle" aria-label="Toggle theme">Toggle theme</button>
    </div>
    <section id="session-card">
      <h2>ChatGPT login</h2>
      <p>Connect with your ChatGPT SSO token to use your account resources while analyzing logs.</p>
      <form id="login-form">
        <label for="sso-token">ChatGPT SSO token</label>
        <input id="sso-token" type="text" name="sso-token" placeholder="Enter token or leave blank to use CHATGPT_SSO_TOKEN" autocomplete="off" />
        <button type="submit" id="login-button">Connect to ChatGPT</button>
        <p id="session-status" class="muted">Not connected.</p>
      </form>
    </section>
    <div id="drop-zone">
      <p style="margin: 0; font-size: 1.1rem;">Drag one or more log files here</p>
      <small>Accepted: .log, .txt, .out, .err, and zip archives</small>
    </div>
    <div id="output-line"></div>
    <section id="results">
      <div class="card">
        <h2>Local summary</h2>
        <div id="summary" class="muted">Drop a file to get started.</div>
      </div>
      <div class="card">
        <h2>ChatGPT recommendations</h2>
        <p id="assistant" class="muted">Waiting for input.</p>
        <p id="assistant-error" class="error" style="display: none;"></p>
      </div>
    </section>
    <footer>
      Drop your logs to see a quick summary of findings. Nothing is uploaded anywhere—everything stays local to this app. Remote queries
      use Coralogix via your configured credentials.
    </footer>
  </main>

  <script>
    const dropZone = document.getElementById('drop-zone');
    const outputLine = document.getElementById('output-line');
    const results = document.getElementById('results');
    const summary = document.getElementById('summary');
    const assistant = document.getElementById('assistant');
    const assistantError = document.getElementById('assistant-error');
    const themeToggle = document.getElementById('theme-toggle');

    function applyTheme(theme) {
      const root = document.documentElement;
      const nextTheme = theme === 'dark' ? 'dark' : 'light';
      root.setAttribute('data-theme', nextTheme);
      localStorage.setItem('theme', nextTheme);
      if (themeToggle) {
        themeToggle.textContent = nextTheme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
        themeToggle.setAttribute('aria-pressed', nextTheme === 'dark');
      }
    }

    function initTheme() {
      const stored = localStorage.getItem('theme');
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(stored || (prefersDark ? 'dark' : 'light'));
    }

    if (themeToggle) {
      themeToggle.addEventListener('click', () => {
        const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
        applyTheme(current === 'dark' ? 'light' : 'dark');
      });
    }

    initTheme();

    function setMessage(text) {
      outputLine.textContent = text;
    }

    function renderLocalSummary(localSummary, fallbackText) {
      summary.innerHTML = '';

      if (!localSummary) {
        summary.textContent = fallbackText || 'Analysis complete.';
        summary.classList.remove('muted');
        return;
      }

      const fragment = document.createDocumentFragment();
      const addSection = (title, body) => {
        const section = document.createElement('div');
        section.style.marginTop = '0.75rem';
        const heading = document.createElement('h3');
        heading.textContent = title;
        heading.style.margin = '0 0 0.35rem 0';
        heading.style.fontSize = '1rem';
        heading.style.color = 'var(--text-strong)';
        section.append(heading);
        section.append(body);
        fragment.append(section);
      };

      if (localSummary.overview) {
        const overview = document.createElement('p');
        overview.textContent = localSummary.overview;
        overview.style.margin = '0 0 0.5rem 0';
        fragment.append(overview);
      }

      if (localSummary.resize_actions && localSummary.resize_actions.length) {
        const list = document.createElement('ul');
        list.style.margin = '0';
        for (const action of localSummary.resize_actions) {
          const item = document.createElement('li');
          const title = document.createElement('strong');
          title.textContent = action.uuid;
          item.append(title);
          if (action.entries && action.entries.length) {
            const inner = document.createElement('ul');
            for (const entry of action.entries) {
              const entryItem = document.createElement('li');
              entryItem.textContent = `${entry.status} (line ${entry.line_no}): ${entry.line}`;
              inner.append(entryItem);
            }
            item.append(inner);
          }
          list.append(item);
        }
        addSection('Resize actions (last 5 per UUID)', list);
      }

      const collectorLines = localSummary.collector_tail || [];
      const collectorBody = document.createElement('pre');
      collectorBody.textContent = collectorLines.length ? collectorLines.join('\n') : 'No collectorHC.log entries found.';
      collectorBody.style.whiteSpace = 'pre-wrap';
      collectorBody.style.margin = '0';
      addSection('collectorHC.log (last 5 lines)', collectorBody);

      const agentLines = localSummary.agent_tail || [];
      const agentBody = document.createElement('pre');
      agentBody.textContent = agentLines.length ? agentLines.join('\n') : 'No agent.log entries found.';
      agentBody.style.whiteSpace = 'pre-wrap';
      agentBody.style.margin = '0';
      addSection('agent.log (last 15 lines)', agentBody);

      const uniqueErrors = localSummary.unique_errors || [];
      const errorList = document.createElement('ul');
      errorList.style.margin = '0';
      if (uniqueErrors.length) {
        for (const finding of uniqueErrors) {
          const li = document.createElement('li');
          li.textContent = `${finding.source}:${finding.line_no} — ${finding.line}`;
          errorList.append(li);
        }
      } else {
        const empty = document.createElement('p');
        empty.textContent = 'No error patterns detected across logs.';
        empty.style.margin = '0';
        addSection('Unique errors', empty);
      }
      if (uniqueErrors.length) {
        addSection('Unique errors', errorList);
      }

      if (!fragment.children.length) {
        summary.textContent = fallbackText || 'Analysis complete.';
        summary.classList.remove('muted');
        return;
      }

      summary.append(fragment);
      summary.classList.remove('muted');
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
          renderFindings([]);
          return;
        }
        const data = await response.json();
        renderLocalSummary(data.local_summary, data.message);
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
        renderFindings([]);
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

    function formatLocalInput(date) {
      const pad = value => `${value}`.padStart(2, '0');
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    function setDefaultTimeframe() {
      const now = new Date();
      const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
      coralogixFrom.value = formatLocalInput(oneHourAgo);
      coralogixTo.value = formatLocalInput(now);
    }

    function setCoralogixLoading(isLoading) {
      coralogixButton.disabled = isLoading;
      coralogixButton.textContent = isLoading ? 'Searching…' : 'Search Coralogix';
      coralogixApiKey.disabled = isLoading;
    }

    function renderCoralogixResults() {
      const limit = parseInt(coralogixLimit.value, 10) || 20;
      const availableRecords = coralogixRecords.length;
      const totalRecords = coralogixHits || availableRecords;
      const totalPages = Math.max(1, Math.ceil(Math.max(availableRecords, 1) / limit));
      if (coralogixPage > totalPages) {
        coralogixPage = totalPages;
      }

      const startIndex = (coralogixPage - 1) * limit;
      const slice = coralogixRecords.slice(startIndex, startIndex + limit);

      coralogixList.innerHTML = '';
      if (!slice.length) {
        const empty = document.createElement('p');
        empty.textContent = 'No Coralogix results yet.';
        empty.style.color = 'var(--text-muted)';
        coralogixList.appendChild(empty);
      } else {
        const fragment = document.createDocumentFragment();
        for (const record of slice) {
          const item = document.createElement('div');
          item.className = 'coralogix-record';

          const meta = document.createElement('div');
          meta.className = 'record-meta';
          const timestamp = document.createElement('span');
          timestamp.className = 'timestamp';
          timestamp.textContent = record.timestamp || record.time || record['@timestamp'] || 'timestamp unknown';
          meta.append(timestamp);
          const severityValue = record.severity || record.level || record.levelName || record.log_level;
          if (severityValue) {
            const severity = document.createElement('span');
            severity.className = 'severity';
            severity.textContent = severityValue;
            meta.append(severity);
          }
          item.append(meta);

          const body = document.createElement('pre');
          const text = record.text || record.message || record.msg || record.content;
          body.textContent = text ? text : JSON.stringify(record, null, 2);
          item.append(body);
          fragment.appendChild(item);
        }
        coralogixList.appendChild(fragment);
      }

      const startDisplay = slice.length ? startIndex + 1 : 0;
      const endDisplay = startIndex + slice.length;
      coralogixCount.textContent = `Showing ${startDisplay}-${endDisplay} of ${totalRecords || 0} record(s)`;
      coralogixHitCount.textContent = coralogixHits ? `${coralogixHits} total hit(s)` : '';
      coralogixPageLabel.textContent = `Page ${coralogixPage} of ${totalPages}`;
      coralogixPrev.disabled = coralogixPage <= 1;
      coralogixNext.disabled = coralogixPage >= totalPages || !slice.length;
    }

    async function performCoralogixSearch(evt) {
      evt.preventDefault();
      if (!coralogixFrom.value || !coralogixTo.value) {
        coralogixStatus.textContent = 'Please select a start and end time.';
        return;
      }

      coralogixPage = 1;
      const limit = parseInt(coralogixLimit.value, 10) || 20;
      coralogixStatus.textContent = 'Searching Coralogix...';
      setCoralogixLoading(true);

      try {
        const payload = {
          query: coralogixQuery.value,
          timeframe: { from: coralogixFrom.value, to: coralogixTo.value },
          pagination: { limit, offset: 0 },
        };

        const apiKey = (coralogixApiKey.value || '').trim();
        if (apiKey) {
          payload.api_key = apiKey;
        }

        if (coralogixUseSummary.checked) {
          payload.use_last_summary = true;
        }

        const response = await fetch('/coralogix-search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || 'Coralogix search failed.');
        }

        const data = await response.json();
        coralogixRecords = Array.isArray(data.records) ? data.records : [];
        coralogixHits = Number.isFinite(Number(data.hits)) ? Number(data.hits) : coralogixRecords.length;
        coralogixStatus.textContent = data.message || 'Search complete.';
        renderCoralogixResults();
      } catch (err) {
        console.error(err);
        coralogixStatus.textContent = err.message || 'Coralogix search failed.';
        coralogixRecords = [];
        coralogixHits = 0;
        renderCoralogixResults();
      } finally {
        setCoralogixLoading(false);
      }
    }

    coralogixForm.addEventListener('submit', performCoralogixSearch);
    coralogixPrev.addEventListener('click', () => {
      if (coralogixPage <= 1) return;
      coralogixPage -= 1;
      renderCoralogixResults();
    });
    coralogixNext.addEventListener('click', () => {
      coralogixPage += 1;
      renderCoralogixResults();
    });
    coralogixLimit.addEventListener('change', () => {
      coralogixPage = 1;
      renderCoralogixResults();
    });

    function renderHistory(history) {
      historyList.innerHTML = '';
      if (!history.length) {
        const empty = document.createElement('li');
        empty.textContent = 'No analyses yet.';
        empty.style.color = 'var(--text-muted)';
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

    async function refreshSession() {
      try {
        const response = await fetch('/chatgpt/session');
        if (!response.ok) return;
        const data = await response.json();
        if (!data.connected) {
          sessionStatus.textContent = 'Not connected.';
          sessionStatus.className = '';
          return;
        }
        const badge = document.createElement('span');
        badge.className = 'pill';
        badge.textContent = data.account || 'ChatGPT account';
        sessionStatus.innerHTML = '';
        sessionStatus.append(badge);
        const details = document.createElement('div');
        details.textContent = data.resource_summary || 'Connected to ChatGPT.';
        details.style.marginTop = '0.35rem';
        sessionStatus.append(details);
      } catch (err) {
        console.error(err);
        sessionStatus.textContent = 'Could not load ChatGPT session status.';
      }
    }

    function renderFindings(findings) {
      findingsList.innerHTML = '';
      const hasFindings = Array.isArray(findings) && findings.length > 0;
      findingsEmpty.style.display = hasFindings ? 'none' : 'block';

      if (!hasFindings) {
        return;
      }

      const fragment = document.createDocumentFragment();
      for (const finding of findings) {
        const item = document.createElement('div');
        item.className = 'finding-line';

        const meta = document.createElement('div');
        meta.className = 'finding-meta';

        const source = document.createElement('span');
        source.className = 'finding-source';
        source.textContent = `${finding.source || 'unknown'}:${finding.line_no ?? '?'}`;

        const category = document.createElement('span');
        category.className = 'finding-category';
        category.textContent = finding.category || 'error';

        meta.append(source, category);

        const text = document.createElement('p');
        text.className = 'finding-text';
        text.textContent = finding.line || '';

        item.append(meta, text);
        fragment.appendChild(item);
      }

      findingsList.appendChild(fragment);
    }

    setDefaultTimeframe();
    renderCoralogixResults();
    renderFindings([]);
    renderHistory([]);
  </script>
</body>
</html>
"""


HISTORY_LIMIT = 20
_history: List[dict] = []
_chatgpt_session: ChatGPTSession | None = None


def _sanitize_query(value: str | None, *, max_length: int = 2000) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())[:max_length]


def _sanitize_timeframe(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("timeframe must be provided with 'from' and 'to' fields")

    start = payload.get("from")
    end = payload.get("to")
    if not start or not end:
        raise ValueError("timeframe must contain both 'from' and 'to'")

    return {"from": str(start)[:128], "to": str(end)[:128]}


def _sanitize_pagination(payload: dict | None) -> dict | None:
    if payload is None:
        return None

    if not isinstance(payload, dict):
        raise ValueError("pagination must be an object with limit/offset values")

    sanitized: dict = {}

    if "limit" in payload:
        try:
            limit = int(payload.get("limit"))
        except (TypeError, ValueError):
            raise ValueError("pagination limit must be a number") from None
        if limit <= 0:
            raise ValueError("pagination limit must be positive")
        sanitized["limit"] = min(limit, 200)

    if "offset" in payload:
        try:
            offset = int(payload.get("offset"))
        except (TypeError, ValueError):
            raise ValueError("pagination offset must be a number") from None
        sanitized["offset"] = max(offset, 0)

    if "page" in payload:
        try:
            page = int(payload.get("page"))
        except (TypeError, ValueError):
            raise ValueError("pagination page must be a number") from None
        if page <= 0:
            raise ValueError("pagination page must be positive")
        sanitized["page"] = page

    return sanitized or None


def _sanitize_api_key(value: str | None, *, max_length: int = 256) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError("api_key cannot be empty")

    return cleaned[:max_length]


def _record_history(sources: Iterable[LogSource], message: str) -> None:
    entry = {
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "files": [source.name for source in sources],
        "message": str(message),
    }
    _history.insert(0, entry)
    if len(_history) > HISTORY_LIMIT:
        del _history[HISTORY_LIMIT:]


def _session_payload() -> dict:
    if _chatgpt_session is None:
        return {"connected": False}

    return {
        "connected": True,
        "account": _chatgpt_session.account,
        "resource_summary": _chatgpt_session.resource_summary,
        "token_hint": _chatgpt_session.token_hint,
        "connected_at": _chatgpt_session.connected_at.isoformat(),
    }


def _connect_chatgpt(payload: dict) -> dict:
    token = None
    resources = None
    if isinstance(payload, dict):
        token = payload.get("token")
        resources = payload.get("resources")

    global _chatgpt_session
    _chatgpt_session = connect_chatgpt_via_sso(token, resources)
    return _session_payload()


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


def _perform_coralogix_search(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")

    timeframe = _sanitize_timeframe(payload.get("timeframe"))
    filters = payload.get("filters")
    pagination = _sanitize_pagination(payload.get("pagination"))

    query = _sanitize_query(payload.get("query"))
    if payload.get("use_last_summary") and _history:
        query = _history[0].get("message", query) or query

    api_key = _sanitize_api_key(payload.get("api_key"))
    timeout = payload.get("timeout", 10)
    try:
        timeout_value: int | float = float(timeout)
    except (TypeError, ValueError):
        raise ValueError("timeout must be numeric") from None

    return search_logs(
        query=query,
        timeframe=timeframe,
        filters=filters if filters else None,
        pagination=pagination,
        api_key=api_key,
        timeout=timeout_value,
    )


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


def _local_summary_payload(report: AnalysisReport) -> dict:
    resize_actions = []
    for uuid, entries in sorted(report.resize_actions.items()):
        resize_actions.append(
            {
                "uuid": uuid,
                "entries": [
                    {"line_no": entry.line_no, "status": entry.status, "line": entry.line}
                    for entry in entries[-5:]
                ],
            }
        )

    unique_errors = [
        {"source": finding.source, "line_no": finding.line_no, "line": finding.line}
        for finding in report.unique_errors
    ]

    return {
        "overview": _summarize(report),
        "resize_actions": resize_actions,
        "collector_tail": report.collector_tail[-5:],
        "agent_tail": report.agent_tail[-15:],
        "unique_errors": unique_errors,
    }


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


def _call_chatgpt(report: AnalysisReport) -> tuple[str | None, str | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "Set OPENAI_API_KEY to enable ChatGPT recommendations."

    if importlib.util.find_spec("openai") is None:
        return None, "Install the 'openai' package to request ChatGPT recommendations."

    openai = importlib.import_module("openai")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    prompt = _assistant_prompt(report)
    try:
        client_cls = getattr(openai, "OpenAI", None)
        if client_cls is None:
            return None, "Upgrade the 'openai' package (>=1.0) to request ChatGPT recommendations."

        client = client_cls(api_key=api_key)
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
        return None, f"ChatGPT request failed: {exc}"[:400]


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/chatgpt/session":
            payload = _session_payload()
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(APP_HTML.encode("utf-8"))

    def do_POST(self):  # noqa: N802
        if self.path not in {"/analyze", "/chatgpt/login", "/coralogix-search"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid JSON")
            return

        if self.path == "/chatgpt/login":
            try:
                payload = _connect_chatgpt(payload)
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return

            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        if self.path == "/coralogix-search":
            try:
                result = _perform_coralogix_search(payload)
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            except CoralogixError as exc:
                self.send_error(HTTPStatus.BAD_GATEWAY, str(exc))
                return

            encoded = json.dumps(result).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        sources = list(_build_sources(payload))
        report = analyze_logs(sources)
        message = _summarize(report)
        _record_history(sources, message)
        assistant, assistant_error = _call_chatgpt(report)
        response = {
            "message": message,
            "assistant": assistant,
            "assistant_error": assistant_error,
            "local_summary": _local_summary_payload(report),
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
