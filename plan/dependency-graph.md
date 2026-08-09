# Dependency graph

```
core ──► topology ──► strategy ◄── knowledge ◄─ core
core ──► catalog ──┬─► strategy
                   └─► demand ──► fulfillment
strategy ──► decisions (written via builder during generation)
strategy ──► demand
knowledge ◄── learning (candidates) ◄── decisions/corrections
ai (ports) ◄── stub/claude adapters; used by api/learning; never by generate()/fulfill() internals
store ◄── all models (persistence only)
api ──► everything (composition root); web static ◄── api
```

Slice ordering constraints: 1→{2,3} independent of each other; 4 needs 1+2+3; 5 needs 2+4;
6 needs 4; 7 needs 1 (annotations) + 4 (intents affect generation); 8 needs 3+7; 9 needs
models from 1–8 (thin, can trail each slice); 10 needs 9; 11 last.

Safe to parallelize (established interfaces): cut planner internals (5) vs overrides (6);
UI (10) against frozen API; docs. Never parallel: topology/knowledge/decision models while
still moving (mission §16).
