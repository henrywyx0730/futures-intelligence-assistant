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

<!-- BEGIN PROJECT SKILL ROUTING -->
### Working Workflow

- Before editing, inspect the relevant files and explain the plan.
- Work only inside this repository.
- Keep changes narrowly scoped to the requested task.
- Do not modify unrelated files.
- Do not commit, push, tag, or create a release unless explicitly requested.
- Show the final diff and report verification results.
- Ask for approval before installing dependencies, running migrations, deleting files, changing environment files, or performing destructive operations.
- `find-skills` may suggest additional skills, but must not install anything without explicit approval.

### General Skill Routing

- Use the appropriate Superpowers workflow for complex features, architecture, substantial refactors, difficult debugging, database work, and test-driven implementation.
- Use `systematic-debugging` before proposing speculative fixes.
- Use `test-driven-development` when changing important logic.
- Use `writing-plans` for substantial multi-step work.
- Use `verification-before-completion` before declaring substantial work complete.
- Do not invoke heavyweight workflows for trivial text, spacing, color, or isolated obvious fixes.

## Project Skill Routing — Futures Intelligence Assistant

### Product Boundary

- Treat this as a market-intelligence and research pipeline, not primarily as a visual-design project.
- Preserve the distinction between collected information, normalized data, deterministic analysis, aggregation, and generated briefs.
- Preserve source provenance, canonical URLs, publication precision, reliability metadata, category scope, and diagnostics.
- Never turn configured source scope or broad categories into unsupported analytical evidence.
- Do not infer directional market conclusions from unsupported language, missing commodity matches, or ambiguous source text.

### Engineering Skills

- Superpowers is the default skill family for collector, fetcher, parser, matcher, analyst, ranking, persistence, configuration, and pipeline work.
- Prefer test-first implementation for collectors, adapters, matching rules, failure isolation, and configuration routing.
- Keep source-specific collection logic separate from shared analyst and downstream pipeline logic.
- Preserve bounded downloads, extraction limits, allowlists, failure isolation, deterministic ordering, and sanitized logging.
- Do not add network-dependent smoke tests to normal verification unless explicitly requested.

### Design Skills

- Use `ui-design` only when editing a real human-facing dashboard, report viewer, brief reader, or configuration interface.
- Do not use `design-taste-frontend` for backend pipeline, collector, matcher, or analysis work.
- Use `apple-design` only for clear feedback, progressive disclosure, filters, loading states, and readable state transitions.
- Avoid decorative motion, glass effects, marketing-page treatments, and animation inside dense analytical views.
- Financial claims, signals, confidence, freshness, and source attribution must remain clearer than visual decoration.
<!-- END PROJECT SKILL ROUTING -->
