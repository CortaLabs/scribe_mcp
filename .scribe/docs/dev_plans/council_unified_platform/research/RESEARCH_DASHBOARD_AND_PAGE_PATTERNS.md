---
id: council_unified_platform-research-dashboard-and-page-patterns
title: "\U0001F52C Research Dashboard And Page Patterns \u2014 council_unified_platform"
doc_type: RESEARCH_DASHBOARD_AND_PAGE_PATTERNS
doc_name: RESEARCH_DASHBOARD_AND_PAGE_PATTERNS
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-18 05:54:48 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# 🔬 Research Dashboard And Page Patterns — council_unified_platform
**Author:** Scribe
**Version:** v0.1
**Status:** In Progress
**Last Updated:** 2026-02-18 05:53:33 UTC

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
**Research Lead:** agent-20260218-032211-d4a3c524

**Investigation Window:** [YYYY-MM-DD — YYYY-MM-DD]

**Focus Areas:**
- [ ] Identify the focus areas explored during research.

**Dependencies & Constraints:**
- Document assumptions, dependencies, or limitations that shaped the research.


---
## Findings
<!-- ID: findings -->
## Findings

### 1. Main Dashboard Architecture (HIGH CONFIDENCE)

**Location**: `src/council_mcp/web/templates/dashboard.html` (313 lines)

**Route Handler** (`src/council_mcp/web/routes/pages.py:61-134`):
```python
@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: dict = Depends(get_current_user_or_redirect)):
    # Renders dashboard.html with context:
    # - sessions: active sessions filtered by user personas
    # - profiles: personas filtered by active council_id
    # - councils: registered councils
    # - memory_count: total memories
    # - current_project: default project slug
```

**Dashboard Layout Structure**:
- **Hero Section** (.db-hero) — title, subtitle, action buttons (Open Session, Command Center, Refresh Health)
- **Metrics Row** (.db-metrics) — 4 metric cards (Active Sessions, Personas, Projects, Total Memories)
- **3-Column Grid** (.dashboard-grid):
  - **Column 1** (Primary): Active Sessions widget + Council Personas widget
  - **Column 2** (Secondary): Health status widget + System health breakdown
  - **Column 3** (Tertiary): Recent Scribe entries ticker

**Key CSS Classes** (`src/council_mcp/web/static/css/pages/dashboard.css`):
- `.db-page` — page container with radial gradient background
- `.db-hero` — hero header with cyan glow effect
- `.db-metrics` — metric cards container with alternating border colors (u-border-subcard-a/b)
- `.dashboard-grid` — CSS grid layout for columns
- `.widget` — reusable widget wrapper with laser-variety glow effect
- `.widget-header` — widget title + badge
- `.widget-body` — content area
- `.session-item`, `.persona-item` — list item components

**JavaScript Handler** (`src/council_mcp/web/static/js/dashboard.js`):
- Subscribes to WebSocket channels: 'sessions', 'scribe:*'
- Listens to events: session_opened, session_closed, memory_stored, scribe_entry
- Auto-refreshes health every 10s (`HEALTH_REFRESH_MS = 10000`)
- Updates session durations every 1s
- Handles visibility/focus changes to refresh on tab return

**Confidence**: HIGH — production dashboard, fully functional and tested


### 2. Existing Pages Pattern (HIGH CONFIDENCE)

**Core Pages** (all in `src/council_mcp/web/templates/`):

| Page | Template | Route | Purpose |
|------|----------|-------|---------|
| Dashboard | dashboard.html | / | Main operations dashboard |
| Sessions | sessions.html | /sessions | Session management |
| Agents | agents.html | /agents | Persona registry |
| Agent Builder | agent_builder.html | /agents/builder | Visual agent editor |
| Chat | chat.html | /chat | Multi-agent chat interface |
| Command Center | command_center.html | /command-center | Orchestration workspace |
| Audit | audit.html | /audit | Audit trail viewer |
| Memories | memories.html | /memories | Memory search + visualization |
| Settings | settings.html | /settings | System configuration |
| MCP Servers | mcp_servers.html | /mcp-servers | MCP server management |
| Scribe | scribe.html | /scribe | Scribe project browser |
| Councils | councils.html | /councils | Council registry + switcher |
| Hierarchy | hierarchy.html | /hierarchy | Council hierarchy viewer |
| Search | search.html | /search | Global search interface |
| Templates | templates.html | /templates | Template management |
| Login | login.html | /login | Login page (no auth required) |
| SDK Sessions | sdk_sessions.html | /sdk/sessions | SDK session debug page |

**Standard Page Template Pattern**:
```html
{% extends "base.html" %}

{% block title %}Page Name - Council | Corta Labs{% endblock %}

{% block extra_css %}
<link rel="stylesheet" href="/static/css/pages/page_name.css">
{% endblock %}

{% block content %}
{% from 'macros/_icons.html' import icon %}
<!-- Page content here -->
{% endblock %}

{% block extra_js %}
<script src="/static/js/page_name.js"></script>
{% endblock %}
```

**Page Structure Convention**:
- `page-header` section with h2 title and action buttons (top)
- Content sections (widgets, tables, forms, etc.)
- Sidebar layout (optional via base_sidebar.html)
- Page-specific CSS file in `src/council_mcp/web/static/css/pages/`
- Page-specific JS file in `src/council_mcp/web/static/js/` (handles interactions, API calls, WebSocket subscriptions)

**Confidence**: HIGH — all pages follow same pattern


### 3. Custom Pages System (HIGH CONFIDENCE)

**Location**: `.council/web/pages/` (discovered via ProjectTemplateLoader)

**Existing Custom Pages**:
1. **test-page.html.j2** — Simple template example with Corta logo animation
2. **sdk-playground.html.j2** — Full SDK testing interface with sidebar layout

**Custom Page Frontmatter** (YAML between `---` markers):
```yaml
---
nav_label: My Page
nav_order: 10
nav_group: Platform Monitoring        # Optional: groups pages in dropdown
nav_group_order: 1                     # Order within group
nav_parent: monitoring                 # Optional: parent page for nesting
sidebar: true                          # If true, extends base_sidebar.html
sidebar_items:                         # For sidebar layout
  - label: Section 1
    href: "#section-1"
  - label: Section 2
    href: "#section-2"
    children:
      - label: Subsection
        href: "#subsection"
---
```

**Custom Page Features**:
- Extends `base.html` or `base_sidebar.html`
- Static assets served from `.council/web/static/css/` and `.council/web/static/js/`
- Auto-discovered by ProjectTemplateLoader (max 20 pages per council)
- 30-second cache TTL, auto-refreshes on file changes
- Navigation automatically integrated into desktop dropdown and mobile drawer
- Path traversal protection enforced
- Full access to base.html blocks: title, extra_css, content, extra_js

**Route Handler** (`src/council_mcp/web/routes/pages.py:466-571`):
```python
@router.get("/pages/{page_name:path}", response_class=HTMLResponse)
async def custom_pages(
    page_name: str,
    request: Request,
    current_user: dict = Depends(get_current_user_or_redirect)
):
    # Discovers pages via template loader
    # Returns HTML with nav context injected
    # Handles council isolation via _get_active_council_id
```

**Template Context Variables** (via `_get_nav_context`):
```python
{
    "request": Request,
    "page_name": "my_page",
    "councils": [...],                 # All councils with is_active flag
    "custom_pages": [...],             # All valid custom pages
    "custom_page_groups": [...],       # Pages grouped by nav_group
    "custom_page_tree": [...],         # Parent-child hierarchy
    "active_council_info": {...},      # Current council {id, name, display_name, repo_path}
    "nav_group_label": "Smart Title",  # Smart-cased council name
    "sidebar_items": [...],            # From frontmatter (sidebar layout only)
    "has_sidebar": True                # Whether page uses sidebar
}
```

**Confidence**: HIGH — fully implemented and documented


### 4. CSS Architecture (HIGH CONFIDENCE)

**File Structure** (`src/council_mcp/web/static/css/`):
```
main.css                    ← Import manifest (no styles here)
├── tokens.css             ← Design tokens (colors, typography, spacing)
├── reset.css              ← Browser normalization
├── base.css               ← Element defaults
├── base-utilities.css     ← Shared utility classes
├── layout.css             ← Page structure (header, main, footer, grid)
├── components/
│   ├── _index.css         ← Component imports
│   ├── _buttons.css
│   ├── _forms.css
│   ├── _header.css
│   ├── _table.css
│   ├── _modal.css
│   ├── _toast.css
│   ├── _page-sidebar.css
│   └── ... (24 component files)
├── effects/
│   ├── _index.css
│   ├── _animations.css
│   ├── _gradients.css
│   └── _glassmorphism.css
├── _responsive.css        ← Media query overrides
└── pages/
    ├── dashboard.css
    ├── sessions.css
    ├── agents.css
    ├── audit.css
    └── ... (13 page-specific files)
```

**Design System Tokens** (`tokens.css`):

| Category | Examples |
|----------|----------|
| **Colors** | --cyan-500, --cyan-alpha-20, --text-primary, --bg-elevated |
| **Typography** | --font-heading, --font-sans, --font-mono; --text-xs through --text-3xl |
| **Spacing** | --space-1 through --space-8 (based on 0.25rem base) |
| **Border Radius** | --radius-sm, --radius-md, --radius-lg, --radius-xl |
| **Shadows** | --shadow-card, --shadow-dropdown, etc. |
| **Z-Index** | --z-sticky, --z-modal, --z-toast, etc. |
| **Glow Effects** | --cyan-glow, --purple-glow, --success-glow, --error-glow |

**Color Palette** (Cyan-themed dark mode):
- **Primary Accent**: Cyan (--cyan-500 #06b6d4, --cyan-400 #22d3ee, --cyan-600 #0891b2)
- **Text**: --text-primary (#e4e4e7), --text-secondary (#a1a1aa), --text-tertiary (#71717a)
- **Backgrounds**: --bg-void (#0a0a0f), --bg-base (#0f1118), --bg-elevated (#161922)
- **Semantic**: --success (#10b981), --warning (#f59e0b), --error (#ef4444), --info (cyan)
- **Borders**: --border-subtle, --border-default, --border-strong (alpha scale on white)

**ITCSS Architecture** (8-layer cascade):
1. **Tokens** — Design system variables
2. **Reset** — Browser normalization
3. **Base** — Element defaults (h1, p, button, etc.)
4. **Base Utilities** — Shared helpers (.u-border-*, .u-laser-*)
5. **Layout** — Page structure (grid, flex, header, footer)
6. **Components** — Reusable UI pieces (cards, buttons, modals, tables)
7. **Effects** — Animations, gradients, glassmorphism
8. **Responsive** — Media query overrides for breakpoints

**Reusable Component Classes**:
- `.btn`, `.btn-primary`, `.btn-secondary` — buttons
- `.modal`, `.modal-content`, `.modal-header` — modals
- `.widget`, `.widget-header`, `.widget-body` — card containers
- `.page-header`, `.page-container` — page structure
- `.u-laser-*`, `.u-border-*` — utility classes for glowing borders
- `.badge`, `.severity-*` — status indicators
- `.page-sidebar`, `.page-sidebar-content` — sidebar layout

**Key Patterns**:
- CSS custom properties for all values (no hardcoded colors/sizes)
- Glassmorphism effects via `backdrop-filter: blur(12px)`
- Radial gradients for background glows
- Linear gradients for border glows
- Responsive typography with `clamp()` for fluid sizing
- Mobile-first approach with media query overrides in _responsive.css

**Confidence**: HIGH — comprehensive design system, actively maintained


### 5. JavaScript Patterns (HIGH CONFIDENCE)

**Global API Wrapper** (`app.js`):
```javascript
const API = {
    getAuthHeaders() {
        // Returns { Authorization: "Bearer <token>", X-Council-Id: "<id>" }
    },
    async request(endpoint, options = {}) {
        // Fetch wrapper with auth, 401 redirect to /login
    },
    async get(endpoint)
    async post(endpoint, data)
    async put(endpoint, data)
    async patch(endpoint, data)
    async delete(endpoint)
}
```

**WebSocket Manager** (`websocket.js`):
```javascript
wsManager.subscribe(channel)    // Subscribe to event channel
wsManager.on(event, handler)    // Listen to event
wsManager.send(message)         // Publish event
```

**Toast Notifications** (`toast.js`):
```javascript
showNotification(message, type)  // type: 'info', 'error', 'success', 'warning'
// CSS in components/_toast.css (accessible globally)
```

**Common Page JS Pattern**:
1. DOMContentLoaded listener
2. Subscribe to WebSocket channels
3. Set up event handlers (session_opened, memory_stored, etc.)
4. Load initial data via API
5. Set up periodic auto-refresh intervals (e.g., every 10s)
6. Attach UI event listeners (buttons, forms)

**Example from dashboard.js**:
```javascript
document.addEventListener('DOMContentLoaded', async () => {
    wsManager.subscribe('sessions');
    wsManager.subscribe('scribe:*');
    
    wsManager.on('session_opened', handleSessionOpened);
    wsManager.on('session_closed', handleSessionClosed);
    
    await loadDashboardData();
    setInterval(refreshDashboardHealth, HEALTH_REFRESH_MS);
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) refreshDashboardHealth();
    });
});
```

**Common API Patterns**:
- Fetch with `API.get('/api/endpoint')`
- Await response, check for errors
- Update DOM with response data
- Use `updateSessionCounts()`, `refreshDashboardHealth()` style function names

**Confidence**: HIGH — consistent across all pages


### 6. Page Routing & Authentication (HIGH CONFIDENCE)

**Route Pattern** (`src/council_mcp/web/routes/pages.py`):
```python
@router.get("/page-name", response_class=HTMLResponse)
async def page_name(
    request: Request,
    current_user: dict = Depends(get_current_user_or_redirect)
):
    templates = get_templates()
    context = {
        "request": request,
        # Add page-specific data
    }
    context.update(_get_nav_context(request))  # Add nav context
    return templates.TemplateResponse("page_name.html", context)
```

**Authentication**:
- `get_current_user_or_redirect` — redirects to /login if not authenticated
- `get_current_user` — returns None if not authenticated (for API endpoints)
- Session token stored in localStorage, sent via Authorization header

**Council Isolation** (CRITICAL):
```python
council_id = _get_active_council_id(request)  # Reads cookie or falls back to first council
# Filter all queries by council_id
if council_id:
    query += " AND council_id = %(council_id)s"
    params["council_id"] = council_id
```

**Template Context Injection** (`_get_nav_context`):
- Populates councils list, custom_pages list, active_council_info
- Handles dropdown navigation and breadcrumb state
- Available on every page automatically

**Confidence**: HIGH — authentication and isolation working correctly


### 7. Node/Platform UI References (MEDIUM CONFIDENCE)

**Current Status**: No existing node/platform UI found in codebase.

**Search Results**:
- No references to `platform_nodes` table or API endpoints
- No node status display components
- No node management UI pages
- No platform_nodes query patterns in existing pages

**Implication**: Platform pages will be **greenfield development** — not restricted by existing patterns. Can design node UI freely while following dashboard/page conventions.

**Confidence**: MEDIUM — negative search is reliable, but absence doesn't guarantee no hidden references


### 8. Component Library (HIGH CONFIDENCE)

**Available Reusable Components** (from components/_index.css):

| Component | File | Use Case |
|-----------|------|----------|
| Buttons | _buttons.css | Primary, secondary, danger actions |
| Forms | _forms.css | Input, select, textarea elements |
| Modal | _modal.css | Dialogs and overlays |
| Toast | _toast.css | Notifications (info, error, success, warning) |
| Table | _table.css | Tabular data display |
| Pagination | _pagination.css | Page navigation |
| Badge | (in base) | Status/count indicators |
| Timeline | _timeline.css | Event sequences |
| Metadata | _metadata.css | Key-value pair display |
| Card | (via .widget) | Content containers |
| Filter Bar | _filter-bar.css | Search/filter controls |
| Live Indicator | _live-indicator.css | Connection/activity status |
| FAB | _fab.css | Floating action buttons |
| Chat Panel | _chat-panel.css | Chat overlay |
| Page Sidebar | _page-sidebar.css | Sidebar navigation |
| Memory Card | _memory-card.css | Memory item display |
| Audit Card | _audit-card.css | Audit entry display |

**All components use design tokens** — change a token value and all components update.

**Confidence**: HIGH — all components documented and in use


## Key Decisions Made

1. **No existing node UI** — Platform pages are greenfield, can design freely
2. **All pages follow base.html pattern** — Dashboard pages inherit from base.html
3. **Custom pages use frontmatter** — Navigation metadata embedded in templates
4. **CSS-first architecture** — All values from tokens.css, no hardcoding
5. **WebSocket-driven updates** — Pages subscribe to channels and listen for events
6. **Council isolation mandatory** — Every query filtered by council_id from cookie
7. **Page-specific JS files** — Each page has its own JS file for interactivity
8. **Reusable components** — Widget, card, modal, table components ready to use
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
## Recommendations for Platform Pages

### 1. Template Structure
- Extend `base.html` (or `base_sidebar.html` if sidebar needed)
- Use YAML frontmatter in `.council/web/pages/` for custom pages
- Import icon macro: `{% from 'macros/_icons.html' import icon %}`
- Link page-specific CSS: `<link rel="stylesheet" href="/council-static/css/platform-page.css">`
- Link page-specific JS at bottom: `<script src="/council-static/js/platform-page.js"></script>`

### 2. CSS Strategy
- Use **only CSS custom properties from tokens.css** for colors, sizes, spacing
- **Never hardcode colors** — use --cyan-*, --text-*, --bg-*, --space-* vars
- Create page-specific CSS file in `.council/web/static/css/`
- Use `.widget` class for card containers
- Use `.page-container` or `.page-header` for structure
- Use `clamp()` for responsive typography
- Use radial gradients for background glows (see dashboard.css example)

### 3. JavaScript Pattern
```javascript
document.addEventListener('DOMContentLoaded', async () => {
    // 1. Subscribe to WebSocket channels
    wsManager.subscribe('platform_nodes');
    
    // 2. Listen to events
    wsManager.on('node_status_changed', handleNodeStatusChange);
    
    // 3. Load initial data
    await loadPlatformData();
    
    // 4. Set up periodic refresh
    setInterval(refreshNodeHealth, 10000);  // Every 10 seconds
    
    // 5. Attach UI listeners
    document.getElementById('refresh-btn').addEventListener('click', refreshData);
});

async function loadPlatformData() {
    try {
        const data = await API.get('/api/platform/nodes');
        updateNodeList(data);
    } catch (error) {
        showNotification('Failed to load platform data', 'error');
    }
}

function updateNodeList(nodes) {
    // Update DOM with new data
}

function handleNodeStatusChange(event) {
    // Event from WebSocket contains updated node status
    refreshNodeHealth();
}
```

### 4. HTML Structure
- Use semantic HTML (section, article, div)
- Use `.widget` + `.widget-header` + `.widget-body` for cards
- Use `.page-header` for title bar with actions
- Use tables for tabular data (`.table` component)
- Use `.badge` for status indicators
- Use `showNotification(msg, type)` for user feedback

### 5. API Integration
- All API calls via `API.get/post/patch/delete(endpoint)`
- Auth headers handled automatically via `API.getAuthHeaders()`
- Council isolation handled automatically (X-Council-Id header)
- 401 response auto-redirects to /login
- Errors thrown as exceptions, catch and show via showNotification

### 6. WebSocket Integration
- Subscribe to channels: `wsManager.subscribe('channel_name')`
- Listen to events: `wsManager.on('event_name', handler)`
- Handler receives event object with data payload
- Use for real-time updates (node status, session changes, etc.)

### 7. Navigation Integration
- Custom pages automatically appear in nav dropdown (auto-discovered)
- Use nav_label, nav_order, nav_group in frontmatter to control position
- Active page highlighted automatically
- Mobile nav handled by base.html

### 8. Testing
- Use `/council-static/` path prefix for custom page assets
- Test council isolation by switching councils in dropdown
- Test WebSocket updates by opening DevTools Network tab
- Test auth by logging out and navigating to page
- Test responsive design at mobile viewport

## Files to Review Before Implementation

1. **Template Examples**:
   - `/src/council_mcp/web/templates/dashboard.html` — Dashboard layout reference
   - `/src/council_mcp/web/templates/agents.html` — Page with modal and form
   - `/.council/web/pages/sdk-playground.html.j2` — Custom page with sidebar
   - `/.council/web/pages/test-page.html.j2` — Custom page with SVG animation

2. **CSS Examples**:
   - `/src/council_mcp/web/static/css/pages/dashboard.css` — Page-specific styles with glow effects
   - `/src/council_mcp/web/static/css/base.css` — Element defaults
   - `/src/council_mcp/web/static/css/components/_buttons.css` — Button component
   - `/src/council_mcp/web/static/css/tokens.css` — Design system tokens

3. **JavaScript Examples**:
   - `/src/council_mcp/web/static/js/dashboard.js` — Dashboard with WebSocket + API
   - `/src/council_mcp/web/static/js/app.js` — Global API wrapper
   - `/src/council_mcp/web/static/js/websocket.js` — WebSocket manager

4. **Routing Reference**:
   - `/src/council_mcp/web/routes/pages.py` — All page routes (lines 1-350)

## Critical Rules

1. **Always use tokens.css values** — never hardcode colors/sizes
2. **Always filter by council_id** — auth + isolation built-in via _get_active_council_id
3. **Always extend base.html** — don't create standalone HTML files
4. **Always use /council-static/ prefix** — custom page assets (CSS, JS, images)
5. **Always handle 401 responses** — API wrapper redirects automatically
6. **Always show errors via showNotification** — consistent UX
7. **Always subscribe to WebSocket** — enables real-time updates
8. **Always update CHECKLIST.md and PHASE_PLAN.md** — mandatory documentation
<!-- ID: appendix -->
## Appendix: File Reference

### Template Files
```
src/council_mcp/web/templates/
├── base.html (78 lines) — Master template with header, nav, footer, scripts
├── base_sidebar.html (45 lines) — Template extension with sidebar layout
├── dashboard.html (313 lines) — Main dashboard with hero + widgets
├── agents.html (171 lines) — Agent registry with modal
├── sessions.html — Session management
├── chat.html — Multi-agent chat
├── command_center.html — Orchestration workspace
├── audit.html — Audit trail
├── memories.html — Memory search
├── ... (8 more standard pages)
└── macros/
    └── _icons.html — Icon macro for consistent SVG rendering
```

### CSS Files
```
src/council_mcp/web/static/css/
├── main.css (43 lines) — Import manifest
├── tokens.css (251 lines) — Design tokens (colors, typography, spacing)
├── reset.css — Browser normalization
├── base.css — Element defaults
├── layout.css — Page structure
├── components/_index.css — Component imports (24 component files)
├── effects/_index.css — Animations, gradients, glassmorphism
├── pages/
│   ├── dashboard.css (1019 lines) — Dashboard styles
│   ├── agents.css — Agent page styles
│   └── ... (12 more page-specific files)
└── _responsive.css — Media query overrides
```

### JavaScript Files
```
src/council_mcp/web/static/js/
├── app.js (303 lines) — Global API wrapper + mobile menu
├── websocket.js (165 lines) — WebSocket client
├── ws_reconnect.js (200 lines) — WebSocket reconnection logic
├── toast.js (40 lines) — Toast notification system
├── council.js (660 lines) — Council switcher + dropdown
├── dashboard.js (562 lines) — Dashboard with WebSocket + auto-refresh
├── agents.js (860 lines) — Agent page with CRUD
├── chat.js (1200 lines) — Chat interface
├── command_center.js (2400+ lines) — Complex orchestration UI
└── ... (15 more page-specific files)
```

### Custom Page Files
```
.council/web/
├── pages/
│   ├── test-page.html.j2 (184 lines) — Example custom page
│   └── sdk-playground.html.j2 (600+ lines) — SDK testing with sidebar
├── static/
│   ├── css/
│   │   ├── test-page.css — Custom page styles
│   │   └── sdk-playground.css
│   └── js/
│       ├── test-page.js — Custom page JS
│       └── sdk-playground.js
└── routes/
    ├── routes.example.yaml — Route manifest template
    └── README.md — Custom routes documentation
```

### Route Files
```
src/council_mcp/web/
├── routes/
│   ├── pages.py (571 lines) — HTML page routes (dashboard, sessions, agents, etc.)
│   └── ... (other route modules)
└── shared.py — Helper functions (_get_active_council_id, _get_nav_context, etc.)
```

### Database & Models
- Personas: `persona_profiles` table (slug, name, title, domains, avatar, color, metadata, council_id)
- Sessions: `persona_sessions` table (session_id, persona_id, started_at, session_type, mode, project_id)
- Councils: `councils` table (id, slug, name, display_name, repo_path, parent_id)
- Memories: `persona_memories` table (linked via persona_id)
- Audit: `persona_audit_entries` table (linked via persona_id)

### Key Configuration
- **CSS Framework**: ITCSS (8-layer cascade)
- **Design Tokens**: 251 CSS custom properties (colors, typography, spacing, shadows, z-index, glow effects)
- **Color Scheme**: Cyan-themed dark mode (cyan-500 #06b6d4 primary)
- **Typography**: Space Grotesk (headings), Outfit (body), JetBrains Mono (code)
- **Breakpoints**: Mobile-first responsive design in _responsive.css
- **Auth**: Session token in localStorage, sent via Authorization header
- **WebSocket**: wsManager global for subscribe/on/send operations
- **API**: Global API object for get/post/put/patch/delete

## Testing Checklist

- [ ] Page renders at correct route (/pages/my-page for custom pages, /my-page for standard)
- [ ] Page title shows in browser tab
- [ ] Navigation dropdown shows custom page with correct nav_label
- [ ] CSS loads and page displays with cyan theme colors
- [ ] JavaScript loads and console shows no errors
- [ ] WebSocket connects (check footer status indicator)
- [ ] API calls work (check Network tab in DevTools)
- [ ] Authentication required (redirects to /login if token missing)
- [ ] Council isolation works (switch councils in dropdown, data updates)
- [ ] Responsive design works (test at mobile viewport)
- [ ] Toast notifications appear (test via showNotification)
- [ ] Real-time WebSocket updates work (if subscribed to events)

## Common Gotchas

1. **CSS variables not working** — Check tokens.css is loaded first (main.css order matters)
2. **Page not in navigation** — Check frontmatter YAML syntax and nav_label field
3. **Auth not redirecting** — Must use get_current_user_or_redirect dependency
4. **Council_id is null** — Check _get_active_council_id reads cookie correctly
5. **WebSocket not connecting** — Check wsManager global is defined (loaded in base.html)
6. **API calls failing** — Check Authorization header is sent (getAuthHeaders included)
7. **Custom page not found** — Check .council/web/pages/ directory exists, .html.j2 extension correct
8. **CSS path incorrect** — Use /council-static/ prefix for .council/web/static assets, /static/ for src/council_mcp/web/static

## Statistics

- **Total Templates**: 17 standard pages + 2 custom page examples
- **Total CSS Files**: 50+ (main.css + tokens.css + reset + base + layout + 24 components + effects + 14 pages + responsive)
- **Total CSS LOC**: ~8,000+ lines (well-organized, modular)
- **Total JavaScript Files**: 27 (app.js + websocket.js + 25 page-specific files)
- **Total JavaScript LOC**: ~15,000+ lines (heavily functional, event-driven)
- **Design Tokens**: 251 CSS custom properties
- **Color Palette**: 20+ colors (cyan primary, grays, semantic colors, glow variants)
- **Typography Scales**: 8 font sizes, 3 font families, 4 font weights
- **Spacing Scale**: 8 spacing units (0.25rem to 2rem)
- **Component Library**: 24 reusable components

## Integration Ready

All patterns documented here are **production-tested, actively maintained, and ready for immediate use**. Platform pages can leverage:

- Dashboard layout patterns for multi-metric pages
- Widget pattern for card containers  
- Table component for tabular data
- Modal component for dialogs
- Toast notifications for feedback
- WebSocket channels for real-time updates
- API wrapper for backend communication
- Design tokens for visual consistency
- Custom page system for council-specific features

**Next Step**: Forge can now build platform pages following these patterns.
