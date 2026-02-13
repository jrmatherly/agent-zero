---
name: docs-audit
description: Audit documentation in docs/ against the live codebase. Cross-references file paths, class names, CLI commands, component counts, image paths, and internal links to find outdated or inaccurate content.
disable-model-invocation: true
---

# Documentation Audit — Cross-reference docs against codebase

Systematically audit all documentation files in `docs/` for accuracy against the current codebase state.

## Procedure

### 1. Inventory

Glob all markdown files:
```
docs/**/*.md
```

Report the count and list them grouped by subdirectory.

### 2. Gather codebase baselines

Collect these ground-truth counts (used to verify claims in docs):

| Metric | Command |
|--------|---------|
| Active tools | `ls python/tools/*.py \| wc -l` |
| Disabled tools | `ls python/tools/*._py 2>/dev/null \| wc -l` |
| API handlers | `ls python/api/*.py \| wc -l` |
| Extension points | `ls -d python/extensions/*/ \| wc -l` |
| Helper modules | `ls python/helpers/*.py \| wc -l` |
| WebSocket handlers | `ls python/websocket_handlers/*.py \| wc -l` |
| GitHub Actions workflows | `ls .github/workflows/*.yml \| wc -l` |
| mise tasks | `mise task ls 2>/dev/null \| wc -l` |

### 3. Audit each file

For every documentation file, check these categories:

#### File path references
- Extract all paths mentioned in the doc (code blocks, inline references)
- Verify each path exists in the codebase
- Flag missing files or wrong directory structures

#### Class and function names
- Extract referenced class names (e.g., `AgentNotification`, `NotificationManager`)
- Verify they exist with `grep -r "class ClassName"` in the codebase
- Flag non-existent classes or renamed references

#### CLI commands
- Extract all CLI commands shown in the doc
- Check if they use `mise run` (required by project convention) or raw tool invocation
- Verify mise task names exist in `mise.toml`

#### Component counts
- Compare any stated counts (e.g., "19 tools", "7 workflows") against baselines from step 2
- Flag mismatches with actual vs stated numbers

#### Image and link paths
- Extract all relative image references (`![](path)`, `<img src="path">`)
- Extract all relative markdown links (`[text](path)`)
- Verify each target exists
- Check for `docs/setup/res/` vs `docs/res/` path confusion

#### Branding
- Flag any hardcoded product names that should use `{{brand_name}}` or the configurable branding system
- Flag references to upstream project resources (Discord, YouTube, agent0ai GitHub) that should be rebranded for the fork

### 4. Severity classification

Classify each finding:

| Severity | Criteria |
|----------|----------|
| **Critical** | Non-existent class/function referenced, commands that would fail, security-relevant misinformation |
| **High** | Wrong file paths, broken images/links, stale component counts (off by >20%) |
| **Medium** | Missing mise wrapper on CLI commands, outdated but non-breaking descriptions |
| **Low** | Minor wording issues, cosmetic path inconsistencies, missing new features in docs |

### 5. Report

Output a structured report with:

1. **Executive summary**: Total findings by severity
2. **Baseline table**: Actual counts vs any documented counts found
3. **Per-file findings**: Grouped by doc file, each finding with:
   - Severity
   - Line number (approximate)
   - What's wrong
   - What it should be
4. **Cross-cutting issues**: Patterns that affect multiple docs
5. **Recommended priority**: Which files to fix first

### 6. Save report

Write the report to `.scratchpad/docs-audit-report.md`.

If a previous report exists, archive it first:
```bash
mv .scratchpad/docs-audit-report.md .scratchpad/docs-audit-report.$(date +%Y%m%d).md
```
