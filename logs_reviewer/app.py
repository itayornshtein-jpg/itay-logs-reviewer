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
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>Itay Logs Reviewer</title>
  <style>
    :root {
      color-scheme: light;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif;
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

    :root[data-theme=\"dark\"] {
      color-scheme: dark;
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
      max-width: 960px;
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
      flex-wrap: wrap;
    }

    .page-header button {
      background: none;
      border: 1px solid var(--border-color);
      color: var(--text-body);
      border-radius: 999px;
      padding: 0.5rem 1rem;
      cursor: pointer;
      font-weight: 600;
      transition: border-color 120ms ease-in-out, transform 120ms ease-in-out;
    }

    .page-header button:hover {
      border-color: var(--accent);
      transform: translateY(-1px);
    }

    h1 {
      margin: 0;
      font-size: 1.9rem;
      letter-spacing: -0.02em;
      color: var(--text-strong);
    }

    p {
      color: var(--text-body);
      line-height: 1.5;
    }

    .card-grid {
      display: grid;
      grid-template-columns: 1.1fr 0.9fr;
      gap: 1rem;
    }

    #results { display: none; grid-template-columns: 1fr 1fr; gap: 1rem; }
    #results.visible { display: grid; }

    .card,
    .panel {
      background: var(--card-bg);
      border-radius: 12px;
      padding: 1rem;
      box-shadow: var(--card-shadow);
      border: 1px solid var(--border-color);
      color: var(--text-body);
    }

    .panel h2,
    .card h2 {
      margin-top: 0;
      margin-bottom: 0.35rem;
      color: var(--text-strong);
    }

    #drop-zone {
      border: 2px dashed var(--drop-border);
      border-radius: 12px;
      padding: 2rem;
      text-align: center;
      background: var(--drop-bg);
      color: var(--drop-text);
      transition: all 150ms ease-in-out;
      cursor: pointer;
    }

    #drop-zone.hover {
      border-color: var(--drop-hover-border);
      background: var(--drop-hover-bg);
      box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.15);
    }

    .muted { color: var(--text-muted); }
    .error { color: var(--error); }

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

    .session-grid {
      display: grid;
      gap: 0.75rem;
    }

    .session-grid label { font-weight: 600; color: var(--text-strong); }

    .session-grid input[type=\"text\"] {
      padding: 0.65rem 0.75rem;
      border: 1px solid var(--input-border);
      border-radius: 10px;
      font-size: 1rem;
      background: var(--input-bg);
      color: var(--input-text);
    }

    .primary-btn {
      background: var(--accent);
      color: var(--card-bg);
      border: none;
      border-radius: 10px;
      padding: 0.75rem 1rem;
      font-size: 1rem;
      cursor: pointer;
      transition: background 120ms ease-in-out, transform 120ms ease-in-out;
    }

    .primary-btn:hover:not(:disabled) { background: var(--accent-hover); transform: translateY(-1px); }
    .primary-btn:disabled { background: var(--accent-disabled); cursor: not-allowed; }

    .list-reset { list-style: none; padding: 0; margin: 0; }

    .history-item { padding: 0.75rem; border: 1px solid var(--border-color); border-radius: 10px; background: var(--card-bg); }
    .history-meta { display: flex; justify-content: space-between; font-size: 0.9rem; color: var(--text-muted); }
    .history-files { margin: 0.3rem 0 0.2rem 0; color: var(--text-strong); font-weight: 600; font-size: 0.95rem; }

    .finding-line { border: 1px solid var(--border-color); border-radius: 10px; padding: 0.7rem; margin-bottom: 0.5rem; background: var(--panel-bg); box-shadow: var(--card-shadow); }
    .finding-meta { display: flex; justify-content: space-between; font-size: 0.9rem; color: var(--text-muted); }
    .finding-source { font-weight: 700; color: var(--text-strong); }
    .finding-category { background: var(--pill-bg); color: var(--pill-text); border-radius: 999px; padding: 0.15rem 0.55rem; }
    .finding-text { margin: 0.35rem 0 0 0; color: var(--text-strong); }

    .coralogix-grid { display: grid; gap: 0.75rem; }
    .coralogix-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 0.5rem; }
    .coralogix-row input, .coralogix-row select, .coralogix-row textarea { width: 100%; padding: 0.5rem 0.6rem; border-radius: 10px; border: 1px solid var(--input-border); background: var(--input-bg); color: var(--input-text); box-sizing: border-box; }
    .coralogix-row textarea { min-height: 120px; resize: vertical; }

    .coralogix-record { border: 1px solid var(--border-color); border-radius: 10px; padding: 0.75rem; background: var(--card-bg); box-shadow: var(--card-shadow); }
    .record-meta { display: flex; justify-content: space-between; font-size: 0.9rem; color: var(--text-muted); gap: 0.75rem; }
    .record-meta .timestamp { font-weight: 700; color: var(--text-strong); }
    .record-meta .severity { background: var(--pill-bg); color: var(--pill-text); border-radius: 999px; padding: 0.2rem 0.5rem; }
    .record-body { white-space: pre-wrap; margin: 0.4rem 0 0 0; }

    footer { margin-top: 1.5rem; border-top: 1px solid var(--footer-border); padding-top: 1rem; color: var(--text-muted); }
  </style>
</head>

<body>
  <main>
    <div id="root"></div>
  </main>

  <script>
    (() => {
      const root = document.getElementById('root');
      const ACCEPTED_TYPES = '.log,.txt,.out,.err,.zip';

      root.innerHTML = `
        <div class="page-header">
          <h1>Itay Logs Reviewer</h1>
          <button type="button" id="theme-toggle" aria-label="Toggle theme">Switch to dark theme</button>
        </div>

        <div class="card-grid">
          <section class="panel" aria-label="ChatGPT login">
            <h2>ChatGPT login</h2>
            <p>Connect with your ChatGPT SSO token to use your account resources while analyzing logs.</p>
            <form id="session-form" class="session-grid">
              <label for="sso-token">ChatGPT SSO token</label>
              <input
                id="sso-token"
                type="text"
                name="sso-token"
                placeholder="Enter token or leave blank to use CHATGPT_SSO_TOKEN"
                autocomplete="off"
              />
              <button class="primary-btn" type="submit" id="session-submit">Connect to ChatGPT</button>
              <p id="session-status" class="muted">Not connected.</p>
            </form>
          </section>

          <section class="card" aria-label="Upload logs">
            <div id="drop-zone" role="button" tabindex="0" aria-busy="false" aria-label="Drop logs or click to select">
              <input id="file-input" type="file" multiple accept="${ACCEPTED_TYPES}" style="display: none" />
              <p style="margin: 0; font-weight: 700">Drop your log files or click to select</p>
              <p class="muted" style="margin-bottom: 0.5rem">Nothing is uploaded anywhere—everything stays local to this app.</p>
              <p class="pill" id="drop-status">Idle</p>
              <p id="drop-message" style="margin: 0.35rem 0 0">Drop a file to get started.</p>
              <p class="muted" id="last-files" style="margin: 0.35rem 0 0"></p>
            </div>
          </section>
        </div>

        <section id="results" class="results-grid">
          <div class="card">
            <h2>Local summary</h2>
            <div id="local-summary" class="muted">Waiting for input.</div>
          </div>
          <div class="card">
            <h2>ChatGPT recommendations</h2>
            <div id="assistant-text" class="muted">No recommendations yet.</div>
          </div>
        </section>

        <section class="card" style="margin-top: 1rem">
          <h2>Findings</h2>
          <div id="findings-list" class="muted">No findings yet.</div>
        </section>

        <section class="card" style="margin-top: 1rem">
          <h2>History</h2>
          <ul id="history-list" class="list-reset muted"><li>No analyses yet.</li></ul>
        </section>

        <section class="panel" aria-label="Coralogix search">
          <h2>Coralogix search</h2>
          <div class="coralogix-grid">
            <div class="coralogix-row">
              <input type="datetime-local" id="cg-from" aria-label="From" />
              <input type="datetime-local" id="cg-to" aria-label="To" />
              <select id="cg-limit" aria-label="Limit">
                <option value="10">10 per page</option>
                <option value="20" selected>20 per page</option>
                <option value="50">50 per page</option>
                <option value="100">100 per page</option>
              </select>
            </div>
            <div class="coralogix-row">
              <textarea id="cg-query" placeholder="Query"></textarea>
            </div>
            <div class="coralogix-row">
              <input type="text" id="cg-api" placeholder="Optional API key" />
              <label style="display: flex; align-items: center; gap: 0.4rem">
                <input type="checkbox" id="cg-summary" />
                Use last summary in query
              </label>
              <button class="primary-btn" type="button" id="cg-search">Search Coralogix</button>
            </div>
            <p class="muted" id="cg-status">Select a timeframe and run a search.</p>
          </div>

          <div style="margin-top: 0.5rem">
            <p class="muted" id="cg-range" style="margin-bottom: 0">Showing 0-0 of 0 record(s)</p>
            <p class="muted" id="cg-page" style="margin-top: 0.2rem">Page 1 of 1</p>
            <div style="display: flex; gap: 0.5rem; margin-top: 0.35rem">
              <button type="button" class="page-header button" style="padding: 0.35rem 0.8rem" id="cg-prev" disabled>Prev</button>
              <button type="button" class="page-header button" style="padding: 0.35rem 0.8rem" id="cg-next" disabled>Next</button>
            </div>
          </div>

          <div id="coralogix-list" style="margin-top: 0.75rem">
            <p class="muted">No Coralogix results yet.</p>
          </div>
        </section>

        <footer>
          Drop your logs to see a quick summary of findings. Remote queries use Coralogix via your configured credentials.
        </footer>
      `;

      const bufferToBase64 = (buffer) => {
        let binary = '';
        const bytes = new Uint8Array(buffer);
        const chunk = 0x8000;
        for (let i = 0; i < bytes.length; i += chunk) {
          binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
        }
        return btoa(binary);
      };

      const formatLocalInput = (date) => {
        const pad = (value) => `${value}`.padStart(2, '0');
        return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
      };

      const defaultTimeframe = () => {
        const now = new Date();
        const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
        return { from: formatLocalInput(oneHourAgo), to: formatLocalInput(now) };
      };

      const dom = {
        themeToggle: document.getElementById('theme-toggle'),
        dropZone: document.getElementById('drop-zone'),
        fileInput: document.getElementById('file-input'),
        dropStatus: document.getElementById('drop-status'),
        dropMessage: document.getElementById('drop-message'),
        lastFiles: document.getElementById('last-files'),
        results: document.getElementById('results'),
        localSummary: document.getElementById('local-summary'),
        assistant: document.getElementById('assistant-text'),
        findings: document.getElementById('findings-list'),
        history: document.getElementById('history-list'),
        sessionForm: document.getElementById('session-form'),
        sessionToken: document.getElementById('sso-token'),
        sessionStatus: document.getElementById('session-status'),
        sessionSubmit: document.getElementById('session-submit'),
        cgFrom: document.getElementById('cg-from'),
        cgTo: document.getElementById('cg-to'),
        cgLimit: document.getElementById('cg-limit'),
        cgQuery: document.getElementById('cg-query'),
        cgApi: document.getElementById('cg-api'),
        cgSummary: document.getElementById('cg-summary'),
        cgSearch: document.getElementById('cg-search'),
        cgStatus: document.getElementById('cg-status'),
        cgRange: document.getElementById('cg-range'),
        cgPage: document.getElementById('cg-page'),
        cgPrev: document.getElementById('cg-prev'),
        cgNext: document.getElementById('cg-next'),
        cgList: document.getElementById('coralogix-list'),
      };

      const state = {
        theme: 'light',
        busy: false,
        message: 'Drop a file to get started.',
        assistant: '',
        assistantError: '',
        localSummary: null,
        findings: [],
        history: [],
        session: { connected: false, text: 'Not connected.' },
        coralogix: {
          query: '',
          from: defaultTimeframe().from,
          to: defaultTimeframe().to,
          limit: 20,
          results: [],
          hits: 0,
          page: 1,
          status: 'Select a timeframe and run a search.',
          useSummary: false,
          apiKey: '',
          loading: false,
        },
      };

      const applyTheme = (theme) => {
        document.documentElement.setAttribute('data-theme', theme);
        state.theme = theme;
        localStorage.setItem('theme', theme);
        dom.themeToggle.textContent = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
      };

      const initTheme = () => {
        const stored = localStorage.getItem('theme');
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        applyTheme(stored || (prefersDark ? 'dark' : 'light'));
      };

      const setBusy = (busy) => {
        state.busy = busy;
        dom.dropStatus.textContent = busy ? 'Analyzing…' : 'Idle';
        dom.dropZone.setAttribute('aria-busy', String(busy));
      };

      const setMessage = (text, isError = false) => {
        state.message = text || '';
        dom.dropMessage.textContent = state.message || 'Drop a file to get started.';
        dom.dropMessage.classList.toggle('error', isError);
      };

      const renderFindings = () => {
        if (!state.findings.length) {
          dom.findings.className = 'muted';
          dom.findings.textContent = 'No findings yet.';
          return;
        }
        dom.findings.className = '';
        dom.findings.innerHTML = state.findings
          .map(
            (finding) => `
              <div class="finding-line">
                <div class="finding-meta">
                  <span class="finding-source">${finding.source || 'unknown'}:${finding.line_no ?? '?'}</span>
                  <span class="finding-category">${finding.category || 'error'}</span>
                </div>
                <p class="finding-text">${finding.line || ''}</p>
              </div>
            `,
          )
          .join('');
      };

      const renderHistory = () => {
        if (!state.history.length) {
          dom.history.className = 'list-reset muted';
          dom.history.innerHTML = '<li>No analyses yet.</li>';
          return;
        }
        dom.history.className = 'list-reset';
        dom.history.innerHTML = state.history
          .map(
            (entry) => `
              <li class="history-item">
                <div class="history-meta">
                  <span>${entry.timestamp || ''}</span>
                  <span>${(entry.files || []).length} file(s)</span>
                </div>
                <div class="history-files">${(entry.files || []).join(', ')}</div>
                <p class="history-summary">${entry.message || ''}</p>
              </li>
            `,
          )
          .join('');
      };

      const renderSummary = () => {
        if (!state.localSummary) {
          dom.localSummary.className = 'muted';
          dom.localSummary.textContent = state.message || 'Waiting for input.';
          return;
        }

        const categories = Object.entries(state.localSummary.by_category || {});
        const repeats = state.localSummary.top_repeats || [];
        dom.localSummary.className = '';
        dom.localSummary.innerHTML = `
          <p><strong>${state.localSummary.scanned_sources}</strong> source(s) scanned. <strong>${state.localSummary.total_findings}</strong> finding(s) detected.</p>
          <div class="summary-grid">
            <div>
              <h3 style="margin-bottom: 0.3rem">By category</h3>
              ${
                categories.length
                  ? `<ul class="list-reset">${categories
                      .map(([category, count]) => `<li style="padding: 0.1rem 0"><strong>${count}</strong> ${category}</li>`)
                      .join('')}</ul>`
                  : '<p class="muted">No findings yet.</p>'
              }
            </div>
            <div>
              <h3 style="margin-bottom: 0.3rem">Top repeats</h3>
              ${
                repeats.length
                  ? `<ul class="list-reset">${repeats
                      .map((repeat) => `<li style="padding: 0.1rem 0"><strong>${repeat.count}×</strong> ${repeat.message}</li>`)
                      .join('')}</ul>`
                  : '<p class="muted">No repeats detected.</p>'
              }
            </div>
          </div>
        `;
      };

      const renderAssistant = () => {
        if (state.assistantError) {
          dom.assistant.className = 'error';
          dom.assistant.textContent = state.assistantError;
          return;
        }
        dom.assistant.className = state.assistant ? '' : 'muted';
        dom.assistant.textContent = state.assistant || 'No recommendations yet.';
      };

      const renderResults = () => {
        const shouldShow = Boolean(state.localSummary || state.assistant || state.message);
        dom.results.classList.toggle('visible', shouldShow);
        renderSummary();
        renderAssistant();
        renderFindings();
        renderHistory();
      };

      const renderCoralogix = () => {
        const { results, hits, page, limit } = state.coralogix;
        const totalPages = Math.max(1, Math.ceil(Math.max(results.length, 1) / limit));
        const startIndex = (page - 1) * limit;
        const slice = results.slice(startIndex, startIndex + limit);

        dom.cgRange.textContent = `Showing ${slice.length ? startIndex + 1 : 0}-${startIndex + slice.length} of ${hits || results.length} record(s)`;
        dom.cgPage.textContent = `Page ${page} of ${totalPages}${hits ? ` (${hits} total hit(s))` : ''}`;
        dom.cgPrev.disabled = page <= 1;
        dom.cgNext.disabled = page >= totalPages || !slice.length;
        dom.cgStatus.textContent = state.coralogix.status || '';
        dom.cgSearch.textContent = state.coralogix.loading ? 'Searching…' : 'Search Coralogix';
        dom.cgSearch.disabled = state.coralogix.loading;

        if (!slice.length) {
          dom.cgList.innerHTML = '<p class="muted">No Coralogix results yet.</p>';
          return;
        }

        dom.cgList.innerHTML = slice
          .map((record, idx) => {
            const timestamp = record.timestamp || record.time || record['@timestamp'] || 'timestamp unknown';
            const severity = record.severity || record.level || record.levelName || record.log_level;
            const body = record.text || record.message || record.msg || record.content || JSON.stringify(record, null, 2);
            return `
              <div class="coralogix-record" key="${timestamp}-${idx}">
                <div class="record-meta">
                  <span class="timestamp">${timestamp}</span>
                  ${severity ? `<span class="severity">${severity}</span>` : ''}
                </div>
                <pre class="record-body">${body}</pre>
              </div>
            `;
          })
          .join('');
      };

      const postJson = async (path, payload) => {
        const response = await fetch(path, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || response.statusText);
        }
        return response.json();
      };

      const handleLogin = async (token) => {
        dom.sessionSubmit.disabled = true;
        dom.sessionSubmit.textContent = 'Connecting…';
        try {
          const payload = await postJson('/chatgpt/login', { token });
          state.session = { connected: payload.connected, text: payload.text || 'Connected.' };
        } catch (error) {
          state.session = { connected: false, text: error.message || 'Failed to connect.' };
        } finally {
          dom.sessionSubmit.disabled = false;
          dom.sessionSubmit.textContent = 'Connect to ChatGPT';
          dom.sessionStatus.textContent = state.session.text;
          dom.sessionStatus.className = state.session.connected ? '' : 'muted';
        }
      };

      const loadSession = () => {
        fetch('/chatgpt/session')
          .then((res) => res.json())
          .then((payload) => {
            state.session = { connected: payload.connected, text: payload.text || 'Session state loaded.' };
            dom.sessionStatus.textContent = state.session.text;
            dom.sessionStatus.className = state.session.connected ? '' : 'muted';
          })
          .catch(() => {
            state.session = { connected: false, text: 'Unable to load session state.' };
            dom.sessionStatus.textContent = state.session.text;
            dom.sessionStatus.className = 'muted';
          });
      };

      const encodeFiles = async (files) =>
        Promise.all(
          files.map(async (file) => ({
            name: file.name,
            encoding: 'base64',
            content: bufferToBase64(await file.arrayBuffer()),
          })),
        );

      const analyzeFiles = async (fileList) => {
        if (!fileList.length) return;
        setBusy(true);
        setMessage('Analyzing files…');
        dom.lastFiles.textContent = `Last upload: ${fileList.map((file) => file.name).join(', ')}`;
        try {
          const encodedFiles = await encodeFiles(fileList);
          const payload = await postJson('/analyze', { files: encodedFiles });
          state.assistant = payload.assistant || '';
          state.assistantError = payload.assistant_error || '';
          state.localSummary = payload.local_summary || null;
          state.findings = state.localSummary?.findings || [];
          const entry = {
            timestamp: new Date().toLocaleString(),
            files: fileList.map((f) => f.name || 'uploaded'),
            message: payload.message,
          };
          state.history = [entry, ...state.history].slice(0, 20);
          setMessage(payload.message || 'Analysis complete.');
        } catch (error) {
          state.localSummary = null;
          state.assistant = '';
          state.assistantError = '';
          state.findings = [];
          setMessage(`Failed to analyze: ${error.message}`, true);
        } finally {
          setBusy(false);
          renderResults();
        }
      };

      const searchCoralogix = async () => {
        state.coralogix.loading = true;
        state.coralogix.status = 'Searching…';
        renderCoralogix();
        try {
          const payload = await postJson('/coralogix-search', {
            query: state.coralogix.query,
            timeframe: { from: state.coralogix.from, to: state.coralogix.to },
            pagination: { limit: state.coralogix.limit },
            use_last_summary: state.coralogix.useSummary,
            api_key: state.coralogix.apiKey,
          });
          state.coralogix.results = payload.records || [];
          state.coralogix.hits = payload.hits || 0;
          state.coralogix.page = 1;
          state.coralogix.status = payload.status || 'Search completed.';
        } catch (error) {
          state.coralogix.results = [];
          state.coralogix.hits = 0;
          state.coralogix.page = 1;
          state.coralogix.status = error.message || 'Search failed.';
        } finally {
          state.coralogix.loading = false;
          renderCoralogix();
        }
      };

      dom.themeToggle.addEventListener('click', () => {
        applyTheme(state.theme === 'dark' ? 'light' : 'dark');
      });

      dom.sessionForm.addEventListener('submit', (evt) => {
        evt.preventDefault();
        handleLogin(dom.sessionToken.value.trim());
      });

      const handleFileSelection = (files) => {
        if (!files.length) return;
        analyzeFiles(Array.from(files));
      };

      dom.fileInput.addEventListener('change', (evt) => {
        handleFileSelection(evt.target.files || []);
        evt.target.value = '';
      });

      dom.dropZone.addEventListener('click', () => dom.fileInput.click());
      dom.dropZone.addEventListener('keydown', (evt) => {
        if (evt.key === 'Enter' || evt.key === ' ') {
          evt.preventDefault();
          dom.fileInput.click();
        }
      });
      dom.dropZone.addEventListener('dragover', (evt) => {
        evt.preventDefault();
        dom.dropZone.classList.add('hover');
      });
      dom.dropZone.addEventListener('dragleave', (evt) => {
        evt.preventDefault();
        dom.dropZone.classList.remove('hover');
      });
      dom.dropZone.addEventListener('drop', (evt) => {
        evt.preventDefault();
        dom.dropZone.classList.remove('hover');
        handleFileSelection(evt.dataTransfer?.files || []);
      });

      dom.cgFrom.value = state.coralogix.from;
      dom.cgTo.value = state.coralogix.to;
      dom.cgLimit.value = String(state.coralogix.limit);

      dom.cgFrom.addEventListener('change', (e) => {
        state.coralogix.from = e.target.value;
      });
      dom.cgTo.addEventListener('change', (e) => {
        state.coralogix.to = e.target.value;
      });
      dom.cgLimit.addEventListener('change', (e) => {
        state.coralogix.limit = parseInt(e.target.value, 10) || 20;
        state.coralogix.page = 1;
        renderCoralogix();
      });
      dom.cgQuery.addEventListener('input', (e) => {
        state.coralogix.query = e.target.value;
      });
      dom.cgApi.addEventListener('input', (e) => {
        state.coralogix.apiKey = e.target.value;
      });
      dom.cgSummary.addEventListener('change', (e) => {
        state.coralogix.useSummary = e.target.checked;
      });
      dom.cgPrev.addEventListener('click', () => {
        state.coralogix.page = Math.max(1, state.coralogix.page - 1);
        renderCoralogix();
      });
      dom.cgNext.addEventListener('click', () => {
        const totalPages = Math.max(1, Math.ceil(Math.max(state.coralogix.results.length, 1) / state.coralogix.limit));
        state.coralogix.page = Math.min(totalPages, state.coralogix.page + 1);
        renderCoralogix();
      });
      dom.cgSearch.addEventListener('click', searchCoralogix);

      initTheme();
      loadSession();
      renderResults();
      renderCoralogix();
    })();
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

    error_entries = [
        {"source": finding.source, "line_no": finding.line_no, "line": finding.line}
        for finding in report.unique_errors
    ]

    return {
        "overview": _summarize(report),
        "resize_actions": resize_actions,
        "collector_tail": report.collector_tail[-5:],
        "agent_tail": report.agent_tail[-15:],
        "unique_errors": error_entries,
        "errors": error_entries,
    }


def _assistant_prompt(report: AnalysisReport) -> str:
    header = _summarize(report)
    if not report.findings:
        return "\n".join(
            [
                f"Local summary: {header}",
                "",
                "No explicit error patterns were found in the provided logs. Suggest a short list of health checks or preventative steps the user can take.",
            ]
        )

    sample = []
    for finding in report.findings[:8]:
        sample.append(
            f"{finding.source}:{finding.line_no} | {finding.category} | {finding.line[:240]}"
        )

    prompt_lines = [
        f"Local summary: {header}",
        "",
        "Here are representative log excerpts:",
    ]
    prompt_lines.extend("- " + line for line in sample)
    prompt_lines.extend(
        [
            "",
            "Provide 2-4 concise remediation recommendations tailored to these findings.",
        ]
    )

    return "\n".join(prompt_lines)


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
