---
id: council_sdk_hetzner-research-romlab-custom-page-api-patterns
title: "\U0001F52C Research Romlab Custom Page Api Patterns \u2014 council_sdk_hetzner"
doc_type: RESEARCH_ROMLAB_CUSTOM_PAGE_API_PATTERNS
doc_name: RESEARCH_ROMLAB_CUSTOM_PAGE_API_PATTERNS
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 12:46:40 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Romlab Custom Page Api Patterns — council_sdk_hetzner
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-17 12:45:56 UTC

> Summarise why this document exists and what decisions it captures.

---
## Executive Summary
<!-- ID: executive_summary -->High-level overview of the research effort and conclusions.
**Primary Objective:** [Describe the primary research goal]

**Key Takeaways:**
- [List critical conclusions or risks].


---
## Research Scope
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

### 1. Custom Page Templates (3 pages)
**Confidence: HIGH** (scanned all templates)

Three custom pages registered in rom_lab:
- **bizhawk.html.j2** (nav_order: 1) — BizHawk emulator UI with control bar, canvas, toolbar
- **runtime-settings.html.j2** (nav_order: 2, nav_group: BizHawk) — Runtime status, server logs, control panel
- **pokeapi.html.js** (nav_order: 10) — Pokémon API browser with sidebar navigation

All templates extend `base.html`, use relative CSS/JS paths (`/council-static/...`), and load custom JavaScript without any API calls in templates themselves. All API logic is in the JS files.

### 2. HTTP Fetch Patterns (4 JS files)
**Confidence: HIGH** (grep-verified across all major JS files)

#### 2.1 Runtime Control API
**File**: `romlab-runtime-control.js`  
**Base URL**: `/api/romlab-runtime`  
**Auth**: Uses `API.getAuthHeaders()` if available (global from app.js)  
**Endpoints Called**:
- `GET /api/romlab-runtime/status?port=8100` — Server status
- `GET /api/romlab-runtime/logs?limit=50` — Server logs
- `POST /api/romlab-runtime/start?port=8100` — Start server
- `POST /api/romlab-runtime/stop?port=8100` — Stop server  
- `POST /api/romlab-runtime/restart?port=8100` — Restart server

```javascript
const DEFAULT_CONFIG = {
    apiBase: '/api/romlab-runtime',
    port: 8100,
    // ...
};

const resp = await fetch(`${_cfg.apiBase}${path}`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
});
```

Ports passed as query parameters; port 8100 is hardcoded default config but can be overridden at init time.

#### 2.2 Emulator Control API
**File**: `emulator-control.js`  
**Base URL**: `/api/romlab/api/emulator`  
**Endpoints Called**:
- `POST /api/romlab/api/emulator/start` — Start emulator
- `POST /api/romlab/api/emulator/stop` — Stop emulator
- `POST /api/romlab/api/emulator/restart` — Restart emulator  
- `GET /api/romlab/api/emulator/status` — Check status
- `GET /api/romlab/api/emulator/games` — List available games
- `GET /api/romlab/api/emulator/logs?limit=80` — Fetch logs

```javascript
const API_BASE = '/api/romlab/api/emulator';

const resp = await fetch(`${API_BASE}/start`, {
    method: 'POST',
    headers: { /* payload headers */ }
});
```

#### 2.3 Game State API
**File**: `game-state.js`  
**Base URLs**: 
- `/api/romlab/state/enriched` — Game state polling (proxied → localhost:8100/state/enriched)
- `/api/romlab/api/look/tool/get_battle` — Battle data
- `/api/romlab/api/look/tool/get_pokemon/{slot}` — Pokémon data

```javascript
const API_URL = '/api/romlab/state/enriched';  // Comment: proxied to localhost:8100/state/enriched
const API_LOOK_BATTLE_URL = '/api/romlab/api/look/tool/get_battle';
const API_LOOK_POKEMON_URL_PREFIX = '/api/romlab/api/look/tool/get_pokemon/';

const resp = await fetch(API_URL, { signal: AbortSignal.timeout(3000) });
```

Polling interval with timeout protection (3000ms) to prevent stalled requests.

#### 2.4 PokeAPI Proxy
**File**: `pokeapi.js`  
**Base URL**: `/api/romlab/api`  
**Endpoints**: Fetches from `/api/romlab/api/pokemon/?limit=500`, `/api/romlab/api/moves/?limit=500`, etc.

```javascript
const POKEAPI_BASE = '/api/romlab/api';

const r = await fetch(`${POKEAPI_BASE}${path}`);
```

No auth headers used here (external data proxy).

### 3. WebSocket Connections (2 types)
**Confidence: HIGH** (verified in bizhawk.js and agent-chat.js)

#### 3.1 BizHawk Stream WebSocket
**File**: `bizhawk.js`  
**Purpose**: Raw ARGB frame streaming from BizHawk emulator (video + audio)  
**URL Pattern**: Protocol-adaptive relative URL

```javascript
const _wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${_wsProto}//${window.location.host}/ws/romlab/bizhawk/stream`;

this.ws = new WebSocket(WS_URL);
```

**Behavior**: 
- Automatically upgrades to `wss:` if page is HTTPS
- Uses `window.location.host` (current host + port)
- **Currently hardcoded for port 8100** in browser (old comment: `ws://localhost:8100/bizhawk/stream`)
- **NOW proxied through** `/ws/romlab/bizhawk/stream`

#### 3.2 Coordination WebSocket (port 8100)
**File**: `agent-chat.js`  
**Purpose**: Mode switching, auto-play commands, journal updates  
**URL Pattern**: Protocol-adaptive relative URL

```javascript
const _acWsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const COORD_BASE = `${_acWsProto}//${window.location.host}`;
const COORD_WS_PATH = '/ws/romlab/ws/agent/chat';

function getCoordWsUrl() {
    return COORD_BASE + COORD_WS_PATH;  // e.g., wss://council-hub:8015/ws/romlab/ws/agent/chat
}

coordWs = new WebSocket(getCoordWsUrl());
```

#### 3.3 SDK WebSocket (port 8015 - Council)
**File**: `agent-chat.js`  
**Purpose**: LLM conversation streaming, tool execution, approvals  
**URL Pattern**: Protocol-adaptive, query-string auth token

```javascript
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = protocol + '//' + window.location.host
    + '/ws/sdk/' + sdkSession.id
    + '?token=' + encodeURIComponent(token);

const ws = new WebSocket(wsUrl);
```

**Behavior**:
- Routes to `/ws/sdk/{sessionId}?token=...`
- Token passed as query parameter (from `getSdkWsAuthToken()`)
- Reconnection logic with exponential backoff (1.2s → 12s, max 8 attempts)
- Replay support via `&replay_from={seqNum}` query param

### 4. Auth Headers Pattern
**Confidence: HIGH** (consistent across files)

All HTTP fetch calls check for global `API.getAuthHeaders()` function (from council-web's `app.js`):

```javascript
const headers = (typeof API !== 'undefined' && API.getAuthHeaders)
    ? API.getAuthHeaders() : {};

const resp = await fetch(url, { headers: headers });
```

This ensures that:
- Council-web session token is automatically included
- Falls back gracefully if `API` object not loaded
- Works in both authenticated and unauthenticated contexts

### 5. API URL Prefixes Summary
**Confidence: HIGH** (all verified)

| Prefix | Purpose | Current Backend | Proxy Target |
|--------|---------|------------------|--------------|
| `/api/romlab-runtime` | Runtime control | 8100 | Runtime API |
| `/api/romlab/api/emulator` | Emulator control | 8100 | Emulator API |
| `/api/romlab/api/look/tool/*` | Game tools (battle/pokemon) | 8100 | Look MCP tools |
| `/api/romlab/state/enriched` | Game state | 8100 | Game state endpoint |
| `/api/romlab/api/*` | Generic proxy | 8100 | PokeAPI, etc. |
| `/api/sdk/*` | Council SDK (sessions, providers) | 8015 | Council daemon |
| `/ws/romlab/bizhawk/stream` | BizHawk video/audio | 8100 | Frame streaming |
| `/ws/romlab/ws/agent/chat` | Coordination WS | 8100 | Coordination server |
| `/ws/sdk/{sessionId}` | Council SDK stream | 8015 | Council WebSocket |

### 6. No Hardcoded Addresses Found
**Confidence: HIGH** (grep-verified across all JS files)

- **No `localhost` references** in custom page JS files
- **No absolute URLs** (e.g., `http://127.0.0.1:8100`)
- **No port numbers hardcoded in URLs** (ports passed as config/query params only)
- **No direct ws://8100 connections** in web JS (all proxied)

The only hardcoded references are config defaults (`port: 8100` in romlab-runtime-control.js) which are initialization parameters, not connection URLs.
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
## Recommendations for Phase 2 Proxy Integration

### 1. No Changes Required to Custom Pages ✅
**Confidence: HIGH**

Rom_lab's custom pages are **already proxy-ready**. All API calls use relative URLs with `/api/romlab/...` and `/ws/romlab/...` prefixes, making them routing-agnostic. No changes needed to:
- Page templates (bizhawk.html.j2, pokeapi.html.j2, runtime-settings.html.j2)
- Fetch calls in JS files
- WebSocket URL construction

The proxy just needs to forward these paths correctly.

### 2. Proxy Routes Needed (Council-Web to Backend)

The council-web proxy must forward these routes to the rom_lab runtime backend (currently 8100, will be Hetzner endpoint):

#### HTTP Routes
```
/api/romlab-runtime/* → {ROMLAB_BACKEND}/...
/api/romlab/api/* → {ROMLAB_BACKEND}/...
/api/romlab/state/* → {ROMLAB_BACKEND}/...
```

#### WebSocket Routes  
```
/ws/romlab/bizhawk/stream → {ROMLAB_BACKEND}/bizhawk/stream
/ws/romlab/ws/agent/chat → {ROMLAB_BACKEND}/ws/agent/chat
```

**Note**: `/api/sdk/...` and `/ws/sdk/...` routes are Council-internal and don't need remapping.

### 3. Config Pattern for Runtime Backend URL

Inject the backend URL into custom pages via:
- **Environment variable** (recommended): `ROMLAB_BACKEND_URL` 
- **Config injection**: Pass base URL in template context during render
- **Runtime config**: Store in `.council/council.yaml` under `council.integrations.romlab`

Example:
```yaml
council:
  integrations:
    romlab:
      backend_url: "http://localhost:8100"  # Local dev
      backend_url: "http://rom-lab:8100"    # Docker compose
      backend_url: "https://romlab.example.com"  # Production/Hetzner
```

### 4. WebSocket Reconnection Handling

The existing reconnection logic in agent-chat.js already handles temporary disconnections gracefully:
- Exponential backoff (1.2s → 12s)
- Max 8 attempts before failing
- User-friendly disconnect messages

No changes required — proxy should maintain WebSocket connections transparently.

### 5. Auth Token Flow

SDK WebSocket connections use query-string auth tokens. Ensure:
- Council-web's auth system works for `/ws/sdk/...` routes
- Tokens are issued by Council daemon
- Proxy passes through query strings unchanged

Romlab coordination WebSocket (`/ws/romlab/ws/agent/chat`) appears to not use auth tokens currently. Verify if this needs securing in production.

### 6. Testing Checklist for Proxy

After implementing proxy routes:
- [ ] `POST /api/romlab-runtime/start?port=8100` returns 200
- [ ] `GET /api/romlab-runtime/status?port=8100` returns runtime status
- [ ] `ws://localhost:8015/ws/romlab/bizhawk/stream` connects and streams frames
- [ ] `ws://localhost:8015/ws/romlab/ws/agent/chat` connects without auth errors
- [ ] SDK WebSocket `/ws/sdk/{sessionId}?token=...` works unchanged
- [ ] All fetch calls in custom pages receive proper CORS headers
- [ ] Protocol switching (http: → ws:, https: → wss:) works end-to-end
<!-- ID: appendix -->
## Appendix: File Inventory

### Custom Pages (3 templates)
- `/home/austin/projects/pokemon/rom_lab/.council/web/pages/bizhawk.html.j2` (46 KB)
- `/home/austin/projects/pokemon/rom_lab/.council/web/pages/pokeapi.html.j2` (1.6 KB)
- `/home/austin/projects/pokemon/rom_lab/.council/web/pages/runtime-settings.html.j2` (3.6 KB)

### Custom JavaScript (11 files)
**Key files analyzed**:
1. `romlab-runtime-control.js` (14 KB) — Runtime API calls with port config
2. `emulator-control.js` (16 KB) — Emulator start/stop/status
3. `game-state.js` (25 KB) — Game state polling with timeout
4. `pokeapi.js` (25 KB) — PokeAPI proxy
5. `bizhawk.js` (99 KB) — BizHawk WebSocket (frame/audio streaming)
6. `agent-chat.js` (177 KB) — Agent chat with SDK + coordination WebSockets

**Other files** (inspected but no API calls):
- `adventure-journal.js` — Journal UI (no fetch/WS)
- `audio-streamer-processor.js` — Audio processing (Web Audio API only)
- `hex-viewer.js` — Hex dump viewer (local data)
- `tool-renderers.js` — Tool rendering (no API)
- `romlab-runtime-toggle.js` — Runtime toggle UI

### Routes
- `/pages/bizhawk` — BizHawk emulator
- `/pages/runtime-settings` — Runtime control panel  
- `/pages/pokeapi` — Pokémon API browser

### Key Code Snippets

#### API Base URL Pattern
```javascript
// romlab-runtime-control.js (line 10)
const DEFAULT_CONFIG = {
    apiBase: '/api/romlab-runtime',
    port: 8100,
    // ...
};

// emulator-control.js (line 12)
const API_BASE = '/api/romlab/api/emulator';

// pokeapi.js (line 17)
const POKEAPI_BASE = '/api/romlab/api';

// game-state.js (line 13-15)
const API_URL = '/api/romlab/state/enriched';
const API_LOOK_BATTLE_URL = '/api/romlab/api/look/tool/get_battle';
const API_LOOK_POKEMON_URL_PREFIX = '/api/romlab/api/look/tool/get_pokemon/';
```

#### WebSocket URL Construction
```javascript
// bizhawk.js (line 24-25)
const _wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${_wsProto}//${window.location.host}/ws/romlab/bizhawk/stream`;

// agent-chat.js (line 21-22)
const _acWsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const COORD_BASE = `${_acWsProto}//${window.location.host}`;
const COORD_WS_PATH = '/ws/romlab/ws/agent/chat';

// agent-chat.js (line 2791-2797) — SDK WebSocket
const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const wsUrl = protocol + '//' + window.location.host
    + '/ws/sdk/' + sdkSession.id
    + '?token=' + encodeURIComponent(token);
```

#### Auth Headers
```javascript
// Consistent pattern across files
const headers = (typeof API !== 'undefined' && API.getAuthHeaders)
    ? API.getAuthHeaders() : {};

const resp = await fetch(url, { headers: headers });
```

### Technical Details

**Protocol Detection**: All WebSocket URLs use `window.location.protocol` to automatically upgrade from `ws:` to `wss:` when served over HTTPS. This makes them deployment-agnostic.

**Reconnection Strategy**: Agent-chat.js implements exponential backoff for SDK WebSocket disconnections:
- Base delay: 1200ms
- Max delay: 12000ms  
- Max attempts: 8
- Formula: `min(1200 * 2^attempt, 12000)`

**Timeout Handling**: Game-state.js uses `AbortSignal.timeout(3000)` for all game state fetches to prevent stalled long-polling requests.
