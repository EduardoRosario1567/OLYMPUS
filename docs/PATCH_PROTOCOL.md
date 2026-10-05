# PATCH Protocol — Compact Format

## Patch Header

```
@patch <PATCH_ID>
@name <OPERATION_NAME>
@mode EXECUTE|PLAN|VERIFY
@autonomy L0|L1|L2|L3
@repair <max_cycles>
@network none|internal|external
@dependencies <comma-separated patch IDs or "none">
```

## Required Sections

### GOAL
Single-sentence objective. What this patch achieves.

### SCOPE.CREATE
Files to create (new paths only).

### SCOPE.MODIFY
Existing files to modify.

### SCOPE.FORBID
Paths that must NOT be touched.

### CONTEXT.READ
Files to read for this patch only.

### CONTEXT.POLICY
```
default=minimal
max_escalation=2
no_repository_wide_scan
no_read_for_familiarity
dependency_reads=direct_only
```

### INPUT
Data/configuration the patch consumes.

### PROCESS
Step-by-step execution logic.

### OUTPUT
Artifacts produced (files, test results, reports).

### ASSERT
Runtime invariants that must hold:
```
runtime_code_changed=false|true
tests_changed=false|true
dependencies_changed=false|true
database_changed=false|true
existing_worktree_preserved=true
```

### VALIDATE
Verification steps:
- Parse/read all created files
- YAML syntax check (if applicable)
- `git status --short`
- `git diff -- <modified files>`
- Do NOT run application regression

### EXIT
Completion criteria:
- All declared files created
- Manifests reference real paths only
- Runtime untouched
- Working tree preserved
- Compact report generated

**Do not propose next patch. Do not ask to continue. Stop after report.**

## Autonomy Levels

| Level | Description |
|-------|-------------|
| L0 | Read-only. No edits. |
| L1 | Authorized scope + targeted tests + git ops + auto-repair (max 3). |
| L2 | Module-level work. Explicit grant required. |
| L3 | Feature-level work. Explicit grant required. |

**Never infer higher autonomy.**

## BLOCK Conditions

Halt immediately on:
- Scope expansion beyond @patch authorization
- New dependency
- Migration
- Secret required
- Destructive operation
- Data-loss risk
- Architecture decision not specified
- Repair cycles exhausted

## Test Policy

| Phase | Scope |
|-------|-------|
| patch | Targeted tests only (unit/integration for changed code) |
| milestone | Full regression |

Full suite only on explicit request or milestone.