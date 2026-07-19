# Codex Working Rules

## Project profile

Futures Intelligence Assistant is a focused Python financial-intelligence
utility, not an automated trading system. Prioritize correctness, provenance,
deterministic behavior, and safe failure modes over feature count or visual
complexity. Preserve the separation between collection, normalization,
analysis, generation, persistence, configuration, and knowledge layers.

## Repository safety

- Run `git status` before making changes and explain a focused plan before editing.
- Work only inside this repository and modify only files directly related to the task.
- Prefer the smallest safe change; preserve existing behavior unless explicitly asked
  to change it.
- Do not delete or rename files, discard uncommitted work, reset or rewrite Git
  history, commit, or push without explicit approval.
- Ask for approval before installing/removing dependencies, changing environment,
  build, deployment, or port settings, running migrations, killing processes, or
  executing destructive commands.
- After editing, report the summary, changed files, checks run, remaining risks, and
  the diff. Do not claim an unrun check passed.

## Engineering defaults

- Read relevant architecture, development, configuration, and knowledge files before
  changing behavior.
- Keep responsibilities isolated: collectors obtain material; processing normalizes
  and filters it; analysts interpret it; generators format it; database code owns
  persistence; `config/` and `knowledge/` hold shared non-secret assumptions.
- Add focused tests for behavior changes. Run the relevant checks; for Python changes
  normally run:

  ```sh
  PYTHONPATH=src python3 -m compileall -q -f src tests
  PYTHONPATH=src python3 -m unittest discover -s tests -v
  git diff --check
  ```

- Preserve source provenance and timezone-aware timestamps. Keep reported facts,
  deterministic rules, and model inference distinguishable.
- Do not introduce trading execution, external collection, API integrations, or
  delivery behavior unless the task explicitly scopes it.
- Treat source reliability, commodity relationships, and market conclusions as
  reviewable assumptions. Avoid unsupported certainty in financial interpretations.

## Configuration, data, and secrets

- Store shared non-secret settings in version-controlled YAML and validate their
  shape. Do not hard-code watchlists, source priorities, or environment-specific
  values.
- Keep credentials only in environment variables or an untracked secret manager.
  `.env.example` may contain names and empty/safe values only.
- Never log, commit, or expose API keys, tokens, private source material, or sensitive
  configuration. Use least privilege and respect source terms, licensing, rate
  limits, and applicable law.

## Skills and interface work

- Use a proportional Superpowers-style workflow for architecture changes, multi-file
  refactors, state/data integrity work, migrations, difficult bugs, or
  regression-sensitive changes. Do not add planning overhead for trivial edits.
- This repository has no primary visual surface. If a future UI is added, favor a
  minimal, accessible, task-focused interface; avoid decorative animation and heavy
  WebGL effects. Seek explicit visual approval before any prominent animation,
  React Bits component, Unicorn Studio, or other GPU-heavy effect.
- For substantial future visual work, obtain approval for the design direction and
  focal effects, then verify desktop/mobile behavior, accessibility, contrast, focus
  states, reduced motion, and performance before calling it complete.
