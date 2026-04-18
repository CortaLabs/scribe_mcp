# Install and Bootstrap

Version: 2.5  
Updated: 2026-04-18

## Overview

This is the canonical onboarding guide for public users of `scribe-mcp`.
It reflects current runtime/source behavior for this release line.

## Table of contents

1. [Install](#install)
2. [Bootstrap Postgres runtime (default)](#bootstrap-postgres-runtime-default)
3. [Standalone SQLite (explicit local-only opt-in)](#standalone-sqlite-explicit-local-only-opt-in)
4. [Remote/client posture](#remoteclient-posture)
5. [Codex projection path](#codex-projection-path)

## Install

```bash
pip install scribe-mcp
```

Validate installed commands:

```bash
scribe --help
scribe-server --help
scribe-server-sse --help
```

## Bootstrap Postgres runtime (default)

`SCRIBE_STORAGE_BACKEND` defaults to `postgres`.
For server/runtime posture, provide `SCRIBE_DB_URL`.

```bash
export SCRIBE_STORAGE_BACKEND=postgres
export SCRIBE_DB_URL="postgresql://scribe_app:pass@127.0.0.1:5432/scribe"
scribe-server
```

Optional guided setup:

```bash
scribe bootstrap
```

## Standalone SQLite (explicit local-only opt-in)

SQLite is supported for local-only standalone usage when explicitly selected.

```bash
export SCRIBE_MODE=standalone
export SCRIBE_STORAGE_BACKEND=sqlite
# Optional:
# export SCRIBE_DB_PATH=".scribe/scribe.db"
scribe-server
```

## Remote/client posture

Remote/client is internal compatibility only for this release line.
Public-release posture (`SCRIBE_RELEASE_PROFILE=public`) excludes remote/client startup.

When used internally:

- `SCRIBE_REMOTE_URL` is the service root (example: `https://scribe.internal.example`)
- mode detection probes `<root>/health`
- SSE stream transport is `<root>/sse`
- message POST target is `<root>/messages/`

Example internal-only client environment:

```bash
export SCRIBE_MODE=client
export SCRIBE_RELEASE_PROFILE=internal
export SCRIBE_REMOTE_URL="https://scribe.internal.example"
export SCRIBE_REMOTE_AUTH_TOKEN="replace-with-token"
```

## Codex projection path

Use the shipped CLI projection path:

```bash
scribe plugins project-codex --repo-root /absolute/path/to/repo
```

Optional flags:

- `--plugin-root` to override plugin bundle path
- `--codex-home` to target a specific CODEX_HOME
- `--config-path` to target a specific Codex config file

This guide intentionally does not define a generic plugin installer.
