# Project Naming Guidelines

## 🔄 Automatic Name Normalization

Project names are **automatically normalized** at all tool boundaries. You can use any reasonable format:

| Input Format | Normalized To |
|--------------|---------------|
| `my-project` | `my_project` |
| `My Project` | `my_project` |
| `MY-PROJECT` | `my_project` |
| `My_Project Name` | `my_project_name` |

**What this means:**
- Hyphens, spaces, and mixed case are all accepted
- Lookups work regardless of input format: `get_project(project="My-Project")` finds `my_project`
- Storage uses canonical underscore_lowercase format
- **Collision detection**: Creating `my-project` when `my_project` exists will warn you

## ⚠️ Reserved Project Names and Patterns

The Scribe MCP system includes automatic temp project detection to prevent auto-switching to test projects during development.

### Reserved Keywords (DO NOT USE in real project names)

```
test, temp, tmp, demo, sample, example
mock, fake, dummy, trial, experiment
```

### Reserved Patterns (DO NOT USE for real projects)

- **UUID Suffixes:** `project-xxxxxxxx` (8+ character suffixes)
- **Numeric Suffixes:** `project-123`, `test_001`
- **Any project name containing reserved keywords**

### Examples

#### ✅ Real Projects (these will work correctly)
- `my-project`
- `production-app`
- `client-work-2024`
- `enhanced-log-rotation`
- `authentication-system`

#### ❌ Test/Temp Projects (these will be auto-skipped)
- `test-project`
- `temp-project`
- `demo-project-123`
- `history-test-711f48a0` (UUID pattern)
- `project-456` (numeric suffix)

### Implementation Details

The `_is_temp_project()` function in `scribe_mcp/tools/project_utils.py` implements this logic using simple NLP pattern matching:

- **Keyword Detection:** Scans for reserved keywords in project names
- **UUID Detection:** Identifies long hexadecimal suffixes common in test isolation
- **Numeric Suffix Detection:** Catches common test numbering patterns

### Why This Exists

This prevents the MCP system from automatically switching to test projects during development, ensuring that:
1. Real work stays focused on production projects
2. Test isolation remains robust
3. Developers don't accidentally log work to test projects

### Need a Test Project?

If you need to create a test project that will be recognized, use names like:
- `my-first-real-project`
- `learning-scribe-mcp`
- `personal-work-tracker`

Or explicitly set the project using `set_project()` to bypass auto-detection.