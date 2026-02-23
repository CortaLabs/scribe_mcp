---
id: council_sdk_hetzner-research-rom-lab-agent-imports-20260217
title: "\U0001F52C Research Rom Lab Agent Imports 20260217 \u2014 council_sdk_hetzner"
doc_type: RESEARCH_ROM_LAB_AGENT_IMPORTS_20260217
doc_name: RESEARCH_ROM_LAB_AGENT_IMPORTS_20260217
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 12:45:21 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Rom Lab Agent Imports 20260217 — council_sdk_hetzner
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 12:44:49 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->
## Executive Summary

**Objective**: Identify ALL third-party pip dependencies required by the rom_lab agent module for Docker container inclusion.

**Scope**: 
- `src/rom_lab/agent/__init__.py`
- `src/rom_lab/agent/runner.py`
- `src/rom_lab/agent/stream_bridge.py`
- `src/rom_lab/api/routes/agent_chat.py`
- `pyproject.toml` (project metadata)

**Key Finding**: Only **2 explicit third-party packages** are directly imported by the agent module:
1. **anthropic** — LLM provider SDK (Claude API)
2. **fastapi** — Web framework (WebSocket support)

**CRITICAL FINDING**: The `anthropic` package is **NOT listed in pyproject.toml** despite being imported unconditionally. This is a package incompleteness bug.

**Confidence**: HIGH — all imports are at file level or early in-function, no dynamic imports detected in analysis.
<!-- ID: research_scope -->
**Research Lead:** atlas

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### 1. Direct Third-Party Imports (HIGH confidence)

#### File: `src/rom_lab/agent/runner.py` (line 17)
```python
import anthropic
```
**Package**: `anthropic` — Anthropic SDK for Claude API
**Usage**: `anthropic.AsyncAnthropic` for streaming LLM conversations with tool_use
**Required**: YES — core to agent reasoning loop

#### File: `src/rom_lab/agent/stream_bridge.py` (line 18, TYPE_CHECKING block)
```python
if TYPE_CHECKING:
    from fastapi import WebSocket
```
**Package**: `fastapi` — Web framework
**Usage**: Type hints for WebSocket subscriber management
**Required**: YES — but see note below

#### File: `src/rom_lab/api/routes/agent_chat.py` (line 24)
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
```
**Package**: `fastapi` — Web framework
**Usage**: Route definition, WebSocket endpoints
**Required**: YES — critical for agent chat endpoints

### 2. Rom_lab Internal Imports (NOT third-party)
All other imports are rom_lab's own modules:
- `rom_lab.agent.events` — internal event types
- `rom_lab.agent.runner` — AgentRunner class
- `rom_lab.agent.prompts` — system prompt building
- `rom_lab.agent.tools` — tool execution
- `rom_lab.agent.journal` — Adventure Journal (lazy-loaded)
- `rom_lab.agent.memory` — goal/thought stores
- `rom_lab.agent.stream_bridge` — internal WebSocket bridge

### 3. Project Dependencies (pyproject.toml)

**Base dependencies** (already in rom_lab):
```toml
dependencies = [
    "pydantic>=2.0",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "typer>=0.9",
    "watchfiles>=0.20",
]
```

**Optional dev dependencies** (not needed for runtime):
```toml
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "httpx>=0.24",
    "ruff>=0.1",
]
```

### 4. Transitive Dependencies (via fastapi & pydantic)

When fastapi is installed, the following are automatically pulled in:
- **starlette** — ASGI web framework (dependency of fastapi)
- **pydantic** — data validation (already listed in base dependencies)
- **typing-extensions** — type hints backport
- **anyio** — async I/O abstraction
- **And many more** (full graph available via `pip show fastapi`)

When anthropic is installed:
- **httpx** — async HTTP client
- **pydantic** — data validation (already listed)
- **And related dependencies**

**Note**: These are NOT needed in Dockerfile IF rom_lab is already installed as a package (they come via `pip install rom-lab`).

### 5. Missing Anthropic in pyproject.toml (FINDING)

**CRITICAL**: The `anthropic` package is NOT listed in `pyproject.toml` base dependencies.

Current base dependencies:
```toml
dependencies = [
    "pydantic>=2.0",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "typer>=0.9",
    "watchfiles>=0.20",
]
```

But `src/rom_lab/agent/runner.py` requires:
```python
import anthropic
```

**Status**: rom_lab agent module is **incomplete** — missing anthropic dependency.
**Recommendation**: Add `"anthropic>=0.28"` to pyproject.toml dependencies.

### 6. Optional Dependencies Not Used by Agent Module

The agent module does NOT import:
- pydantic (used elsewhere in rom_lab, not by agent module itself)
- uvicorn
- typer
- watchfiles
- pytest, httpx, ruff (dev only)
<!-- ID: technical_analysis -->
**Code Patterns Identified:**
- List relevant code paths, abstractions, or anti-patterns uncovered.

**System Interactions:**
- Summarise dependencies across services, databases, or external APIs.

**Risk Assessment:**
- [ ] Document technical or product risks discovered and mitigation ideas.


---
## Recommendations
<!-- ID: recommendations -->
## Recommendations for Docker Inclusion

### Option A: For rom_lab Package (Recommended)

**Fix pyproject.toml** to add missing anthropic dependency:

```toml
dependencies = [
    "anthropic>=0.28",      # ← ADD THIS
    "pydantic>=2.0",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "typer>=0.9",
    "watchfiles>=0.20",
]
```

Then install in Docker:
```dockerfile
RUN pip install rom-lab[agent]
# or just:
RUN pip install rom-lab
```

This will automatically pull in all transitive dependencies (fastapi, anthropic, pydantic, etc.).

### Option B: For Manual pip install (If Not Packaging rom_lab)

If rom_lab is not installed as a package, manually list these in Dockerfile:

```dockerfile
# Explicit packages needed by agent module
RUN pip install \
    anthropic>=0.28 \
    fastapi>=0.100 \
    pydantic>=2.0 \
    uvicorn[standard]>=0.20 \
    httpx>=0.24
```

(uvicorn needed for serving FastAPI; httpx needed by anthropic async client)

### Option C: Complete Locked Requirements

Generate a requirements.lock from rom_lab:
```bash
cd /home/austin/projects/pokemon/rom_lab
pip install --dry-run rom-lab 2>&1 | grep "Collecting"
# or
pip install rom-lab && pip freeze > requirements-rom-lab.txt
```

Use in Dockerfile:
```dockerfile
COPY requirements-rom-lab.txt .
RUN pip install -r requirements-rom-lab.txt
```

## Summary Table

| Package | Version | Source | Required By | Confidence |
|---------|---------|--------|-------------|------------|
| anthropic | >=0.28 | Direct import | runner.py line 17 | HIGH |
| fastapi | >=0.100 | Direct import | agent_chat.py line 24, stream_bridge.py | HIGH |
| pydantic | >=2.0 | pyproject.toml | (used elsewhere in rom_lab) | MEDIUM |
| uvicorn | >=0.20 | pyproject.toml | (needed to serve FastAPI) | MEDIUM |
| typer | >=0.9 | pyproject.toml | (CLI, not agent) | LOW |
| watchfiles | >=0.20 | pyproject.toml | (development reload) | LOW |

**Priority for Docker**: anthropic + fastapi (tier 1), pydantic + uvicorn (tier 2)
<!-- ID: appendix -->
## Appendix

### A. Import Analysis by File

#### `src/rom_lab/agent/__init__.py`
**Imports**: Only rom_lab internal (events, runner)
**Third-party**: None direct; inherits from runner.py

#### `src/rom_lab/agent/runner.py`
**Line 17**: `import anthropic` — CRITICAL, direct import
**Other imports**: json, logging, dataclasses (stdlib), rom_lab internals

#### `src/rom_lab/agent/stream_bridge.py`
**Line 18**: TYPE_CHECKING import of fastapi.WebSocket (type hint only)
**Line 54, 78**: `await ws.send_json()` — runtime use requires fastapi
**Other imports**: json, logging, collections, deque (stdlib), rom_lab internals

#### `src/rom_lab/api/routes/agent_chat.py`
**Line 24**: `from fastapi import APIRouter, WebSocket, WebSocketDisconnect`
**Other lines**: Lazy imports of rom_lab internal modules (journal, tools, memory, prompts)
**Other imports**: asyncio, json, logging, Enum (stdlib)

### B. Dependency Chain

```
rom_lab agent module
  ├── anthropic (explicit)
  │   └── httpx (transitive)
  │       └── certifi, idna, rfc3986, sniffio, ...
  └── fastapi (explicit)
      ├── starlette
      ├── pydantic
      ├── typing-extensions
      └── anyio
```

### C. Files Referenced in Import Analysis

| Path | Lines | Third-party | Status |
|------|-------|-------------|--------|
| /home/austin/projects/pokemon/rom_lab/src/rom_lab/agent/__init__.py | 28 | 0 | Complete |
| /home/austin/projects/pokemon/rom_lab/src/rom_lab/agent/runner.py | 359 | 1 (anthropic) | Complete |
| /home/austin/projects/pokemon/rom_lab/src/rom_lab/agent/stream_bridge.py | 119 | 1 (fastapi) | Complete |
| /home/austin/projects/pokemon/rom_lab/src/rom_lab/api/routes/agent_chat.py | 692 | 1 (fastapi) | Complete (headers only) |
| /home/austin/projects/pokemon/rom_lab/pyproject.toml | 41 | — | Complete |

### D. Confidence Scoring

| Finding | Confidence | Reasoning |
|---------|------------|-----------|
| anthropic required | HIGH | Direct import at line 17, no fallback, essential to AgentRunner class |
| fastapi required | HIGH | Direct imports in agent_chat.py line 24 and runtime use in stream_bridge.py |
| anthropic missing from pyproject.toml | HIGH | Static analysis shows no entry; agent module imports it unconditionally |
| Transitive deps auto-pulled | HIGH | Standard pip behavior with fastapi and anthropic packages |
| Other rom_lab internals | HIGH | All verified as rom_lab.* modules, not third-party |
