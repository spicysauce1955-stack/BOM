# Current status

Updated: 2026-08-09

- [x] Phase: research — 4 parallel researcher reports in `docs/research/`, synthesis + ADRs 0001–0010
- [x] Phase: architecture — `docs/architecture/*` written; golden scenarios defined
- [ ] Slice 0: spike ← **in progress**
- [ ] Slices 1–11: pending (see implementation-roadmap.md)

Open items / risks:
- Screws-per-connection policy left as a knowledge FACT (doc notes 2/connection in demo KB).
- Event re-anchoring implemented as edit-time transform (anchor {seg, offset, authored seg len}).
- Claude adapter will be built but only stub-tested unless an API key is present at runtime.
