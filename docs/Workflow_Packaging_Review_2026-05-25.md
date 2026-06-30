# Workflow Packaging Review (2026-05-25)

## Evidence Window
- Requested window: last 30 days, or all available history if shorter.
- Available Codex session index after reindex: 1 session (2026-05-25), no indexed turns.
- Codex Memories reviewed:
  - user memory: 2 recurring PowerShell failure notes
  - repo memory: PostgreSQL partitioning pitfalls from implementation
- Chronicle discovery via standup: only same session visible, no external references.
- Existing custom assets:
  - user-level prompt: uiagent.prompt.md (2026-05-18)

## Compact Shortlist

| Repeated workflow | Supporting evidence and dates | Frequency / confidence | Recommended form | Why create or skip |
|---|---|---|---|---|
| Defensive PowerShell command authoring | Memory notes show two recurring issues: unsafe array slicing and here-string syntax errors (user memory; persisted before current run) | >=2 occurrences / High | Skill-like prompt (new) | High recurrence, error-prone, stable inputs, clear output (safe command shape) |
| Plan-first strict delivery for multi-file implementation | 2026-05-25 session involved full-stack scaffolding, phased execution, repeated validation/fix loops, and explicit strict standards request | 2+ within current run and likely recurring / High | Skill-like prompt (new) | Costly manual orchestration, stable procedure, strong quality and consistency gains |
| UI mutation preview-first flow | Existing uiagent prompt already defines preview->approve->apply policy (2026-05-18) | Reused pattern / High | Extend existing | Already adequately covered; avoid duplication |
| Chronicle-driven weekly workflow mining | Chronicle data currently minimal (same session only; no refs) | 1 / Low | Skip for now | Insufficient evidence to design reliable automation triggers |
| Cross-system recurring automation (scheduled reports/reminders) | No repeat evidence from indexed sessions beyond current run | 1 / Low | Skip for now | Needs more historical signal to avoid speculative automations |

## Created (High-Confidence Missing Items)

1. strict-delivery.prompt.md (user-level prompt)
- Purpose: package plan-first implementation, validation gates, and zero-regression final checks.
- Scope: cross-workspace personal workflow.
- Validation: includes entry criteria, step-by-step procedure, and output contract.

2. powershell-defensive.prompt.md (user-level prompt)
- Purpose: prevent known recurring PowerShell failures.
- Scope: cross-workspace personal workflow.
- Validation: includes safe helper pattern, here-string rules, and defensive execution checklist.

## Deliberately Skipped
- New UI mutation skill/agent (already covered by existing uiagent prompt).
- Chronicle-based automation/reporting (data signal currently too weak).
- Broad all-purpose mega-agent (too wide, high overlap risk).

## Needs More Evidence Before Packaging
- Any scheduled automation (weekly/monthly monitors) should wait for at least 2-3 additional sessions showing repeat cadence and stable input sources.
- Chronicle-based packaging should be revisited after more than one session appears in Chronicle/session index.
