---
id: query_enhancement_suite-project-brief
title: "Query Enhancement Suite \u2014 Project Brief"
doc_name: PROJECT_BRIEF
category: engineering
status: draft
version: '0.1'
last_updated: '2026-02-01'
maintained_by: Corta Labs
created_by: Corta Labs
owners: []
related_docs: []
tags: []
summary: ''
---
# Query Enhancement Suite — Project Brief

## Vision
Scribe's query tools (query_entries, read_recent, get_project) are solid for single-project workflows. But as Scribe gets used across multiple projects in a repo (and now in Council_MCP), we need **cross-project visibility** and **graceful behavior** when no project is set.

## Problems to Solve

### 1. Cross-Project Agent Search
- "What did CoderAgent do across all projects in this repo?" — currently impossible without manually switching projects
- query_entries has `search_scope="all_projects"` but it's underutilized and the agent filter is project-scoped
- Want: easy filtering by agent name across all repo projects, with per-project grouping

### 2. Graceful No-Project Responses
- read_recent and get_project throw errors when no project is set
- They SHOULD return useful info: recent projects in this repo, last activity, suggested next steps
- The data is there (we already show `last_known_project` in some errors) — just surface it properly

### 3. Session-Aware Filtering
- Council_MCP has a session mapping system that tracks agent sessions
- We should investigate what they do and see if their patterns can inform our querying
- Could enable: "show me everything from this session" or "what sessions has this agent had?"

## Design Constraints
- **No new tools** — enhance existing tool schemas
- **Minimal schema changes** — add optional params, don't break existing calls
- **Intuitive** — if you have to read docs to use the filter, it's too complex
- **Backward compatible** — every existing call must work identically

## Research Questions
1. What does query_entries currently support? Where are the gaps?
2. How does the storage backend handle cross-project queries?
3. How does Council_MCP map sessions? What can we learn?
4. What would the ideal filter UX look like for cross-project agent search?

## Success Criteria
- `query_entries(agent='X', search_scope='all_projects', agents=['CoderAgent'])` returns grouped results
- `read_recent(agent='X')` with no project set returns recent activity across repo
- `get_project(agent='X')` with no project set returns a useful project list instead of an error
- Zero breaking changes to existing callers
