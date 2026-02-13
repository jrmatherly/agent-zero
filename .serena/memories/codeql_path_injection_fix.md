# CodeQL Path Injection Fix (Feb 2026)

## Alert #74: `py/path-injection` on `file_browser.py` __init__
- Rule: CWE-22 — Uncontrolled data used in path expression
- Sink: `os.makedirs()` in `FileBrowser.__init__`

## CodeQL's Two-State Taint Model (from codeql/python query source)
1. **NotNormalized** → data starts here at every source
2. **NormalizedUnchecked** → after `PathNormalization` (realpath/normpath/abspath)
3. Taint blocked when **both** stages satisfied: normalization + SafeAccessCheck guard

## Recognized Sanitizer Patterns (Exhaustive)
- **PathNormalization**: `os.path.normpath()`, `os.path.abspath()`, `os.path.realpath()` ONLY
- **SafeAccessCheck**: `str.startswith()` ONLY
- **NOT recognized**: `pathlib.Path.resolve()`, `pathlib.Path()` constructor

## Critical SSA Requirement
CodeQL's barrier guard is **SSA-based**: it only protects uses of the EXACT same variable definition that was checked by `startswith`. These break it:
- `self.x = normalized` → attribute store/read is a SEPARATE data flow path
- `Path(normalized)` → Path constructor is a taint step, not normalizer; guard doesn't carry through
- Compound `and` conditions → can confuse guard node identification

## Correct Pattern
```python
normalized = os.path.realpath(untrusted)      # PathNormalization
if not normalized.startswith(safe_prefix):     # SafeAccessCheck (simple, no compound and)
    raise ValueError("bad")
os.makedirs(normalized, exist_ok=True)         # Sink uses SAME SSA variable
self.base_dir = Path(normalized)               # Assignment AFTER the guarded sink
```

## Previous Failed Attempts
1. **Helper function** `_confine_to_project_root()`: CodeQL didn't propagate sanitizer across function boundary (alerts #71, #72)
2. **Inlined with Path() + self.base_dir at sink**: SSA tracking broken by Path() + attribute store/read (alert #74)
3. **Compound `and` condition**: `not x.startswith(root + os.sep) and x != root` ambiguous for guard identification

## Defense-in-Depth Layers (all still active)
1. TenantContext.__post_init__ — regex allowlist on user_id, org_id, team_id
2. files.get_abs_path() — all workspace paths joined with project root
3. FileBrowser.__init__ — realpath + startswith guard (CodeQL-recognized)
4. FileBrowser._is_confined() — per-operation confinement checks
