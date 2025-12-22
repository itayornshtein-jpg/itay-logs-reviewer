# itay-logs-reviewer

A lightweight log reviewer that can scan plain text log files, directories of logs, or `.zip` archives of logs. The tool highlights lines that look like errors, exceptions, or tracebacks and offers quick suggestions for next steps.

## Features
- Accepts a single log file, a directory of log files, or a `.zip` archive containing log files.
- Detects common error patterns (ERROR, CRITICAL, exceptions, Python tracebacks).
- Provides simple next-step suggestions for common issues like timeouts, connection failures, or missing files.
- Summarizes findings by category and highlights the most repeated messages.

## Usage
Run the CLI using Python:

```bash
python -m logs_reviewer <path-to-log-file-or-zip-or-directory>
```

Example:

```bash
python -m logs_reviewer ./sample_logs.zip
```

The command prints a summary including counts by category, top repeated messages, and sample findings with suggestions.

## Development
Run the tests with:

```bash
python -m unittest
```

The test suite covers reading from both directories and zip archives and ensures common error patterns are detected.
