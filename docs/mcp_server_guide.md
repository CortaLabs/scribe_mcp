# 🛠️ Building Model Context Protocol (MCP) Servers - Python Edition

## 🎯 What the Hell is MCP Anyway?

Model Context Protocol is Anthropic's way of letting AI assistants talk to external data sources and tools without hard-coding every goddamn integration. Think of it as a standard API that lets Claude (or other LLMs) interact with your databases, filesystems, APIs, or whatever cursed data source you're dealing with.

## 📦 Core Components

### 1. **The Server**
Your MCP server exposes:
- **Resources**: Static or dynamic data (files, database records, etc.)
- **Tools**: Functions the AI can invoke
- **Prompts**: Pre-configured prompt templates

### 2. **The Protocol**
JSON-RPC 2.0 over stdio or HTTP. Because apparently we needed another protocol in our lives.

## 🐍 Python Implementation - The Right Way

### Prerequisites
```bash
./install.sh
source .venv/bin/activate
```
The script creates a virtual environment and installs the packages listed in `requirements.txt` (`mcp`, `asyncpg`, `rich`, `pytest`). If you prefer manual setup, run `pip install -r requirements.txt` inside your own environment.

Copy `.env.example` to `.env` and tweak values (database URL, rate limits, default project) to match your environment.

### Basic Server Structure

```python
from mcp.server import Server
from mcp.types import Resource, Tool, TextContent
import asyncio
import psycopg2
from typing import Any

# Initialize the server
app = Server("your-server-name")

# Connection pool for Postgres (reuse connections, don't be wasteful)
db_config = {
    "dbname": "your_db",
    "user": "your_user",
    "password": "your_pass",
    "host": "localhost",
    "port": 5432
}
```

### 🔧 Implementing Tools

Tools are functions the AI can call. Make them **idempotent** and **safe**.

```python
@app.tool()
async def query_database(query: str, params: list[Any] | None = None) -> str:
    """
    Execute a READ-ONLY SQL query against Postgres.

    Args:
        query: SQL SELECT statement
        params: Optional query parameters

    Returns:
        JSON string of results
    """
    # CRITICAL: Validate it's read-only
    if not query.strip().upper().startswith("SELECT"):
        return "Error: Only SELECT queries allowed, nice try hackerman."

    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()
        cur.execute(query, params or [])

        results = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

        # Return as structured data
        return json.dumps([
            dict(zip(columns, row)) for row in results
        ])

    except Exception as e:
        return f"Query failed: {str(e)}"
    finally:
        if conn:
            conn.close()


@app.tool()
async def get_table_schema(table_name: str) -> str:
    """Get the schema for a specific table."""
    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        cur.execute("""
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """, (table_name,))

        schema = cur.fetchall()
        return json.dumps({
            "table": table_name,
            "columns": [
                {
                    "name": col[0],
                    "type": col[1],
                    "max_length": col[2]
                }
                for col in schema
            ]
        })
    except Exception as e:
        return f"Schema fetch failed: {str(e)}"
    finally:
        if conn:
            conn.close()
```

### 📚 Implementing Resources

Resources provide context data that the AI can read.

```python
@app.resource("db://tables/list")
async def list_tables() -> Resource:
    """Provide a list of all available tables."""
    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        cur.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """)

        tables = [row[0] for row in cur.fetchall()]

        return Resource(
            uri="db://tables/list",
            name="Available Database Tables",
            mimeType="application/json",
            text=json.dumps({"tables": tables})
        )
    except Exception as e:
        return Resource(
            uri="db://tables/list",
            name="Error",
            mimeType="text/plain",
            text=f"Failed to list tables: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@app.resource("db://tables/{table_name}")
async def get_table_data(uri: str) -> Resource:
    """Fetch recent rows from a specific table."""
    table_name = uri.split("/")[-1]

    # Basic SQL injection prevention (validate table name)
    if not table_name.isidentifier():
        return Resource(
            uri=uri,
            name="Error",
            mimeType="text/plain",
            text="Invalid table name"
        )

    conn = None
    try:
        conn = psycopg2.connect(**db_config)
        cur = conn.cursor()

        # Safe because we validated table_name is an identifier
        cur.execute(f"SELECT * FROM {table_name} LIMIT 100;")
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description]

        data = [dict(zip(columns, row)) for row in rows]

        return Resource(
            uri=uri,
            name=f"Table: {table_name}",
            mimeType="application/json",
            text=json.dumps(data)
        )
    except Exception as e:
        return Resource(
            uri=uri,
            name="Error",
            mimeType="text/plain",
            text=f"Failed to fetch table data: {str(e)}"
        )
    finally:
        if conn:
            conn.close()
```

### 🚀 Running the Server

```python
async def main():
    # Run the server on stdio (standard for MCP)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
```

## 🔒 Security Best Practices

### 1. **Input Validation**
```python
def sanitize_table_name(name: str) -> str:
    """Only allow alphanumeric and underscores."""
    if not name.replace("_", "").isalnum():
        raise ValueError("Invalid table name")
    return name
```

### 2. **Use Connection Pooling**
```python
from psycopg2 import pool

connection_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20,  # min and max connections
    **db_config
)

def get_connection():
    return connection_pool.getconn()

def return_connection(conn):
    connection_pool.putconn(conn)
```

### 3. **Rate Limiting**
```python
from collections import defaultdict
from time import time

rate_limits = defaultdict(list)

def rate_limit(key: str, max_requests: int, window: int) -> bool:
    """Simple rate limiter."""
    now = time()
    rate_limits[key] = [t for t in rate_limits[key] if now - t < window]

    if len(rate_limits[key]) >= max_requests:
        return False

    rate_limits[key].append(now)
    return True
```

### 4. **Read-Only Queries**
```python
def is_read_only(query: str) -> bool:
    """Validate query is read-only."""
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"]
    query_upper = query.strip().upper()
    return not any(cmd in query_upper for cmd in dangerous)
```

## 📝 Configuration File

Create `mcp-server-config.json`:

```json
{
  "mcpServers": {
    "postgres-server": {
      "command": "python",
      "args": ["path/to/your_mcp_server.py"],
      "env": {
        "DB_NAME": "your_db",
        "DB_USER": "your_user",
        "DB_PASSWORD": "your_pass",
        "DB_HOST": "localhost",
        "DB_PORT": "5432"
      }
    }
  }
}
```

## 🎯 Pro Tips

1. **Always use async** - MCP servers should be async-first
2. **Handle errors gracefully** - Don't crash, return error messages
3. **Log everything** - You'll thank yourself later
4. **Test with real Claude interactions** - The AI will do weird shit
5. **Document your tools** - The AI reads your docstrings
6. **Connection pooling is mandatory** - Don't open a new connection per request
7. **Validate EVERYTHING** - Trust nothing from the AI
8. **Keep tools atomic** - One clear purpose per tool

## 🐛 Common Pitfalls

- **Blocking I/O**: Use async libraries (asyncpg instead of psycopg2)
- **No connection pooling**: You'll run out of connections fast
- **Overly complex tools**: Keep them simple and composable
- **Poor error messages**: The AI needs context to fix issues
- **No timeout handling**: Set query timeouts

## 📊 Example: Complete Server

```python
import asyncio
import json
import asyncpg
from mcp.server import Server
from mcp.types import Resource, Tool

app = Server("postgres-mcp")
db_pool = None

async def init_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(
        host='localhost',
        database='your_db',
        user='your_user',
        password='your_pass',
        min_size=1,
        max_size=10
    )

@app.tool()
async def query(sql: str) -> str:
    """Execute read-only SQL query."""
    if not sql.strip().upper().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT allowed"})

    async with db_pool.acquire() as conn:
        try:
            rows = await conn.fetch(sql)
            return json.dumps([dict(row) for row in rows])
        except Exception as e:
            return json.dumps({"error": str(e)})

@app.resource("db://schema")
async def schema() -> Resource:
    """Get complete database schema."""
    async with db_pool.acquire() as conn:
        tables = await conn.fetch("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public'
        """)
        return Resource(
            uri="db://schema",
            name="Database Schema",
            mimeType="application/json",
            text=json.dumps([t['table_name'] for t in tables])
        )

async def main():
    await init_pool()
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())
    await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## 🚀 Quickstart

### Direct Tool Invocation
```python
import asyncio
from scribe_mcp.tools import set_project, append_entry

async def main():
    await set_project.set_project(name="demo", root=".")
    await append_entry.append_entry(
        message="Hello from Scribe",
        status="info",
        meta={"component": "demo"},
    )

asyncio.run(main())
```

### Run as MCP Server (stdio)
```bash
source .venv/bin/activate
python -m MCP_SPINE.scribe_mcp.server
```
Configure your MCP-compatible client (Claude Code, etc.) to execute the command above for stdio transport.

### Project Configuration
Store project definitions under `config/projects/<name>.json`:

```json
{
  "name": "scribe_mcp",
  "root": ".",
  "progress_log": "docs/dev_plans/scribe_mcp/PROGRESS_LOG.md",
  "docs_dir": "docs/dev_plans/scribe_mcp",
  "defaults": { "emoji": "ℹ️", "agent": "Scribe" }
}
```
List available projects with `python scripts/scribe.py --list-projects` and select one via `--project <name>` or by setting `SCRIBE_DEFAULT_PROJECT` in `.env`.

## 🎨 Optional Rich UI Modules

The `example_code/modules/` directory contains reusable Rich-based UI components (menus, tables, progress bars, prompts) originally built for the Sanctum project. They are not wired into the Scribe MCP server yet, but can be adopted later for richer CLI output. See `example_code/modules/ui_readme.md` for details.

## 🎓 Additional Resources

- Official MCP Spec: https://spec.modelcontextprotocol.io/
- Anthropic MCP Docs: https://docs.anthropic.com/
- asyncpg docs: https://magicstack.github.io/asyncpg/

---

## 🗄️ Scribe Storage Strategy (Hybrid)

Scribe’s MCP server now targets a **hybrid storage stack**:

- **SQLite by default** for zero-dependency local installs. It excels at append-heavy workloads, ships in Python’s stdlib, and keeps first-run setup painless.
- **PostgreSQL opt-in** via `SCRIBE_DB_URL` when teams need shared dashboards, multi-user access, or external analytics. Existing asyncpg helpers stay relevant.
- A thin `StorageBackend` abstraction lets tools stay agnostic—log append, metrics, and queries call into a driver that picks SQLite or Postgres based on config.

### Next Moves
1. **Design storage interface** (`StorageBackend` + factory) and migrate current DB helpers onto it.
2. **Implement SQLite backend** (probably `aiosqlite`) mirroring Postgres behaviour: projects table, entries table, metrics view.
3. **Refine Postgres backend** to match the interface, centralising hash/metrics logic already in place.
4. **Config UX**: expose `scribe.storage` settings in `settings.py` so MCP clients know which backend is active and where the DB file lives.
5. **Testing matrix**: extend the new test suite with parametrised fixtures to validate both backends (Austin-run locally while sandbox settles).

Defaulting to SQLite keeps “drop-in logging” fast, while the Postgres path remains available for the larger telemetry story. Now go build something that doesn’t suck—with the right database for the job.

---

Now go build something that doesn't suck.
