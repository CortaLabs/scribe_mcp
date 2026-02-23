---
id: council_downstream_cicd-research-custom-pages-docker-20260217
title: 'Custom Pages in Docker: Path Resolution Analysis'
doc_type: custom
doc_name: RESEARCH_CUSTOM_PAGES_DOCKER_20260217
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-17 09:07:43 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Custom Pages in Docker: Path Resolution Analysis

## Executive Summary

Custom council pages in Docker fail because the web container cannot access downstream council repositories on the host filesystem. The architecture fetches `repo_path` from the database (e.g., `/opt/rom_lab` on Hetzner), but the Docker container's filesystem only includes `/app` (council_mcp code). When the web UI tries to render templates or serve static assets from a downstream council, `Path.exists()` checks fail, and `FileResponse` attempts fail with permission or "file not found" errors.

**Confidence**: High (source code verified)
**Root cause**: Volume mount mismatch between host (`/opt/rom_lab`) and container (`/app`)
**Impact**: Custom pages and assets cannot load for any downstream council in Docker
**Solution scope**: Add volume mounts to docker-compose.yaml and/or implement alternative asset serving pattern

## How Custom Pages Load (Request Chain)

### 1. User navigates to `/pages/my_page`

**Handler**: `src/council_mcp/web/routes/pages.py:458-517` (`custom_page` route)

```python
@router.get("/pages/{page_name:path}", response_class=HTMLResponse)
async def custom_page(request, page_name, current_user):
    # Line 479: Get active council from cookie
    council_id = _get_active_council_id(request)
    
    # Line 483: Load council from DB
    council = get_council_by_id_sync(council_id)
    
    # Line 487: Extract repo_path from DB record
    repo_path = Path(council["repo_path"])  # e.g., Path("/opt/rom_lab")
    
    # Line 488-489: Scan for pages at that repo_path
    template_loader = get_template_loader()
    valid_pages = template_loader.get_valid_pages(repo_path)
```

**Key point**: `repo_path` comes from the database, not hardcoded. The web container will receive whatever path is stored in the `council.councils` table.

### 2. Template loader scans for custom pages

**Method**: `src/council_mcp/web/template_loader.py:216-293` (`discover_pages`)

```python
def discover_pages(self, repo_path: Path, *, use_cache=True):
    # Line 241: Construct path to custom pages directory
    pages_dir = repo_path / ".council" / "web" / "pages"
    
    # Line 243: Check if directory exists
    if not pages_dir.is_dir():
        # Returns empty list if path doesn't exist on container
        return []
    
    # Line 257-268: Scan .html.j2 templates
    for path in sorted(pages_dir.glob("*.html.j2")):
        page = self._parse_template_file(path)
        if page:
            pages.append(page)
```

**Docker problem**: When `repo_path=/opt/rom_lab` (a path on Hetzner host), the web container tries to access `/opt/rom_lab/.council/web/pages/`. This directory doesn't exist in the container's filesystem because no volume mount binds the host's `/opt/` into the container.

**Result**: `pages_dir.is_dir()` returns False → discover_pages returns empty list → no custom pages found → request fails with "not found".

### 3. Static file serving has the same problem

**Handler**: `src/council_mcp/web/routes/pages.py:525-571` (`council_static_file` route)

```python
@router.get("/council-static/{file_path:path}")
async def council_static_file(request, file_path, current_user):
    # Line 544: Get active council
    council_id = _get_active_council_id(request)
    
    # Line 548: Load from DB
    council = get_council_by_id_sync(council_id)
    
    # Line 553: Build static path
    static_root = Path(council["repo_path"]) / ".council" / "web" / "static"
    full_path = (static_root / file_path).resolve()
    
    # Line 562: Check if file exists
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    
    # Line 568: Serve the file
    return FileResponse(path=full_path, media_type=content_type)
```

**Docker problem**: Same issue. `FileResponse(path=full_path)` will fail because the path doesn't exist in the container's filesystem.

## Database Schema: How repo_path is Stored

**Table**: `council.councils` (managed by AgentKit + council extensions)

**Query**: `src/council_mcp/storage/registry.py:114-122` (`get_council_by_id_sync`)

```python
def get_council_by_id_sync(council_id: str):
    with models.db.connection() as conn:
        row = conn.execute(
            "SELECT id, parent_council_id, name, repo_path, status, "
            "metadata, created_at, last_seen FROM council.councils WHERE id = %s;",
            (council_id,),
        ).fetchone()
        return dict(row) if row else None
```

**Schema** (expected columns in council.councils):
- `id` (UUID): Primary key
- `parent_council_id` (UUID, nullable): Parent council for hierarchy
- `name` (text): Council name
- **`repo_path` (text): Filesystem path to the council repository** ← THIS IS THE PROBLEM
- `status` (text): Registration status
- `metadata` (jsonb): Arbitrary config
- `created_at` (timestamp): Registration time
- `last_seen` (timestamp): Last activity

**How repo_path gets set**: Via `src/council_mcp/cli/init_cmd.py` or direct DB insert during `council init`.

**Expected value on Hetzner**: `/opt/rom_lab`, `/opt/osrs_hiscore_pull`, etc.

**Inside container**: These paths don't exist because docker-compose.yaml has NO volume mounts that bind `/opt/` or `/opt/rom_lab` into the container.

## Volume Mounts in Docker Compose

**File**: `deploy/docker-compose.yaml`

**Council-web service** (lines 242-288):

```yaml
council-web:
  image: ghcr.io/cortalabs/mcp_spine/web:${DOCKER_IMAGE_TAG:-latest}
  build:
    context: ..
    dockerfile: deploy/Dockerfile
    target: web
  
  # NO VOLUMES SECTION!
  # This means the container ONLY sees:
  # - /app          (from COPY in Dockerfile)
  # - /run/secrets  (from Docker secrets)
  # - Network mounts
  
  networks:
    - backend
  
  ports:
    - "${TAILSCALE_IP:-127.0.0.1}:8015:8015"
```

**Contrast with council-daemon** (lines 150-229):

```yaml
council-daemon:
  # ... other config ...
  
  volumes:
    - scribe_data:/app/.scribe  # Only this volume
```

**Key finding**: The web container has NO volumes binding:
- `/opt/rom_lab` → `/opt/rom_lab` (pass-through)
- `/opt/` → `/opt/` (pass-through)
- Or any alternative mount that makes downstream repos accessible

This is why custom pages fail in Docker but work in local development (where `/opt/` IS accessible on the host OS).

## Request Chain Summary

```
HTTP GET /pages/monitoring
  ↓
web route handler (pages.py:458)
  ↓
Read council_id from cookie
  ↓
Lookup council.councils in DB: get repo_path="/opt/rom_lab"
  ↓
Create Path("/opt/rom_lab") [SUCCESS in memory]
  ↓
Call template_loader.discover_pages(Path("/opt/rom_lab"))
  ↓
Check if "/opt/rom_lab/.council/web/pages/" exists
  ↓
FAIL: Container doesn't see /opt/ directory
  ↓
pages_dir.is_dir() → False
  ↓
Return empty pages list
  ↓
HTTP 404: "Custom page not found"
```

## Static Files Follow the Same Pattern

```
HTTP GET /council-static/css/monitoring.css
  ↓
Static file route handler (pages.py:525)
  ↓
Read council_id from cookie
  ↓
Lookup council.councils: repo_path="/opt/rom_lab"
  ↓
Build path: "/opt/rom_lab/.council/web/static/css/monitoring.css"
  ↓
Call full_path.is_file()
  ↓
FAIL: Path doesn't exist in container
  ↓
HTTP 404: "File not found"
  ↓
CSS/JS fails to load in browser
```

## Why This Works in Local Development

When running locally (without Docker):
1. CLI runs on the host OS (WSL2 on Windows)
2. `/opt/rom_lab` actually exists on the WSL2 filesystem
3. Python code runs in the host Python process (or local container with bind mounts)
4. `Path.is_dir()` and `Path.glob()` find the files
5. Everything works

In Docker on Hetzner:
1. Web container has isolated filesystem
2. `/opt/rom_lab` only exists on the HOST filesystem, not in container
3. Container's `/opt/` is empty (not mounted)
4. `Path.is_dir()` fails
5. 404 errors

## Summary of Findings

| Finding | Confidence | Details |
|---------|-----------|----------|
| **Page discovery uses repo_path from DB** | High | Code verified in template_loader.py:241 and registry.py:114-122 |
| **repo_path is host filesystem path** | High | Stored as string in council.councils.repo_path |
| **No volume mounts in docker-compose** | High | Scanned deploy/docker-compose.yaml:242-288, no volumes section |
| **Container can't access /opt/** | High | Docker isolation means /opt/ on host ≠ /opt/ in container |
| **Page discovery returns empty list** | High | discover_pages:243 returns [] if pages_dir.is_dir() is false |
| **Static file serving fails** | High | council_static_file:562 raises 404 if full_path.is_file() is false |
| **Both routes use the same pattern** | High | Both call get_council_by_id_sync() then Path(repo_path) |

## Solution Approaches

### Approach A: Mount all downstream repos in docker-compose

Add volumes section to council-web:

```yaml
council-web:
  volumes:
    - /opt/rom_lab:/opt/rom_lab:ro  # Read-only
    - /opt/osrs_hiscore_pull:/opt/osrs_hiscore_pull:ro
    # ... more councils ...
```

**Pros**: Minimal code changes, template_loader already works
**Cons**: Hard-coded volume list, doesn't scale to unknown councils, requires docker-compose edits

### Approach B: Dynamic volume discovery at startup

Create a volume mount discovery system that:
1. Scans DB for all registered councils
2. Generates docker volume mounts on startup
3. Uses docker-compose.yaml templating

**Pros**: Scales to any number of councils
**Cons**: Requires initialization sequence, complex docker-compose setup

### Approach C: Copy custom page assets into container at build time

Modify Dockerfile to:
1. Clone/copy downstream repos during build
2. Bundle .council/web/ directories into image
3. Update repo_path resolution to use in-container paths

**Pros**: No volume mounts needed, everything self-contained
**Cons**: Large image size, repos must be committed to git, defeats "downstream" goal

### Approach D: Serve custom pages via HTTP/API

Instead of filesystem access:
1. Store custom page templates as blobs in DB
2. Serve via REST API endpoint
3. Template loader reads from DB instead of filesystem

**Pros**: Works with any repo location, no volume mounts needed
**Cons**: Major refactor of template_loader, API/DB overhead

## Recommended Next Steps

1. **Validate in Hetzner**: SSH to council-hub, run `docker exec council-web ls /opt/` to confirm empty
2. **Test Approach A**: Add `- /opt/rom_lab:/opt/rom_lab:ro` to docker-compose, rebuild, test page load
3. **Design dynamic approach**: If multiple councils needed, design Approach B properly
4. **Document in deployment guide**: Add warnings about custom page volumes
