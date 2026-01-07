# Dependency Graph Visualization

## Files

- **dependency_graph.dot**: Graphviz DOT format dependency graph
- **import_graph.md**: Comprehensive textual analysis (primary deliverable)

## Generating Visualization

### Prerequisites

Install Graphviz:
```bash
# Ubuntu/Debian
sudo apt-get install graphviz

# macOS
brew install graphviz

# Or use online viewer: https://dreampuf.github.io/GraphvizOnline/
```

### Generate PNG

```bash
dot -Tpng dependency_graph.dot -o dependency_graph.png
```

### Generate SVG (scalable)

```bash
dot -Tsvg dependency_graph.dot -o dependency_graph.svg
```

### Generate PDF

```bash
dot -Tpdf dependency_graph.dot -o dependency_graph.pdf
```

## Visualization Key

### Node Colors (Coupling Score)
- **Dark Red**: EXTREME coupling (>40 importers) - `config`, `utils`, `tools`
- **Orange**: HIGH coupling (20-40 importers) - `storage`, `shared`
- **Yellow**: MEDIUM coupling (10-20 importers) - `state`, `doc_management`, `plugins`, `server`
- **Light Green**: LOW coupling (<10 importers) - `security`, `templates`, `db`

### Edge Colors
- **Blue**: Normal dependency (A imports from B)
- **Red (bold)**: Circular dependency (A and B import from each other)

### Layout Layers
- **Layer 0 (Foundation)**: config - No dependencies
- **Layer 1 (Infrastructure)**: security, template_engine, templates
- **Layer 2 (Storage/Utils)**: db, storage, utils
- **Layer 3 (State)**: state
- **Layer 4 (Application)**: tools, doc_management, plugins, shared, reminders
- **Layer 5 (Interface)**: server, scripts

## Critical Findings

### 5 Circular Dependencies (RED arrows)

1. **tools ↔ utils** - Highest impact (57 and 63 importers)
2. **storage ↔ db** - Database layer circular coupling
3. **doc_management ↔ tools** - Feature coupling
4. **shared ↔ utils** - Infrastructure coupling
5. **shared ↔ tools** - Infrastructure coupling

### Top 3 Coupling Hot Spots

1. **utils**: 63 files depend on it (EXTREME)
2. **tools**: 57 files depend on it (EXTREME)
3. **config**: 47 files depend on it (EXTREME)

## Online Viewing

If you don't have Graphviz installed, paste the contents of `dependency_graph.dot` into:

https://dreampuf.github.io/GraphvizOnline/

## Usage Notes

- Graph shows module-to-module dependencies (not file-level detail)
- Circular dependencies MUST be resolved before src/ migration
- High coupling modules (red/orange nodes) require extra care during refactoring
- See `import_graph.md` for detailed file-level analysis

## Related Documents

- **import_graph.md**: Complete textual analysis (primary deliverable)
- **phase_3_coordination.md**: Team coordination and handoffs
- **Team D deliverable**: Detailed circular dependency analysis (forthcoming)
- **Team C deliverable**: src/ migration strategy (forthcoming)
