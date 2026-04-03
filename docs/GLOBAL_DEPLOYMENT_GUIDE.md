---
id: scribe_sentinel_concurrency_v1-global_deployment_guide
title: Global Scribe Deployment Guide
doc_type: global_deployment_guide
category: engineering
status: draft
version: '0.1'
last_updated: '2026-03-21'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Global Scribe Deployment Guide

This guide covers deploying Scribe as a **global MCP server** that can automatically discover and work with any repository without requiring per-repository installation.

## Overview

Scribe can now operate in two deployment modes:

1. **Global Mode (Recommended)**: Single Scribe installation that automatically detects and adapts to any repository
2. **Embedded Mode**: Scribe embedded within each repository (legacy approach)

This guide focuses on **Global Mode** deployment.

## Architecture

### Repository Discovery
Scribe automatically discovers repositories by looking for:
- `.git` directory (Git repositories)
- `.scribe` directory (Scribe-specific marker)
- `pyproject.toml` (Python projects)
- `package.json` (Node.js projects)
- `Cargo.toml` (Rust projects)
- `go.mod` (Go projects)

### Per-Repository Configuration
Each repository can have its own configuration via `.scribe/config/scribe.yaml`:
```yaml
repo_slug: my-project
dev_plans_dir: .scribe/docs/dev_plans  # Canonical default; keep docs/dev_plans only for legacy/back-compat repos
progress_log_name: PROGRESS_LOG.md
permissions:
  allow_rotate: true
  allow_generate_docs: true
default_emoji: "📋"
default_agent: "Agent"
```

### Security and Isolation
- **Path Sandboxing**: Operations are restricted to repository boundaries
- **Permission Checks**: Repository-specific permissions control allowed operations
- **Plugin Isolation**: Plugins are loaded per-repository with proper isolation

## Installation

### 1. Install Scribe Once
```bash
# Clone Scribe repository
git clone <scribe-repo-url> scribe-mcp
cd scribe-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure MCP Client
Add Scribe to your MCP client configuration:

#### Claude Desktop/Code
```json
{
  "mcpServers": {
    "scribe": {
      "command": "python",
      "args": ["-m", "scribe_mcp.server"],
      "env": {
        "SCRIBE_ROOT": "/path/to/scribe-mcp",
        "SCRIBE_STORAGE_BACKEND": "sqlite"
      }
    }
  }
}
```

#### Codex CLI
```bash
codex mcp add scribe \
  --env SCRIBE_ROOT=/path/to/scribe-mcp \
  --env SCRIBE_STORAGE_BACKEND=sqlite \
  -- python -m scribe_mcp.server
```

### 3. Verify Installation
```bash
# Test the server
python demo/demo_global_scribe.py

# Run health check
python demo/test_global_scribe.py
```

## Repository Setup

### Automatic Initialization
When Scribe is used in a new repository, it will:
1. Automatically detect the repository
2. Create default configuration if needed
3. Set up basic directory structure
4. Initialize security sandbox

### Manual Initialization
For more control over repository setup:

```bash
# Initialize in current directory
python -m scribe_mcp.scripts.scribe_cli init

# Initialize in specific directory
python -m scribe_mcp.scripts.scribe_cli init --path /path/to/project

# Force reinitialization
python -m scribe_mcp.scripts.scribe_cli init --force
```

### Configuration Options
Create `.scribe/config/scribe.yaml` in your repository:

```yaml
# Repository identification
repo_slug: my-project  # Auto-detected if not specified

# Documentation structure
dev_plans_dir: .scribe/docs/dev_plans  # Canonical default; set docs/dev_plans only when preserving a legacy tree
progress_log_name: PROGRESS_LOG.md

# Template configuration
templates_pack: default
custom_templates_dir: .scribe/templates

# Permissions
permissions:
  allow_rotate: true
  allow_generate_docs: true
  require_project: true

# Plugin configuration
plugins_dir: .scribe/plugins

# Default values
default_emoji: "📋"
default_agent: "Agent"

# Reminder configuration
reminder_config:
  tone: "friendly"
  log_warning_minutes: 15
  log_urgent_minutes: 30

# Storage backend (overrides global setting)
storage_backend: "sqlite"
```

## Multi-Repository Usage

### Scenario 1: Different Projects
Scribe automatically maintains separate contexts for each repository:

```bash
# In project-a
cd ~/projects/project-a
# Scribe automatically detects and uses project-a configuration

# In project-b
cd ~/projects/project-b
# Scribe automatically switches to project-b configuration
```

### Scenario 2: Monorepo Structure
For monorepos with multiple subprojects:

```yaml
# .scribe/config/scribe.yaml
repo_slug: my-monorepo
dev_plans_dir: .scribe/docs/dev_plans
permissions:
  allow_rotate: true
```

### Scenario 3: Mixed Repositories
Different repositories can have completely different configurations:

**Frontend Project** (`.scribe/config/scribe.yaml`):
```yaml
repo_slug: frontend-app
default_emoji: "🎨"
dev_plans_dir: documentation
permissions:
  allow_rotate: true
```

**Backend Project** (`.scribe/config/scribe.yaml`):
```yaml
repo_slug: backend-api
default_emoji: "⚙️"
dev_plans_dir: docs
permissions:
  allow_rotate: false
```

## CLI Utilities

### scribe-cli
Command-line utility for managing Scribe repositories:

```bash
# Initialize repository
python -m scribe_mcp.scripts.scribe_cli init

# Diagnose setup issues
python -m scribe_mcp.scripts.scribe_cli doctor

# Show current status
python -m scribe_mcp.scripts.scribe_cli status

# Switch to different repository
python -m scribe_mcp.scripts.scribe_cli use /path/to/other/repo
```

### Common Commands

#### Doctor
Run comprehensive diagnostics:
```bash
python -m scribe_mcp.scripts.scribe_cli doctor
```
Output:
```
🔍 Scribe Doctor - Diagnosing your setup...

1. Repository Discovery:
   ✅ Found repository root: /home/user/my-project

2. Configuration:
   ✅ Loaded configuration for repo: my-project
   📁 Dev plans directory: /home/user/my-project/.scribe/docs/dev_plans
   📄 Progress log name: PROGRESS_LOG.md

3. Directory Structure:
   ✅ /home/user/my-project/.scribe/docs/dev_plans

4. Permissions:
   ✅ read
   ✅ append
   ✅ rotate
   ✅ generate_docs

🎉 Diagnosis complete!
```

#### Status
Show current repository status:
```bash
python -m scribe_mcp.scripts.scribe_cli status
```
Output:
```
📊 Scribe Status
   Repository: my-project
   Root: /home/user/my-project
   Storage: sqlite
   Plugins: 2 plugin(s)
   Last entry: 🔧 Fixed authentication bug...
```

## Plugin System

### Creating Plugins
Add custom functionality via repository-specific plugins:

1. Create `.scribe/plugins/` directory
2. Add Python files with plugin classes

Example plugin (`.scribe/plugins/custom_policy.py`):
```python
from scribe_mcp.plugins.registry import PolicyPlugin

class CustomPolicyPlugin(PolicyPlugin):
    name = "custom-policy"
    version = "1.0.0"
    description = "Custom validation rules"

    def initialize(self, config):
        self.config = config

    def check_permission(self, operation, context):
        # Custom permission logic
        if operation == "rotate" and context.get("is_friday"):
            return False
        return True

    def validate_entry(self, entry_data):
        # Custom validation
        if not entry_data.get("component"):
            return "Component field is required"
        return None
```

### Plugin Types
- **TemplatePlugin**: Custom document templates
- **PolicyPlugin**: Validation rules and permissions
- **FormatterPlugin**: Custom entry formatting
- **HookPlugin**: Custom workflow hooks

## Troubleshooting

### Common Issues

#### Repository Not Found
**Error**: `Could not find repository root`
**Solution**: Ensure your directory has a `.git` directory or `.scribe` marker

```bash
# Initialize git repository
git init

# Or add Scribe marker
mkdir .scribe
```

#### Configuration Not Loading
**Error**: `Failed to load configuration`
**Solution**: Check YAML syntax and file permissions

```bash
# Validate YAML
python -c "import yaml; yaml.safe_load(open('.scribe/config/scribe.yaml'))"

# Check permissions
ls -la .scribe/config/scribe.yaml
```

#### Permission Denied
**Error**: `PermissionError: Operation not allowed`
**Solution**: Check repository permissions in configuration

```bash
# Run doctor to diagnose
python -m scribe_mcp.scripts.scribe_cli doctor
```

### Debug Mode
Enable debug logging:

```bash
export SCRIBE_DEBUG=true
python -m scribe_mcp.server
```

### Log Files
Scribe logs to:
- Console output (server startup/errors)
- Repository-specific progress logs
- Optional external logging if configured

## Migration from Embedded Mode

### From Embedded to Global
1. Install Scribe globally once
2. Remove embedded Scribe from repositories
3. Add `.scribe/config/scribe.yaml` to repositories that need custom configuration
4. Update MCP client configuration to point to global installation

### Preserving Data
Migrate existing data:
1. Export existing progress logs
2. Back up database files
3. Import into global Scribe installation

## Security Considerations

### Path Sandboxing
Scribe restricts operations to repository boundaries:
- Cannot access files outside repository
- Cannot traverse to parent directories
- Cannot access system files

### Permission System
Repository-specific permissions control:
- `allow_rotate`: Log rotation permissions
- `allow_generate_docs`: Document generation permissions
- `require_project`: Whether project selection is required
- Custom permissions via plugins

### Plugin Security
- Plugins run in repository context
- No access to other repositories
- Plugin validation and error handling

## Performance

### Startup Time
- Repository discovery: <100ms
- Configuration loading: <50ms
- Plugin initialization: <200ms per plugin

### Memory Usage
- Base memory: ~50MB
- Per-repository cache: ~10MB
- Plugin memory: Variable

### Storage
- SQLite: Single database file
- PostgreSQL: Shared database instance
- Config files: <10KB per repository

## Support

### Getting Help
1. Run `python -m scribe_mcp.scripts.scribe_cli doctor` for diagnostics
2. Check the demo scripts for working examples
3. Review the troubleshooting section

### Contributing
1. Test changes with `python demo/test_global_scribe.py`
2. Update documentation
3. Ensure backward compatibility

---

**Scribe Global Deployment** provides a seamless, secure, and scalable way to manage project documentation across multiple repositories with automatic discovery and per-repository customization.
