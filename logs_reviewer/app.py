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
    p {
      color: #1f2937;
      line-height: 1.5;
    }
    h1 {
      margin-top: 0;
      font-size: 1.8rem;
      letter-spacing: -0.02em;
    }
    #session-card {
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      background: linear-gradient(180deg, #eef2ff, #fff);
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 8px 24px rgba(79, 70, 229, 0.08);
    }
    #session-card h2 {
      margin: 0 0 0.5rem 0;
      font-size: 1.2rem;
      color: #312e81;
    }
    #session-card form {
      display: grid;
      gap: 0.5rem;
      margin-top: 0.75rem;
    }
    #session-card label {
      font-weight: 600;
      color: #111827;
    }
    #session-card input[type="text"] {
      padding: 0.6rem 0.75rem;
      border: 1px solid #c7d2fe;
      border-radius: 10px;
      font-size: 1rem;
      background: #fff;
      color: #111827;
    }
    #session-card button {
      background: #4f46e5;
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 0.7rem 1rem;
      font-size: 1rem;
      cursor: pointer;
      transition: background 120ms ease-in-out, transform 120ms ease-in-out;
    }
    #session-card button:disabled {
      background: #cbd5e1;
      cursor: not-allowed;
    }
    #session-card button:hover:not(:disabled) {
      background: #4338ca;
      transform: translateY(-1px);
    }
    #session-status {
      margin: 0.25rem 0 0 0;
      color: #334155;
      font-size: 0.95rem;
    }
    .pill {
      display: inline-block;
      padding: 0.25rem 0.6rem;
      border-radius: 999px;
      background: #e0f2fe;
      color: #075985;
      font-weight: 600;
      font-size: 0.9rem;
      margin-top: 0.25rem;
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
    #results {
      margin-top: 1.5rem;
      border-top: 1px solid #e2e8f0;
      padding-top: 1rem;
    }
    #results h2 {
      margin: 0 0 0.5rem 0;
      font-size: 1.1rem;
      color: #0f172a;
    }
    #findings-box {
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      background: #0b1224;
      color: #e2e8f0;
      padding: 1rem;
      min-height: 140px;
      max-height: 320px;
      overflow: auto;
      box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.1);
    }
    .finding-line {
      margin: 0.1rem 0;
      font-family: "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 0.9rem;
      line-height: 1.3;
      padding: 0.35rem 0.4rem;
      border-radius: 6px;
      background: rgba(255, 255, 255, 0.04);
      display: grid;
      gap: 0.25rem;
    }
    .finding-meta {
      display: flex;
      gap: 0.4rem;
      color: #cbd5e1;
      font-size: 0.85rem;
    }
    .finding-source {
      font-weight: 700;
      color: #bfdbfe;
    }
    .finding-category {
      padding: 0.05rem 0.45rem;
      border-radius: 999px;
      background: #fef3c7;
      color: #854d0e;
      font-weight: 700;
      font-size: 0.8rem;
    }
    .finding-text {
      margin: 0;
      color: #e2e8f0;
      white-space: pre-wrap;
      word-break: break-word;
    }
    #coralogix {
      margin-top: 1.5rem;
      border-top: 1px solid #e2e8f0;
      padding-top: 1.25rem;
    }
    #coralogix h2 {
      margin: 0 0 0.5rem 0;
      font-size: 1.1rem;
      color: #0f172a;
    }
    #coralogix p.description {
      margin-top: 0;
      color: #475569;
    }
    #coralogix form {
      display: grid;
      gap: 0.6rem;
      margin-top: 0.5rem;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 1rem;
    }
    #coralogix form label {
      font-weight: 600;
      color: #111827;
    }
    #coralogix .field-row {
      display: grid;
      gap: 0.5rem;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }
    #coralogix input[type="text"],
    #coralogix input[type="password"],
    #coralogix input[type="datetime-local"],
    #coralogix select {
      padding: 0.6rem 0.75rem;
      border: 1px solid #cbd5e1;
      border-radius: 10px;
      font-size: 1rem;
      background: #fff;
      color: #0f172a;
      width: 100%;
      box-sizing: border-box;
    }
    #coralogix button {
      justify-self: start;
      background: #0ea5e9;
      color: #fff;
      border: none;
      border-radius: 10px;
      padding: 0.7rem 1rem;
      font-size: 1rem;
      cursor: pointer;
      transition: background 120ms ease-in-out, transform 120ms ease-in-out;
    }
    #coralogix button:disabled {
      background: #bae6fd;
      cursor: not-allowed;
    }
    #coralogix button:hover:not(:disabled) {
      background: #0284c7;
      transform: translateY(-1px);
    }
    #coralogix-status {
      margin: 0;
      color: #0f172a;
    }
    #coralogix-results {
      margin-top: 0.75rem;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 0.85rem;
      background: #fff;
    }
    #coralogix-meta {
      display: flex;
      justify-content: space-between;
      align-items: center;
      color: #475569;
      font-size: 0.95rem;
      margin-bottom: 0.5rem;
      gap: 0.5rem;
    }
    #coralogix-list {
      display: grid;
      gap: 0.6rem;
    }
    .coralogix-record {
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 0.65rem 0.75rem;
      background: linear-gradient(180deg, #0b1224, #0f172a);
      color: #e2e8f0;
    }
    .coralogix-record .record-meta {
      display: flex;
      gap: 0.35rem;
      align-items: center;
      margin-bottom: 0.35rem;
      font-size: 0.9rem;
      color: #cbd5e1;
    }
    .record-meta .timestamp {
      font-weight: 700;
      color: #bfdbfe;
    }
    .record-meta .severity {
      padding: 0.05rem 0.45rem;
      border-radius: 999px;
      background: #fef08a;
      color: #854d0e;
      font-weight: 700;
      font-size: 0.8rem;
    }
    .coralogix-record pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: "SFMono-Regular", Menlo, Consolas, "Liberation Mono", monospace;
      font-size: 0.9rem;
    }
    #coralogix-pagination {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 0.75rem;
      gap: 0.75rem;
      flex-wrap: wrap;
    }
    #coralogix-pagination button {
      background: #475569;
      color: #fff;
      padding: 0.5rem 0.8rem;
      border-radius: 10px;
      border: none;
      cursor: pointer;
      transition: opacity 120ms ease-in-out;
    }
    #coralogix-pagination button:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    #coralogix-pagination .page-summary {
      color: #475569;
      font-size: 0.95rem;
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
      <h2>Detected error lines</h2>
      <div id="findings-box">
        <p id="findings-empty" style="margin: 0; color: #cbd5e1;">Drop logs to see detected errors.</p>
        <div id="findings-list"></div>
      </div>
    </section>
    <section id="coralogix">
      <h2>Search Coralogix</h2>
      <p class="description">Query your centralized logs remotely using your configured Coralogix credentials or a key you provide below (kept only in this session).</p>
      <form id="coralogix-form">
        <label for="coralogix-api-key">Coralogix API key</label>
        <input id="coralogix-api-key" type="password" name="api-key" placeholder="Paste your Coralogix API key" autocomplete="off" />
        <label for="coralogix-query">Search query</label>
        <input id="coralogix-query" type="text" name="query" placeholder="service:error OR exception" autocomplete="off" />
        <div class="field-row">
          <div>
            <label for="coralogix-from">From</label>
            <input id="coralogix-from" type="datetime-local" name="from" />
          </div>
          <div>
            <label for="coralogix-to">To</label>
            <input id="coralogix-to" type="datetime-local" name="to" />
          </div>
        </div>
        <div class="field-row">
          <div>
            <label for="coralogix-limit">Results per page</label>
            <select id="coralogix-limit" name="limit">
              <option value="10">10</option>
              <option value="20" selected>20</option>
              <option value="50">50</option>
            </select>
          </div>
          <label style="align-self: end; display: flex; gap: 0.35rem; align-items: center;">
            <input id="coralogix-use-summary" type="checkbox" />
            Use last summary when query is empty
          </label>
        </div>
        <button type="submit" id="coralogix-button">Search Coralogix</button>
        <p id="coralogix-status">Enter a query and timeframe to search.</p>
      </form>
      <div id="coralogix-results">
        <div id="coralogix-meta">
          <span id="coralogix-count">No results yet.</span>
          <span id="coralogix-hit-count"></span>
        </div>
        <div id="coralogix-list"></div>
        <div id="coralogix-pagination">
          <button type="button" id="coralogix-prev">Previous</button>
          <span class="page-summary" id="coralogix-page"></span>
          <button type="button" id="coralogix-next">Next</button>
        </div>
      </div>
    </section>
    <section id="history">
      <h2>Recent analyses</h2>
      <ul id="history-list"></ul>
    </section>
    <footer>
      Drop your logs to see a quick summary of findings. Nothing is uploaded anywhere—everything stays local to this app. Remote queries
      use Coralogix via your configured credentials.
    </footer>
  </main>

  <script>
    const dropZone = document.getElementById('drop-zone');
    const outputLine = document.getElementById('output-line');
    const findingsList = document.getElementById('findings-list');
    const findingsEmpty = document.getElementById('findings-empty');
    const historyList = document.getElementById('history-list');
    const loginForm = document.getElementById('login-form');
    const loginButton = document.getElementById('login-button');
    const ssoToken = document.getElementById('sso-token');
    const sessionStatus = document.getElementById('session-status');
    const coralogixForm = document.getElementById('coralogix-form');
    const coralogixApiKey = document.getElementById('coralogix-api-key');
    const coralogixQuery = document.getElementById('coralogix-query');
    const coralogixFrom = document.getElementById('coralogix-from');
    const coralogixTo = document.getElementById('coralogix-to');
    const coralogixLimit = document.getElementById('coralogix-limit');
    const coralogixUseSummary = document.getElementById('coralogix-use-summary');
    const coralogixStatus = document.getElementById('coralogix-status');
    const coralogixList = document.getElementById('coralogix-list');
    const coralogixCount = document.getElementById('coralogix-count');
    const coralogixHitCount = document.getElementById('coralogix-hit-count');
    const coralogixPageLabel = document.getElementById('coralogix-page');
    const coralogixPrev = document.getElementById('coralogix-prev');
    const coralogixNext = document.getElementById('coralogix-next');
    const coralogixButton = document.getElementById('coralogix-button');

    let coralogixRecords = [];
    let coralogixHits = 0;
    let coralogixPage = 1;

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
        setMessage(data.message || 'Analysis complete.');
        renderFindings(data.findings || []);
        renderHistory(data.history || []);
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
        empty.style.color = '#475569';
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


def _sanitize_bool(value: bool | str | None) -> bool | None:
    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False

    raise ValueError("verify_tls must be a boolean value if provided")


def _sanitize_ca_bundle(value: str | None, *, max_length: int = 512) -> str | None:
    if value is None:
        return None

    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError("ca_bundle cannot be empty")

    return cleaned[:max_length]


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


def _session_payload() -> dict:
    if not _chatgpt_session:
        return {"connected": False}

    return {
        "connected": True,
        "account": _chatgpt_session.account,
        "resource_summary": _chatgpt_session.resource_summary,
        "token_hint": _chatgpt_session.token_hint,
        "connected_at": _chatgpt_session.connected_at.isoformat(timespec="seconds") + "Z",
    }


def _connect_chatgpt(payload: dict | None) -> dict:
    if payload is None or not isinstance(payload, dict):
        raise ValueError("Invalid payload")

    token = payload.get("token")
    resources = payload.get("resources") if isinstance(payload.get("resources"), dict) else None

    session = connect_chatgpt_via_sso(token=token, resources=resources)
    global _chatgpt_session
    _chatgpt_session = session

    response = _session_payload()
    response["message"] = f"Connected to ChatGPT as {session.account}"
    return response


def _perform_coralogix_search(payload: dict | None) -> dict:
    if payload is None or not isinstance(payload, dict):
        raise ValueError("Invalid payload")

    timeframe = _sanitize_timeframe(payload.get("timeframe"))
    query = _sanitize_query(payload.get("query"))
    pagination = _sanitize_pagination(payload.get("pagination"))
    api_key = _sanitize_api_key(payload.get("api_key"))
    verify_tls = _sanitize_bool(payload.get("verify_tls"))
    ca_bundle = _sanitize_ca_bundle(payload.get("ca_bundle"))

    if not query and payload.get("use_last_summary") and _history:
        query = _sanitize_query(_history[0].get("message"))

    if not query:
        raise ValueError("query is required for Coralogix search")

    filters = payload.get("filters")
    if filters is not None and not isinstance(filters, dict):
        raise ValueError("filters must be an object if provided")

    return search_logs(
        query=query,
        timeframe=timeframe,
        filters=filters,
        pagination=pagination,
        api_key=api_key,
        verify=verify_tls,
        ca_bundle=ca_bundle,
    )


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

        if not isinstance(payload, dict):
            self.send_error(HTTPStatus.BAD_REQUEST, "Invalid payload")
            return

        if self.path == "/chatgpt/login":
            try:
                response = _connect_chatgpt(payload)
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return

            encoded = json.dumps(response).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        if self.path == "/coralogix-search":
            try:
                response = _perform_coralogix_search(payload)
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            except CoralogixError as exc:
                self.send_error(HTTPStatus.BAD_GATEWAY, str(exc))
                return
        else:
            files = payload.get("files")
            if files is not None and not isinstance(files, list):
                self.send_error(HTTPStatus.BAD_REQUEST, "Invalid files payload")
                return

            sources = list(_build_sources(payload))

            report = analyze_logs(sources)
            message = _summarize(report)
            history = _record_history(sources, message)
            findings = [
                {
                    "source": finding.source,
                    "line_no": finding.line_no,
                    "line": finding.line,
                    "category": finding.category,
                    "suggestion": finding.suggestion,
                }
                for finding in report.findings[:200]
            ]
            response = {"message": message, "history": history, "findings": findings}

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
