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
    <div id=\"root\"></div>
  </main>

  <script crossorigin src=\"https://unpkg.com/react@18/umd/react.production.min.js\"></script>
  <script crossorigin src=\"https://unpkg.com/react-dom@18/umd/react-dom.production.min.js\"></script>
  <script src=\"https://unpkg.com/@babel/standalone/babel.min.js\"></script>
  <script type=\"text/babel\">
    const { useEffect, useMemo, useRef, useState } = React;
    const ACCEPTED_TYPES = '.log,.txt,.out,.err,.zip';

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

    const ThemeToggle = ({ theme, onToggle }) => (
      <button type=\"button\" onClick={onToggle} aria-label=\"Toggle theme\">
        {theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      </button>
    );

    const SessionCard = ({ onLogin, sessionInfo, loading }) => {
      const [token, setToken] = useState('');

      const handleSubmit = async (evt) => {
        evt.preventDefault();
        await onLogin(token);
      };

      return (
        <section className=\"panel\" aria-label=\"ChatGPT login\">
          <h2>ChatGPT login</h2>
          <p>Connect with your ChatGPT SSO token to use your account resources while analyzing logs.</p>
          <form onSubmit={handleSubmit} className=\"session-grid\">
            <label htmlFor=\"sso-token\">ChatGPT SSO token</label>
            <input
              id=\"sso-token\"
              type=\"text\"
              name=\"sso-token\"
              placeholder=\"Enter token or leave blank to use CHATGPT_SSO_TOKEN\"
              autoComplete=\"off\"
              value={token}
              onChange={(e) => setToken(e.target.value)}
            />
            <button className=\"primary-btn\" type=\"submit\" disabled={loading}>
              {loading ? 'Connecting…' : 'Connect to ChatGPT'}
            </button>
            <p className={sessionInfo.connected ? '' : 'muted'}>{sessionInfo.text}</p>
          </form>
        </section>
      );
    };

    const DropZone = ({ onFiles, busy, helperText, message }) => {
      const [hover, setHover] = useState(false);
      const fileInput = useRef(null);
      const [lastFiles, setLastFiles] = useState([]);

      const handleFiles = (files) => {
        if (!files.length) return;
        setLastFiles(files.map((file) => file.name));
        onFiles(files);
      };

      const onDrop = (evt) => {
        evt.preventDefault();
        setHover(false);
        const files = Array.from(evt.dataTransfer?.files || []);
        handleFiles(files);
      };

      const onClick = (evt) => {
        evt.preventDefault();
        fileInput.current?.click();
      };

      const onKeyDown = (evt) => {
        if (evt.key === 'Enter' || evt.key === ' ') {
          evt.preventDefault();
          fileInput.current?.click();
        }
      };

      return (
        <div className=\"panel\">
          <div
            id=\"drop-zone\"
            role=\"button\"
            tabIndex={0}
            aria-label=\"Select or drop log files\"
            className={hover ? 'hover' : ''}
            onDragEnter={(e) => { e.preventDefault(); setHover(true); }}
            onDragOver={(e) => { e.preventDefault(); setHover(true); }}
            onDragLeave={(e) => { e.preventDefault(); setHover(false); }}
            onDrop={onDrop}
            onClick={onClick}
            onKeyDown={onKeyDown}
          >
            <p style={{ margin: 0, fontSize: '1.1rem' }}>Drag one or more log files here</p>
            <small>Accepted: .log, .txt, .out, .err, and zip archives. Click to choose files.</small>
            <input
              ref={fileInput}
              id=\"file-input\"
              type=\"file\"
              multiple
              accept={ACCEPTED_TYPES}
              style={{ display: 'none' }}
              onChange={(e) => {
                const files = Array.from(e.target.files || []);
                handleFiles(files);
                e.target.value = '';
              }}
            />
          </div>
          <div id=\"output-line\" style={{ marginTop: '0.75rem', fontWeight: 600 }}>
            {busy ? 'Processing logs…' : message || 'Drop a file to get started.'}
          </div>
          {!!lastFiles.length && (
            <p className=\"muted\" style={{ marginTop: '0.35rem' }}>
              Last selected: {lastFiles.join(', ')}
            </p>
          )}
          <p className=\"muted\" style={{ marginTop: '0.35rem', fontSize: '0.9rem' }}>{helperText}</p>
        </div>
      );
    };

    const SummarySection = ({ localSummary, fallbackText }) => {
      if (!localSummary) {
        return <p className=\"muted\">{fallbackText || 'Drop a file to get started.'}</p>;
      }

      const sections = [];

      if (localSummary.overview) {
        sections.push(
          <p key=\"overview\" style={{ margin: '0 0 0.5rem 0' }}>
            {localSummary.overview}
          </p>
        );
      }

      if (localSummary.resize_actions?.length) {
        sections.push(
          <div key=\"resize\" style={{ marginTop: '0.75rem' }}>
            <h3 style={{ margin: '0 0 0.35rem 0', fontSize: '1rem', color: 'var(--text-strong)' }}>
              Resize actions (last 5 per UUID)
            </h3>
            <ul style={{ margin: 0 }}>
              {localSummary.resize_actions.map((action) => (
                <li key={action.uuid}>
                  <strong>{action.uuid}</strong>
                  {action.entries?.length ? (
                    <ul>
                      {action.entries.map((entry, idx) => (
                        <li key={`${action.uuid}-${idx}`}>
                          {entry.status} (line {entry.line_no}): {entry.line}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        );
      }

      const tailSection = (title, lines, id) => (
        <div key={id} style={{ marginTop: '0.75rem' }}>
          <h3 style={{ margin: '0 0 0.35rem 0', fontSize: '1rem', color: 'var(--text-strong)' }}>{title}</h3>
          <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{(lines || []).length ? lines.join('\n') : 'No entries found.'}</pre>
        </div>
      );

      sections.push(tailSection('collectorHC.log (last 5 lines)', localSummary.collector_tail || [], 'collector'));
      sections.push(tailSection('agent.log (last 15 lines)', localSummary.agent_tail || [], 'agent'));

      const errors = localSummary.errors || localSummary.unique_errors || [];
      sections.push(
        <div key=\"errors\" style={{ marginTop: '0.75rem' }}>
          <h3 style={{ margin: '0 0 0.35rem 0', fontSize: '1rem', color: 'var(--text-strong)' }}>Errors</h3>
          {errors.length ? (
            <ul style={{ margin: 0 }}>
              {errors.map((finding, idx) => (
                <li key={`${finding.source}-${finding.line_no}-${idx}`}>
                  {finding.source}:{finding.line_no} — {finding.line}
                </li>
              ))}
            </ul>
          ) : (
            <p style={{ margin: 0 }}>No error patterns detected across logs.</p>
          )}
        </div>
      );

      return <>{sections}</>;
    };

    const AssistantSection = ({ text, error }) => (
      <div>
        <p className={!text ? 'muted' : ''}>{text || 'Waiting for input.'}</p>
        {error ? <p className=\"error\" style={{ margin: 0 }}>{error}</p> : null}
      </div>
    );

    const FindingsList = ({ findings }) => {
      const hasFindings = Array.isArray(findings) && findings.length > 0;
      if (!hasFindings) {
        return <p className=\"muted\" id=\"findings-empty\">No findings yet.</p>;
      }
      return (
        <div id=\"findings-list\">
          {findings.map((finding, idx) => (
            <div key={`${finding.source}-${finding.line_no}-${idx}`} className=\"finding-line\">
              <div className=\"finding-meta\">
                <span className=\"finding-source\">{`${finding.source || 'unknown'}:${finding.line_no ?? '?'}`}</span>
                <span className=\"finding-category\">{finding.category || 'error'}</span>
              </div>
              <p className=\"finding-text\">{finding.line || ''}</p>
            </div>
          ))}
        </div>
      );
    };

    const HistoryList = ({ history }) => {
      if (!history.length) {
        return <p className=\"muted\">No analyses yet.</p>;
      }
      return (
        <ul id=\"history-list\" className=\"list-reset\">
          {history.map((entry, idx) => (
            <li className=\"history-item\" key={`${entry.timestamp}-${idx}`}>
              <div className=\"history-meta\">
                <span>{entry.timestamp || ''}</span>
                <span>{(entry.files || []).length} file(s)</span>
              </div>
              <div className=\"history-files\">{(entry.files || []).join(', ')}</div>
              <p className=\"history-summary\">{entry.message || ''}</p>
            </li>
          ))}
        </ul>
      );
    };

    const CoralogixPanel = ({ onSearch, state, setState }) => {
      const { query, from, to, limit, results, hits, page, status, useSummary, apiKey, loading } = state;

      const totalPages = Math.max(1, Math.ceil(Math.max(results.length, 1) / limit));
      const startIndex = (page - 1) * limit;
      const slice = results.slice(startIndex, startIndex + limit);

      const updateField = (key, value) => setState((prev) => ({ ...prev, [key]: value }));

      return (
        <section className=\"panel\" aria-label=\"Coralogix search\">
          <h2>Coralogix search</h2>
          <div className=\"coralogix-grid\">
            <div className=\"coralogix-row\">
              <input type=\"datetime-local\" value={from} onChange={(e) => updateField('from', e.target.value)} aria-label=\"From\" />
              <input type=\"datetime-local\" value={to} onChange={(e) => updateField('to', e.target.value)} aria-label=\"To\" />
              <select value={limit} onChange={(e) => updateField('limit', parseInt(e.target.value, 10) || 20)} aria-label=\"Limit\">
                {[10, 20, 50, 100].map((value) => (
                  <option key={value} value={value}>{value} per page</option>
                ))}
              </select>
            </div>
            <div className=\"coralogix-row\">
              <textarea placeholder=\"Query\" value={query} onChange={(e) => updateField('query', e.target.value)} />
            </div>
            <div className=\"coralogix-row\">
              <input type=\"text\" placeholder=\"Optional API key\" value={apiKey} onChange={(e) => updateField('apiKey', e.target.value)} />
              <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                <input type=\"checkbox\" checked={useSummary} onChange={(e) => updateField('useSummary', e.target.checked)} />
                Use last summary in query
              </label>
              <button className=\"primary-btn\" type=\"button\" onClick={onSearch} disabled={loading}>
                {loading ? 'Searching…' : 'Search Coralogix'}
              </button>
            </div>
            <p className=\"muted\">{status}</p>
          </div>

          <div style={{ marginTop: '0.5rem' }}>
            <p className=\"muted\" style={{ marginBottom: 0 }}>
              Showing {slice.length ? startIndex + 1 : 0}-{startIndex + slice.length} of {hits || results.length} record(s)
            </p>
            <p className=\"muted\" style={{ marginTop: '0.2rem' }}>
              Page {page} of {totalPages} {hits ? `(${hits} total hit(s))` : ''}
            </p>
            <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.35rem' }}>
              <button type=\"button\" className=\"page-header button\" style={{ padding: '0.35rem 0.8rem' }} disabled={page <= 1}
                onClick={() => setState((prev) => ({ ...prev, page: Math.max(1, prev.page - 1) }))}>
                Prev
              </button>
              <button type=\"button\" className=\"page-header button\" style={{ padding: '0.35rem 0.8rem' }}
                disabled={page >= totalPages || !slice.length}
                onClick={() => setState((prev) => ({ ...prev, page: prev.page + 1 }))}>
                Next
              </button>
            </div>
          </div>

          <div id=\"coralogix-list\" style={{ marginTop: '0.75rem' }}>
            {!slice.length ? (
              <p className=\"muted\">No Coralogix results yet.</p>
            ) : (
              slice.map((record, idx) => (
                <div className=\"coralogix-record\" key={`${record['@timestamp'] || record.time || idx}-${idx}`}>
                  <div className=\"record-meta\">
                    <span className=\"timestamp\">{record.timestamp || record.time || record['@timestamp'] || 'timestamp unknown'}</span>
                    {record.severity || record.level || record.levelName || record.log_level ? (
                      <span className=\"severity\">{record.severity || record.level || record.levelName || record.log_level}</span>
                    ) : null}
                  </div>
                  <pre className=\"record-body\">{record.text || record.message || record.msg || record.content || JSON.stringify(record, null, 2)}</pre>
                </div>
              ))
            )}
          </div>
        </section>
      );
    };

    const App = () => {
      const [theme, setTheme] = useState('light');
      const [message, setMessage] = useState('Drop a file to get started.');
      const [assistant, setAssistant] = useState('Waiting for input.');
      const [assistantError, setAssistantError] = useState('');
      const [localSummary, setLocalSummary] = useState(null);
      const [findings, setFindings] = useState([]);
      const [history, setHistory] = useState([]);
      const [resultsVisible, setResultsVisible] = useState(false);
      const [busy, setBusy] = useState(false);
      const [sessionInfo, setSessionInfo] = useState({ connected: false, text: 'Not connected.' });
      const [sessionLoading, setSessionLoading] = useState(false);
      const [coralogixState, setCoralogixState] = useState({
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
      });

      useEffect(() => {
        const stored = localStorage.getItem('theme');
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        const nextTheme = stored || (prefersDark ? 'dark' : 'light');
        document.documentElement.setAttribute('data-theme', nextTheme);
        setTheme(nextTheme);
      }, []);

      const toggleTheme = () => {
        setTheme((prev) => {
          const next = prev === 'dark' ? 'light' : 'dark';
          document.documentElement.setAttribute('data-theme', next);
          localStorage.setItem('theme', next);
          return next;
        });
      };

      const refreshSession = async () => {
        try {
          const response = await fetch('/chatgpt/session');
          if (!response.ok) return;
          const data = await response.json();
          if (!data.connected) {
            setSessionInfo({ connected: false, text: 'Not connected.' });
            return;
          }
          const badge = data.account || 'ChatGPT account';
          const details = data.resource_summary || 'Connected to ChatGPT.';
          setSessionInfo({ connected: true, text: `${badge} — ${details}` });
        } catch (err) {
          console.error(err);
          setSessionInfo({ connected: false, text: 'Could not load ChatGPT session status.' });
        }
      };

      useEffect(() => { refreshSession(); }, []);

      const handleLogin = async (token) => {
        setSessionLoading(true);
        try {
          const response = await fetch('/chatgpt/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sso_token: token || undefined }),
          });
          const data = await response.json();
          const text = data.message || (data.connected ? 'Connected to ChatGPT.' : 'Not connected.');
          setSessionInfo({ connected: !!data.connected, text });
        } catch (err) {
          console.error(err);
          setSessionInfo({ connected: false, text: 'Could not connect to ChatGPT.' });
        } finally {
          setSessionLoading(false);
        }
      };

      const handleFiles = async (files) => {
        if (!files.length) {
          setMessage('No files detected.');
          return;
        }
        setBusy(true);
        setMessage('Processing logs...');
        setAssistant('Waiting for ChatGPT...');
        setAssistantError('');
        try {
          const payload = [];
          for (const file of files) {
            if (file.name.toLowerCase().endsWith('.zip')) {
              const buffer = await file.arrayBuffer();
              payload.push({ name: file.name, content: bufferToBase64(buffer), encoding: 'base64' });
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
            setFindings([]);
            return;
          }

          const data = await response.json();
          setLocalSummary(data.local_summary || null);
          setAssistant(data.assistant || (data.assistant_error ? 'Unavailable.' : 'Waiting for input.'));
          setAssistantError(data.assistant_error || '');
          setFindings(Array.isArray(data.findings) ? data.findings : []);
          setHistory(Array.isArray(data.history) ? data.history.slice(0, 20) : []);
          setMessage(data.message || 'Analysis complete.');
          setResultsVisible(true);
        } catch (err) {
          console.error(err);
          setMessage('Something went wrong.');
          setFindings([]);
        } finally {
          setBusy(false);
        }
      };

      const searchCoralogix = async () => {
        if (!coralogixState.from || !coralogixState.to) {
          setCoralogixState((prev) => ({ ...prev, status: 'Please select a start and end time.' }));
          return;
        }

        setCoralogixState((prev) => ({ ...prev, status: 'Searching Coralogix...', loading: true, page: 1 }));
        try {
          const payload = {
            query: coralogixState.query,
            timeframe: { from: coralogixState.from, to: coralogixState.to },
            pagination: { limit: coralogixState.limit, offset: 0 },
          };

          if ((coralogixState.apiKey || '').trim()) {
            payload.api_key = coralogixState.apiKey.trim();
          }
          if (coralogixState.useSummary) {
            payload.use_last_summary = true;
          }

          const response = await fetch('/coralogix-search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });

          if (!response.ok) {
            const text = await response.text();
            throw new Error(text || 'Coralogix search failed.');
          }

          const data = await response.json();
          const records = Array.isArray(data.records) ? data.records : [];
          const hits = Number.isFinite(Number(data.hits)) ? Number(data.hits) : records.length;
          setCoralogixState((prev) => ({
            ...prev,
            results: records,
            hits,
            status: data.message || 'Search complete.',
            loading: false,
            page: 1,
          }));
        } catch (err) {
          console.error(err);
          setCoralogixState((prev) => ({
            ...prev,
            results: [],
            hits: 0,
            status: err.message || 'Coralogix search failed.',
            loading: false,
            page: 1,
          }));
        }
      };

      return (
        <div>
          <div className=\"page-header\">
            <h1>Itay Logs Reviewer</h1>
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
          </div>

          <div className=\"card-grid\">
            <SessionCard onLogin={handleLogin} sessionInfo={sessionInfo} loading={sessionLoading} />
            <DropZone onFiles={handleFiles} busy={busy} helperText=\"Nothing is uploaded anywhere—everything stays local to this app.\" message={message} />
          </div>

          <section id=\"results\" style={{ marginTop: '1.25rem', display: resultsVisible ? 'grid' : 'none', gap: '1rem', gridTemplateColumns: '1fr 1fr' }}>
            <div className=\"card\">
              <h2>Local summary</h2>
              <SummarySection localSummary={localSummary} fallbackText={message} />
            </div>
            <div className=\"card\">
              <h2>ChatGPT recommendations</h2>
              <AssistantSection text={assistant} error={assistantError} />
            </div>
          </section>

          <section className=\"card\" style={{ marginTop: '1rem' }}>
            <h2>Findings</h2>
            <FindingsList findings={findings} />
          </section>

          <section className=\"card\" style={{ marginTop: '1rem' }}>
            <h2>History</h2>
            <HistoryList history={history} />
          </section>

          <CoralogixPanel onSearch={searchCoralogix} state={coralogixState} setState={setCoralogixState} />

          <footer>
            Drop your logs to see a quick summary of findings. Remote queries use Coralogix via your configured credentials.
          </footer>
        </div>
      );
    };

    const root = ReactDOM.createRoot(document.getElementById('root'));
    root.render(<App />);
  </script>
</body>
</html>

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
