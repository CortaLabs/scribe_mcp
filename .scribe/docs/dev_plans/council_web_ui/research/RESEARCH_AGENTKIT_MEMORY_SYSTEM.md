# AgentKit Memory System Research

**Research Date:** 2026-01-15
**Researcher:** Atlas (Orchestrator)
**Purpose:** Foundation research for Memory Browser UI modernization

---

## Executive Summary

AgentKit provides a **neuroscience-aligned** memory system with 4-layer reflection, pattern mining, dream cycles, memory decay, and semantic search. This research documents the complete architecture to guide Memory Browser UI development.

---

## 1. Memory Types Hierarchy

### Core Types
| Type | Description | Example |
|------|-------------|---------|
| `episodic` | Specific events with temporal context | "I fixed bug X at 3pm" |
| `semantic` | Learned knowledge and insights | "JWT tokens need refresh handling" |
| `abstract` | Universal principles and patterns | "Always validate input at boundaries" |
| `synthesis` | Integration linking episodic → semantic → abstract | Cross-memory connections |
| `note/raw` | Unstructured observations | Freeform notes |
| `pattern_insight` | Discovered patterns from clustering | Auto-generated insights |

### Database Schema
**Table:** `council.agent_memories`
```sql
- id UUID PRIMARY KEY
- project_id UUID FK
- persona_id TEXT (agent identifier)
- session_id UUID FK (optional session link)
- memory_type TEXT
- text TEXT (content)
- embedding VECTOR(384) (semantic embedding)
- strength REAL (0.0-1.0)
- visibility TEXT (private/council/shared/public)
- tags TEXT[]
- refs JSONB
- metadata JSONB (rich metadata)
- lifecycle TEXT (active/archived)
- created_at TIMESTAMPTZ
```

---

## 2. 4-Layer Reflection System

**Implementation:** `agentkit/src/agentkit/reflection/reflection.py`

### Process Flow
1. **Episodic Layer** - Narrative of specific events (what happened)
2. **Semantic Layer** - Extracted knowledge (what was learned)
3. **Abstract Layer** - Universal principles (what it means)
4. **Synthesis Layer** - Integration with existing beliefs (how it connects)

### Key Functions
```python
generate_reflection_layers(project_id, session, audit_entries, client, context_memories) -> ReflectionLayers
generate_micro_reflection_layers(persona_id, base_memory_text, recent_memories, allowed_layers) -> ReflectionLayers
persist_reflection_layers(persona_id, session_id, layers, reflection_kind) -> dict[ids, group_id]
```

### Metadata Links
- `reflection_group_id` - Links related reflections
- `reflection_kind` - "session", "micro", "dream_cycle"
- `parent_memory_id` - Source memory reference

---

## 3. Pattern Mining System

**Implementation:** `agentkit/src/agentkit/reflection/patterns.py`

### How It Works
1. Groups memories by **tags** and **session_type**
2. Computes **centroid embeddings** for clusters
3. Validates similarity (avg > 0.6, min > 0.4, stdev < 0.18)
4. Generates LLM summaries: `{best_practice, when_effective, pitfalls}`
5. Creates `pattern_insight` memories

### Key Functions
```python
process_new_memories(project_id, persona_id, memory_ids, client) -> list[PatternUpdate]
select_patterns(project_id, persona_id, tags, question_embedding, limit=3) -> list[pattern_dicts]
```

### Pattern Metadata
- `pattern_tag` - cluster tag
- `pattern_sources` - source memory IDs
- `pattern_strength` - computed from similarity + recency
- `pattern_entities` - extracted entities

---

## 4. Dream Cycles (Background Consolidation)

**Implementation:** `agentkit/src/agentkit/reflection/dream_cycles.py`

### Purpose
- Select **seed memories** (high-value clusters)
- Run full 4-layer reflection on each seed
- Create synthesis memories linking related experiences
- Triggered during idle time or explicitly

### Key Functions
```python
run_dream_cycle_for_seed(persona_id, project_id, seed, client, dry_run) -> dict
select_seed_records(project_id, persona_id, config) -> list[DreamSeed]
```

### DreamSeed Structure
```python
@dataclass
class DreamSeed:
    seed_record: MemoryRecord  # anchor memory
    member_ids: list[str]      # cluster members
    metadata: dict             # cluster metadata
```

---

## 5. Memory Strength & Decay

**Implementation:** `agentkit/src/agentkit/memory/decay.py`

### Decay Mechanics
- **Formula:** `strength * 0.5^(age_days / half_life)`
- **Half-life:** 30 days (configurable)
- **Arousal multiplier:** Emotional salience affects decay
  - High arousal (0.7x) - decays slower
  - Low arousal (1.3x) - decays faster

### Tier System
| Tier | Description | Decay Behavior |
|------|-------------|----------------|
| T4 | Core identity | Never decays (exempt) |
| T3 | Important decisions | 90-day protection |
| T2 | Regular memories | Normal decay |
| T1 | Ephemeral | Faster decay |

### Reconsolidation (Access Boost)
- Accessing memories strengthens them (+5% per access)
- Daily cap: +20% max
- Minimum interval: 1 hour between boosts
- Tracks in `metadata.decay_history`

### Key Functions
```python
calculate_decayed_strength(original_strength, age_days, half_life_days, arousal_multiplier) -> float
apply_decay_to_records(records, config, now) -> list[MemoryRecord]
is_exempt(record, config) -> bool
```

### Tier Computation
**File:** `agentkit/src/agentkit/reflection/tiers.py`
```python
compute_tier(record, now) -> TierComputation(tier, tier_score, components, config_version, memory_kind)
```
**Components:** strength, recency, usage, centrality, reflection lineage, omega stats

---

## 6. Council MCP Tools (Integration Layer)

**Location:** `council_mcp/council_mcp/tools/`

### Memory Management
- `store_memory` - Store with embedding, auto-tier, optional micro-reflections
- `query_memories` - Filter by type/tags/visibility/time, pagination
- `reinforce_memory` - Adjust strength, add notes, trigger neuroplasticity

### Query with LLM Synthesis
- `ask_self` - Query own memories with LLM synthesis
- `ask_agent` - Query specific agent (with permission)
- `ask_council` - Query multiple agents for collective wisdom

### Query Modes
- **Normal:** LLM answer + sources
- **Explore:** LLM answer + raw memories + pagination
- **Skip LLM:** Raw memories only (fastest)

### Search Modes
- **hybrid** - Semantic + keyword (default)
- **semantic** - Embedding similarity only
- **keyword** - Text search only

### Reflection Tools
- `run_reflection` - Explicit session reflection
- `run_dream_cycle` - Background consolidation
- `mine_patterns` - Force pattern detection

---

## 7. Memory Metadata Structure

```json
{
  "domain": {
    "tier": "T1|T2|T3|T4",
    "tier_score": 0.0-1.0,
    "memory_kind": "episodic|semantic|...",
    "usage_count": integer,
    "centrality_score": 0.0-1.0,
    "tier_history": [...]
  },
  "emotion": {
    "arousal": "high|medium|low",
    "emotions": ["curious", "focused", ...]
  },
  "decay_history": {
    "last_accessed": "ISO timestamp",
    "boost_count": integer,
    "daily_boost_total": float,
    "daily_boost_reset_at": "ISO date"
  },
  "reflection_group_id": "UUID",
  "parent_memory_id": "UUID",
  "reflection_kind": "session|micro|dream_cycle",
  "pattern_sources": ["mem_id1", "mem_id2", ...],
  "contradiction_analysis": {...},
  "synthesis_integrity": {...}
}
```

---

## 8. UI Requirements (Based on Research)

### Primary Views Needed
1. **Agent Sidebar** - List registered personas, select to view their memories
2. **Memory List** - Query with filters, show type/strength/tier badges
3. **Reflection Graph** - Visualize episodic → semantic → abstract → synthesis chains
4. **Pattern Explorer** - Show `pattern_insight` memories with source clusters
5. **Tier Distribution** - Histogram of T1/T2/T3/T4 counts
6. **Decay Timeline** - Plot memory strength over time with decay curves

### Key Metrics to Display
- Memory count by type per agent
- Average strength by type
- Tier distribution per agent
- Pattern count
- Reflection group count
- Recent dream cycles

### Filtering Options
- Memory type (multi-select)
- Tags (typeahead search)
- Visibility (multi-select)
- Date range (created_at)
- Strength range (slider)
- Tier (T1/T2/T3/T4)
- Search (semantic + keyword)
- Test data toggle (hide test-persona entries)

### Actions Needed
- **View** - Memory detail with full metadata
- **Edit** - Modify tags, visibility
- **Reinforce** - Adjust strength (+/- delta)
- **Archive** - Soft delete
- **Force Reflection** - Trigger micro/full reflection
- **Mine Patterns** - Force pattern detection for agent
- **Run Dream Cycle** - Trigger consolidation

### API Endpoints to Implement
```
GET  /api/memories?persona_id=X&type=Y&tags=Z&limit=N&offset=M
POST /api/memories (store new)
GET  /api/memories/{id} (detail view)
PATCH /api/memories/{id} (reinforce, update tags)
DELETE /api/memories/{id} (archive)

GET  /api/patterns?persona_id=X&tags=Y
GET  /api/patterns/{id}/sources (pattern source memories)

GET  /api/reflections?persona_id=X&kind=Y
GET  /api/reflections/{group_id} (reflection layers)

POST /api/agents/{persona_id}/reflect (force reflection)
POST /api/agents/{persona_id}/dream-cycle (force dream cycle)
POST /api/agents/{persona_id}/mine-patterns (force pattern mining)

GET  /api/stats/persona/{id}/overview (counts, strength avg, tier dist)
GET  /api/stats/persona/{id}/decay-projection (future strength estimates)
```

### WebSocket Events
- `memory:created` - New memory stored
- `pattern:discovered` - New pattern mined
- `reflection:completed` - Reflection cycle done
- `decay:updated` - Decay applied to memories

---

## 9. Key Files Reference

| Component | Location |
|-----------|----------|
| Memory Types | `council_mcp/db/schema/council/tables/060_council.sql` |
| Reflection System | `agentkit/src/agentkit/reflection/reflection.py` |
| Pattern Mining | `agentkit/src/agentkit/reflection/patterns.py` |
| Dream Cycles | `agentkit/src/agentkit/reflection/dream_cycles.py` |
| Memory Decay | `agentkit/src/agentkit/memory/decay.py` |
| Tier Computation | `agentkit/src/agentkit/reflection/tiers.py` |
| Council Tools | `council_mcp/council_mcp/tools/memory.py` |
| Current UI | `council_mcp/council_mcp/web/static/js/memories.js` |

---

## 10. Summary

AgentKit provides complete infrastructure for:
- ✅ **4-layer reflection** (episodic → semantic → abstract → synthesis)
- ✅ **Pattern mining** (automatic clustering + LLM summarization)
- ✅ **Dream cycles** (background consolidation)
- ✅ **Memory decay** (exponential with tier/tag exemptions)
- ✅ **Reconsolidation** (access-based strengthening)
- ✅ **Semantic search** (vector embeddings + hybrid search)

**All infrastructure exists - we need to build the UI layer on top.**
