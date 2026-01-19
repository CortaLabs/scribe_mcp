## Core Project Management

### `set_project`
**Purpose**: Create/select a project and bootstrap documentation structure.

**Required Parameters:**
- `name` (string): Project name

**Optional Parameters:**
- `root` (string): Project root directory (defaults to current directory)
- `progress_log` (string): Path to progress log file
- `defaults` (dict): Default settings for the project

**Example Usage:**
```python
# Basic usage
await set_project(name="my-project")

# With custom defaults
await set_project(
    name="my-project",
    defaults={"emoji": "🧪", "agent": "MyAgent"}
)
```

**Returns:**
```json
{
  "ok": true,
  "project": {
    "name": "my-project",
    "root": "/path/to/project",
    "progress_log": "/path/to/progress/log.md",
    "docs_dir": "/path/to/docs",
    "docs": {
      "architecture": "/path/to/ARCHITECTURE_GUIDE.md",
      "phase_plan": "/path/to/PHASE_PLAN.md",
      "checklist": "/path/to/CHECKLIST.md",
      "progress_log": "/path/to/PROGRESS_LOG.md"
    },
    "defaults": {"agent": "Scribe"},
    "author": "Scribe"
  }
}
```

### `get_project`
**Purpose**: Retrieve current active project context and configuration.

**Parameters:** None

**Example Usage:**
```python
await get_project()
```

**Returns:**
```json
{
  "ok": true,
  "project": {
    "name": "current-project",
    "root": "/path/to/project",
    "progress_log": "/path/to/log.md",
    "docs_dir": "/path/to/docs",
    "defaults": {"agent": "Scribe"},
    "author": "Scribe"
  }
}
```

### `list_projects`
**Purpose**: Discover available projects and their configurations.

**Optional Parameters:**
- `limit` (int, default: 5): Maximum number of projects to return
- `filter` (string): Filter projects by name (case-insensitive)
- `compact` (bool): Use compact response format
- `fields` (list): Specific fields to include in response
- `include_test` (bool, default: false): Include test/temp projects
- `page` (int, default: 1): Page number for pagination
- `page_size` (int): Number of items per page

**Example Usage:**
```python
# Basic usage
await list_projects()

# With pagination
await list_projects(limit=10, page=1)

# Filtered search
await list_projects(filter="my-project", limit=3)
```

**Returns:**
```json
{
  "ok": true,
  "projects": [
    {
      "name": "project-name",
      "root": "/path/to/project",
      "progress_log": "/path/to/log.md"
    }
  ],
  "count": 1,
  "pagination": {
    "page": 1,
    "page_size": 5,
    "total_count": 10,
    "has_next": true,
    "has_prev": false
  }
}
```

---
