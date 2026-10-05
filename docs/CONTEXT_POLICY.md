# Context Policy — Minimal-First Loading

## Principle

**CONTEXT IS PULLED, NOT PUSHED.**

Load only what is needed for the current patch. Never scan the entire repository "to understand the project."

## Context Levels

| Level | Name | Contents | Default Max |
|-------|------|----------|-------------|
| L0 | Permanent Contracts | AGENTS.md, PATCH_PROTOCOL.md, CONTEXT_POLICY.md | Always |
| L1 | Patch Target Files | Files in SCOPE.CREATE + SCOPE.MODIFY | Always |
| L2 | Direct Dependencies | Imports/uses from L1 files | Automatic if needed |
| L3 | Shared/System Context | Cross-module patterns, infrastructure | Explicit grant only |

## Loading Rules

1. **Default maximum = L2**
2. **L1 → L2 automatic** when direct dependency proves necessary
3. **L2 → L3 requires BLOCK** unless patch explicitly allows L3
4. **Forbidden by default:**
   - Repository-wide scanning
   - Reading unrelated frontend/backend/db/routing modules
   - Reading historical patches unless required
   - Loading files merely "to understand the project better"

## Escalation Protocol

When L2 is insufficient:
1. Record: `ESCALATION: L1→L2 | file: <path> | reason: <why>`
2. Load only the specific dependency file(s)
3. Do not load siblings or parents unless proven necessary

When L3 is requested:
1. Record: `ESCALATION: L2→L3 | file: <path> | reason: <why>`
2. If not explicitly granted in patch → BLOCK
3. If granted, load only the specific file(s)

## Context Manifests

Each `contexts/*.yaml` defines a domain's context boundary:

```yaml
name: <domain>
purpose: <one sentence>
required:
  - <file paths that MUST be loaded for this domain>
tests:
  - <test files for this domain>
dependencies:
  - <direct dependency files>
optional:
  - <files that may be loaded if needed>
forbidden:
  - <files that MUST NOT be loaded>
```

## Verification

Before executing patch:
- All `required` paths exist
- No `forbidden` paths in scope
- YAML syntax valid