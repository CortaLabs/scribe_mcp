---
id: council_env_enforcement-phase-plan
title: "\u2699\uFE0F Phase Plan \u2014 council_env_enforcement"
doc_type: phase_plan
doc_name: phase_plan
category: engineering
status: draft
version: '0.1'
last_updated: 2026-02-18 07:35:10 UTC
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---

# ⚙️ Phase Plan — council_env_enforcement
**Author:** Scribe
**Version:** Draft v0.1
**Status:** active
**Last Updated:** 2026-02-18 07:17:54 UTC

> Execution roadmap for council_env_enforcement.

---
## Phase Overview
<!-- ID: phase_overview -->
| Phase | Goal | Key Deliverables | Est. Sessions |
|-------|------|------------------|---------------|
| Phase 1 | Schema Module + Validation | `env_schema.py` with full EnvVar registry + `validate_env()` + `__main__` entry point | 1 |
| Phase 2 | CLI Commands + Scanner | `env_cmd.py` with `council env check/generate/validate` + source scanner | 1 |
| Phase 3 | Startup Hooks + Entrypoint | Integration into `council start` + `docker-entrypoint.sh` | 1 |
| Phase 4 | .env.example Regeneration + Tests | Generate fresh .env.example files from schema + comprehensive tests | 1 |
<!-- ID: phase_0 -->
**Scope**: Create the `env_schema.py` module containing the `EnvVar` dataclass, the complete `ENV_SCHEMA` registry, `validate_env()`, `validate_env_or_exit()`, and `__main__` entry point.

**Files to Create**:
- `src/council_mcp/config/env_schema.py`

**Files to NOT Touch**:
- `src/council_mcp/config/__init__.py`
- `src/council_mcp/cli/start_cmd.py`
- `deploy/docker-entrypoint.sh`
- Any `.env.example` files

**Dependencies**: None (first task)

### Specifications

1. Create `src/council_mcp/config/env_schema.py` with:
   - `EnvVar` frozen dataclass with fields: `name: str`, `required: bool = False`, `default_local: str = ""`, `default_docker: str = ""`, `description: str = ""`, `group: str = "Other"`, `owner: str = "council"`, `secret: bool = False`, `conditional: str = ""`, `include_in_dotenv: bool = True`
   - `ENV_SCHEMA: list[EnvVar]` containing ALL variables from ARCHITECTURE_GUIDE section 4.1 (copy the full list verbatim)
   - `validate_env(context: str = "local", schema: list[EnvVar] | None = None) -> list[str]` per section 4.2
   - `validate_env_or_exit(context: str = "local") -> None` per section 4.2 (respects `COUNCIL_SKIP_ENV_CHECK=1`)
   - `if __name__ == "__main__"` block with argparse per section 4.9

2. The module MUST have zero external dependencies beyond stdlib. No Click, no yaml, no agentkit imports. Only `os`, `sys`, `argparse`, `dataclasses`, `typing`.

3. The `ENV_SCHEMA` list MUST contain every variable from the architecture guide section 4.1, with exactly the field values specified there. Do NOT omit any entries or change any field values.

### Verification
- [x] `python -c "from council_mcp.config.env_schema import ENV_SCHEMA; print(f'{len(ENV_SCHEMA)} vars registered')"` prints count >= 75 -- **PASS: 85 vars registered**
- [x] `python -c "from council_mcp.config.env_schema import validate_env; print(validate_env())"` runs without error -- **PASS: returns list of 3 missing required vars**
- [x] `python -m council_mcp.config.env_schema validate --context local` runs (may show errors for missing vars, that is expected) -- **PASS: exits 1 with formatted error listing**
- [x] `python -c "from council_mcp.config.env_schema import EnvVar; v = EnvVar(name='TEST'); print(v.include_in_dotenv)"` prints True -- **PASS: prints True**

### Out of Scope (DO NOT TOUCH)
- CLI command registration
- startup_cmd.py modifications
- docker-entrypoint.sh modifications
- .env.example file generation
- Test files
<!-- ID: phase_1 -->
**Scope**: Create the `council env` CLI command group with `check`, `generate`, and `validate` subcommands plus the `scan_env_reads()` source scanner.

**Files to Create**:
- `src/council_mcp/cli/env_cmd.py`

**Files to Modify**:
- `src/council_mcp/cli/main.py` (register `env` command group)

**Files to NOT Touch**:
- `src/council_mcp/config/env_schema.py` (created in Task 1)
- `src/council_mcp/cli/start_cmd.py`
- `deploy/docker-entrypoint.sh`
- Any `.env.example` files

**Dependencies**: Task Package 1 (env_schema.py must exist)

### Specifications

1. Create `src/council_mcp/cli/env_cmd.py` with:

   a. `scan_env_reads(src_dir: Path) -> set[str]` function per ARCHITECTURE_GUIDE section 4.4:
      - Regex patterns for `os.getenv("VAR")`, `os.environ.get("VAR")`, `os.environ["VAR"]`
      - Returns set of variable names found
      - Scans all `*.py` files recursively under `src_dir`

   b. `generate_dotenv(context: str, schema: list[EnvVar]) -> str` function:
      - Groups variables by `var.group`
      - Only includes vars where `include_in_dotenv=True`
      - Uses `default_local` when context="local", `default_docker` when context="docker"
      - Secret vars render as `VAR_NAME=  # description`
      - Non-secret vars with defaults render as `VAR_NAME=default  # description`
      - Required vars get `# REQUIRED` prefix in description
      - Outputs header with "Generated by: council env generate --context {context}"
      - Returns the full file content as a string

   c. `@click.group() def env()` command group

   d. `@env.command() def check(strict)` subcommand:
      - Calls `scan_env_reads(src_dir)` where `src_dir` is auto-detected from repo root
      - Compares against `ENV_SCHEMA` names
      - Ignores vars where `owner="system"`
      - Reports: undeclared reads (in code but not schema), unused declarations (in schema but not code, only if `include_in_dotenv=True`)
      - `--strict` flag: exit 1 on any drift
      - Normal mode: exit 0 with warnings

   e. `@env.command() def generate(context, target, output)` subcommand:
      - Calls `generate_dotenv()` with appropriate context
      - `--target root` writes to `{repo_root}/.env.example`
      - `--target deploy` writes to `{repo_root}/deploy/.env.example`
      - `--target scaffold` writes to `{repo_root}/.council/.env.example`
      - `--output` overrides target path
      - Prints confirmation with path and var count

   f. `@env.command() def validate(context)` subcommand:
      - Calls `validate_env(context=context)` from env_schema
      - Reports results in human-readable format
      - Exit 0 if valid, 1 if missing vars

2. Modify `src/council_mcp/cli/main.py`:
   - Import and register the `env` command group: `from council_mcp.cli.env_cmd import env` and `cli.add_command(env)`
   - Follow the existing pattern used by other command groups (e.g., `roster`, `mcp`, `db`)

### Verification
- [x] `council env --help` shows check, generate, validate subcommands (VERIFIED)
- [x] `council env validate --context local` runs and reports missing vars (VERIFIED: reports 3 missing required vars)
- [x] `council env check` runs and reports any code/schema drift (VERIFIED: 66 undeclared + 46 unused)
- [x] `council env generate --context local --output /tmp/test.env.example` produces a valid file with grouped sections (VERIFIED: 49 vars)
- [x] `council env generate --context docker --output /tmp/test-docker.env.example` produces file with Docker-specific defaults (VERIFIED: POSTGRES_HOST=postgres)

**Status: COMPLETE** (Forge, 2026-02-18)

### Out of Scope (DO NOT TOUCH)
- `env_schema.py` (already created)
- `start_cmd.py` (Task 3)
- `docker-entrypoint.sh` (Task 3)
- Actual `.env.example` files (Task 4)
<!-- ID: milestone_tracking -->
**Scope**: Wire env validation into `council start` and `docker-entrypoint.sh` so missing required vars cause fail-fast at boot time.

**Files to Modify**:
- `src/council_mcp/cli/start_cmd.py` (add `validate_env_or_exit()` call)
- `deploy/docker-entrypoint.sh` (add validation call after secret loading)

**Files to NOT Touch**:
- `src/council_mcp/config/env_schema.py` (created in Task 1)
- `src/council_mcp/cli/env_cmd.py` (created in Task 2)
- `src/council_mcp/cli/main.py` (modified in Task 2)
- Any `.env.example` files

**Dependencies**: Task Package 1 (env_schema.py must exist)

### Specifications

1. Modify `src/council_mcp/cli/start_cmd.py`:
   - Import: `from council_mcp.config.env_schema import validate_env_or_exit`
   - In the `start()` function (line ~104-139), add `validate_env_or_exit(context="local")` AFTER the remote deployment check but BEFORE `_start_background()` or `_start_foreground()` is called
   - The validation must run regardless of whether `--background` or `--foreground` mode is used
   - The existing `_validate_remote_startup()` logic stays unchanged

2. Modify `deploy/docker-entrypoint.sh`:
   - Add validation block after the admin credential derivation (line ~110) and BEFORE the auto-bootstrap section (line ~139)
   - The validation block must:
     ```bash
     # --- Validate required environment variables ---
     echo "[entrypoint] Validating environment variables..."
     if ! python -m council_mcp.config.env_schema validate --context docker 2>&1; then
         echo "[entrypoint] ERROR: Environment validation failed. See above." >&2
         exit 1
     fi
     echo "[entrypoint] Environment validation passed."
     ```
   - This ensures secrets are loaded from Docker secrets BEFORE validation runs
   - If validation fails, the container exits before bootstrap, preventing partial initialization

### Verification
- [x] `COUNCIL_SKIP_ENV_CHECK=1 council start --foreground` starts normally (escape hatch works) -- VERIFIED: validate_env_or_exit returns immediately when COUNCIL_SKIP_ENV_CHECK=1
- [x] With DATABASE_URL unset: `council start` prints formatted error listing missing vars and exits non-zero -- VERIFIED: validate_env returns 3 errors (DATABASE_URL, POSTGRES_APP_USER, POSTGRES_APP_PASSWORD), validate_env_or_exit calls sys.exit(1)
- [x] `docker-entrypoint.sh` contains the validation block after secret loading -- VERIFIED: lines 112-118, after POSTGRES_ADMIN_* (line 110), before auto-bootstrap (line 121)
- [x] The validation block in docker-entrypoint.sh calls `python -m council_mcp.config.env_schema validate --context docker` -- VERIFIED: line 114

**Status: COMPLETE** (Forge, 2026-02-18)

### Out of Scope (DO NOT TOUCH)
- env_schema.py
- env_cmd.py
- .env.example files
- Test files


---
## Task Package 4: .env.example Regeneration + Unit Tests

**Scope**: Use `council env generate` to regenerate all `.env.example` files from the schema, then write comprehensive unit tests for the entire env enforcement system.

**Files to Modify**:
- `.env.example` (regenerated from schema)
- `deploy/.env.example` (regenerated from schema)

**Files to Create**:
- `tests/test_env_schema.py`

**Files to NOT Touch**:
- `src/council_mcp/config/env_schema.py` (created in Task 1)
- `src/council_mcp/cli/env_cmd.py` (created in Task 2)
- `src/council_mcp/cli/start_cmd.py` (modified in Task 3)
- `deploy/docker-entrypoint.sh` (modified in Task 3)

**Dependencies**: Task Packages 1-3 (all must be complete)

### Specifications

1. Regenerate `.env.example` files:
   - Run `council env generate --context local --target root` to regenerate `.env.example`
   - Run `council env generate --context docker --target deploy` to regenerate `deploy/.env.example`
   - Verify both files have the correct header, grouping, and context-appropriate defaults
   - Verify deploy version has Docker-specific defaults (postgres hostname, council user, etc.)

2. Create `tests/test_env_schema.py` with:

   a. Schema integrity tests:
      - `test_schema_has_minimum_vars()`: Assert `len(ENV_SCHEMA) >= 75`
      - `test_no_duplicate_names()`: Assert all `var.name` values are unique
      - `test_all_required_vars_have_descriptions()`: All `required=True` vars have non-empty `description`
      - `test_secret_vars_have_no_defaults_in_dotenv()`: All `secret=True` vars with `include_in_dotenv=True` render with empty values
      - `test_owner_values_valid()`: All `owner` values are in `{"council", "agentkit", "scribe", "docker", "system"}`
      - `test_system_vars_not_in_dotenv()`: All `owner="system"` vars have `include_in_dotenv=False`

   b. Validation tests:
      - `test_validate_env_all_set()`: Set all required vars in env, assert empty errors list
      - `test_validate_env_missing_required()`: Unset required vars, assert error messages contain var names
      - `test_validate_env_skip_check()`: Set `COUNCIL_SKIP_ENV_CHECK=1`, assert `validate_env_or_exit()` returns without error
      - `test_validate_env_context_docker()`: Verify context flag changes hint messages

   c. Scanner tests (if scan_env_reads is importable):
      - `test_scan_finds_getenv()`: Create temp file with `os.getenv("TEST_VAR")`, assert "TEST_VAR" in results
      - `test_scan_finds_environ_get()`: Create temp file with `os.environ.get("TEST_VAR")`, assert found
      - `test_scan_finds_environ_bracket()`: Create temp file with `os.environ["TEST_VAR"]`, assert found
      - `test_scan_ignores_dynamic()`: Create temp file with `os.getenv(f"{prefix}_KEY")`, assert NOT found

   d. Generator tests (if generate_dotenv is importable):
      - `test_generate_local_context()`: Assert output contains local defaults
      - `test_generate_docker_context()`: Assert output contains Docker defaults
      - `test_generate_excludes_non_dotenv()`: Assert vars with `include_in_dotenv=False` are NOT in output
      - `test_generate_groups_by_section()`: Assert output has section headers matching group names

   e. All tests MUST use the `test_agent` fixture pattern where applicable (for any council operations). For pure env_schema tests, no fixture needed.

### Verification
- [ ] `pytest tests/test_env_schema.py -v` passes all tests
- [ ] `.env.example` has "Generated by" header
- [ ] `deploy/.env.example` has Docker-specific defaults (e.g., `POSTGRES_HOST=postgres`)
- [ ] Both `.env.example` files have identical variable SETS (same names, different defaults)
- [ ] `council env check --strict` passes with exit code 0 against the new .env.example files

### Out of Scope (DO NOT TOUCH)
- Source modules (already complete from Tasks 1-3)
- docker-compose.yaml
- Any Python source files outside tests/
<!-- ID: retro_notes -->
- Summarise lessons learned after each phase completes.  
- Document any scope changes or re-planning decisions here.


---