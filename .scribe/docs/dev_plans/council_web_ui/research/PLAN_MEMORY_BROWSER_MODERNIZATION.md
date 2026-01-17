# Memory Browser Modernization Plan

**Date:** 2026-01-15
**Author:** Atlas (Orchestrator)
**Status:** Planning

---

## Vision

Transform the Memory Browser from a basic card grid into a **professional agent introspection system** that provides deep visibility into what agents are learning, remembering, and synthesizing.

---

## Current State

- Basic card grid showing all memories
- Left sidebar with basic filters (persona dropdown, type checkboxes, tags, search)
- No agent-centric navigation
- No edit/delete capabilities
- No reflection controls
- No pattern visualization
- Test data mixed with real data

---

## Target Architecture

### Layout: Three-Panel Design

```
┌─────────────────────────────────────────────────────────────────────┐
│  Council MCP Command Center    [Dashboard] [Sessions] [Memories]    │
├──────────┬──────────────────────────────────────────┬───────────────┤
│          │                                          │               │
│  AGENT   │           MEMORY VIEW                    │   DETAIL      │
│  SIDEBAR │                                          │   PANEL       │
│          │  ┌─────────────────────────────────┐    │               │
│  ○ atlas │  │ [Memories] [Patterns] [Graph]   │    │  Selected     │
│  ● forge │  ├─────────────────────────────────┤    │  Memory       │
│  ○ lens  │  │                                 │    │               │
│  ○ mantis│  │  Memory cards/table here        │    │  - Full text  │
│  ○ arbiter│ │                                 │    │  - Metadata   │
│          │  │                                 │    │  - Actions    │
│  ────────│  │                                 │    │  - Graph      │
│  + Add   │  │                                 │    │               │
│          │  └─────────────────────────────────┘    │               │
│          │                                          │               │
│  Stats:  │  [Filter Bar]  [Search]  [Actions]      │               │
│  42 mem  │                                          │               │
│  3 patt  │                                          │               │
└──────────┴──────────────────────────────────────────┴───────────────┘
```

---

## Phase 1: Agent Sidebar & Navigation

### Goal
Replace persona dropdown with proper agent sidebar showing all registered personas.

### Components
1. **Agent List** - Vertical list of registered personas
   - Avatar/color indicator
   - Name + title
   - Memory count badge
   - Pattern count badge
   - Active indicator (has open session)

2. **Agent Stats** - Quick stats for selected agent
   - Total memories
   - Active patterns
   - Last activity
   - Tier distribution mini-chart

3. **Actions**
   - View all memories
   - Force reflection
   - Run dream cycle
   - Mine patterns

### Data Source
- `GET /api/profiles` (list_profiles)
- `GET /api/stats/persona/{id}/overview`

---

## Phase 2: Memory List Overhaul

### Goal
Professional memory list with proper filtering, sorting, and batch operations.

### Components
1. **View Modes**
   - **Card Grid** (current, improved)
   - **Compact Table** (high density)
   - **Timeline** (chronological)

2. **Enhanced Filters**
   - Memory type (multi-select with badges)
   - Tier (T1/T2/T3/T4 checkboxes)
   - Strength range (slider)
   - Date range (picker)
   - Tags (typeahead)
   - Visibility (private/council/shared/public)
   - **Hide test data** toggle (critical!)

3. **Sorting Options**
   - Created (newest/oldest)
   - Strength (high/low)
   - Tier (T4 first)
   - Recently accessed

4. **Memory Cards** (improved)
   - Type badge with color
   - Tier indicator (T1-T4)
   - Strength bar (visual)
   - Truncated text with expand
   - Tags as chips
   - Quick actions (reinforce, archive)

### Data Source
- `GET /api/memories?persona_id=X&...`
- Direct DB query for performance

---

## Phase 3: Detail Panel & Editing

### Goal
Full memory detail view with edit capabilities.

### Components
1. **Memory Detail**
   - Full text (formatted)
   - All metadata displayed
   - Tier explanation
   - Decay projection chart
   - Reflection lineage (if synthesis)

2. **Edit Capabilities**
   - Edit tags
   - Change visibility
   - Add notes to metadata
   - Reinforce (+/- strength)
   - Archive/restore

3. **Related Memories**
   - Similar by embedding (semantic neighbors)
   - Same reflection group
   - Pattern members (if pattern_insight)

### Data Source
- `GET /api/memories/{id}`
- `PATCH /api/memories/{id}`

---

## Phase 4: Patterns Page

### Goal
Dedicated view for pattern insights - what agents are learning.

### Components
1. **Pattern List**
   - Pattern tag/name
   - Source memory count
   - Pattern strength
   - Created date
   - Best practice summary

2. **Pattern Detail**
   - Full insight text
   - `best_practice` field
   - `when_effective` field
   - `pitfalls` field
   - Source memories (expandable list)
   - Cluster visualization (UMAP?)

3. **Pattern Actions**
   - View source memories
   - Reinforce pattern
   - Archive pattern
   - Force re-mine

### Data Source
- `GET /api/patterns?persona_id=X`
- Filter `memory_type='pattern_insight'`

---

## Phase 5: Reflection Graph

### Goal
Visualize reflection chains (episodic → semantic → abstract → synthesis).

### Components
1. **Graph View**
   - Nodes = memories
   - Edges = reflection relationships
   - Color by type
   - Size by strength
   - Interactive (click to select)

2. **Reflection Groups**
   - Group by `reflection_group_id`
   - Show 4-layer structure
   - Timeline view of group creation

3. **Force Reflection UI**
   - Select memories
   - Choose reflection type (micro/full)
   - Preview before running
   - Progress indicator

### Data Source
- `GET /api/reflections?persona_id=X`
- `POST /api/agents/{id}/reflect`

---

## Phase 6: Actions & Controls

### Goal
Agent control panel for memory operations.

### Actions
1. **Force Reflection**
   - Select session or memories
   - Run micro or full reflection
   - Show progress

2. **Run Dream Cycle**
   - Trigger background consolidation
   - Show seed selection
   - Progress and results

3. **Mine Patterns**
   - Force pattern detection
   - Show discovered patterns
   - Configurable thresholds

4. **Bulk Operations**
   - Select multiple memories
   - Batch archive
   - Batch tag
   - Batch reinforce

### Data Source
- `POST /api/agents/{id}/reflect`
- `POST /api/agents/{id}/dream-cycle`
- `POST /api/agents/{id}/mine-patterns`

---

## Phase 7: Test Data Isolation

### Goal
Clearly separate test/development data from real agent memories.

### Components
1. **Test Data Filter**
   - Toggle to hide test-persona entries
   - Regex patterns for test detection
   - Visual indicator when filter active

2. **Test Data Markers**
   - Badge on test memories
   - Different card style
   - Excluded from stats by default

3. **Test Data Cleanup**
   - Bulk delete test data
   - Archive test data
   - Export before cleanup

### Detection Patterns
```javascript
const TEST_PATTERNS = [
    /^test-persona/i,
    /^test-/i,
    /integration test/i,
    /test entry/i,
    /-123$/
];
```

---

## Technical Requirements

### Backend APIs (New/Enhanced)
```
GET  /api/personas (list with memory stats)
GET  /api/personas/{id}/stats (detailed stats)
GET  /api/patterns (pattern_insight memories)
GET  /api/reflections (by group/kind)
POST /api/personas/{id}/reflect (force reflection)
POST /api/personas/{id}/dream-cycle (trigger consolidation)
POST /api/personas/{id}/mine-patterns (force pattern mining)
PATCH /api/memories/{id} (edit tags, visibility, strength)
DELETE /api/memories/{id} (archive)
```

### WebSocket Events
- `memory:created` - Real-time updates
- `pattern:discovered` - New pattern alert
- `reflection:completed` - Reflection done
- `decay:tick` - Periodic decay updates

### Frontend Components
- AgentSidebar.js
- MemoryList.js (with view modes)
- MemoryCard.js
- MemoryDetail.js
- PatternList.js
- PatternDetail.js
- ReflectionGraph.js (D3.js or similar)
- ActionPanel.js

---

## Implementation Order

1. **Phase 1: Agent Sidebar** - Foundation for agent-centric view
2. **Phase 2: Memory List** - Core browsing experience
3. **Phase 3: Detail Panel** - View and edit
4. **Phase 7: Test Data** - Critical for usability (do early!)
5. **Phase 4: Patterns** - Key learning visibility
6. **Phase 5: Graph** - Advanced visualization
7. **Phase 6: Actions** - Full control

---

## Success Criteria

- [ ] Can select any registered agent from sidebar
- [ ] Can view all memories for selected agent
- [ ] Can filter by type, tier, strength, tags
- [ ] Can hide test data with one toggle
- [ ] Can edit memory tags and visibility
- [ ] Can reinforce memory strength
- [ ] Can archive memories
- [ ] Can force reflection on agent
- [ ] Can run dream cycle
- [ ] Can mine patterns
- [ ] Can view pattern insights with sources
- [ ] Can see reflection chains visually
- [ ] Real-time updates via WebSocket

---

## Dependencies

- AgentKit memory/reflection infrastructure (exists ✅)
- Council MCP tools (exists ✅)
- PostgreSQL with pgvector (exists ✅)
- D3.js or similar for graph visualization (to add)
- Enhanced backend APIs (to implement)
