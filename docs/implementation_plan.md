# Initial implementation plan

Repository inspected 2026-10-30: empty initial commit, clean worktree, no applicable
AGENTS.md found. Preserve work in this worktree; no external publishing or trading.

1. Audit official Fed, FRED/ALFRED, and prediction-market documentation and access.
2. Establish a Python 3.12 / uv locked environment, cached raw-source provenance,
   explicit meeting/observation schemas, and conservative UTC availability rules.
3. Reconstruct and audit one real seven-day forecast snapshot before scaling.
4. Build as much verified scheduled-meeting and historical vintage coverage as
   the actual sources permit. Keep unavailable fields missing and exclusions explicit.
5. Implement chronological expanding-window frequency, logistic, and shallow-tree
   baselines, train-only preprocessing, saved predictions, calibration and paired
   block-bootstrap uncertainty. Run empirical models only on real eligible data.
6. Test consequential leakage/label/calendar failures; document coverage, results,
   access blockers, and the later state-space and PSI experiments.

No performance-dependent sample selection. Candidate split: train through 2012,
development 2013–2018, holdout 2019–2025 (last complete calendar year). Adjust only
for source coverage, before evaluating scores. Holdout iterations are logged.

