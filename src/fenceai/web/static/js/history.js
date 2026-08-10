// Undo/redo stub (Task 1). Task 6 replaces this with the real gesture-snapshot
// stack (see docs/superpowers/plans/2026-08-10-ui-v2.md Task 6 for the contract).

export function pushSnapshot(_label) {}
export function undo() { return false; }
export function redo() { return false; }
export function canUndo() { return false; }
export function canRedo() { return false; }
export function resetHistory() {}
