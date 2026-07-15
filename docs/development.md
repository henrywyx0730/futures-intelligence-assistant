# Development Guidelines

## Project Overview

Futures Intelligence Assistant is a personal futures research system, not an
automated trading system. It turns market events into traceable supply, demand,
inventory, cost-transmission, and futures-market research insights. Development
should favor correctness, provenance, and clear reasoning over speed or feature
count.

## Python Environment Setup

- Use a dedicated virtual environment for local development.
- Install dependencies from `requirements.txt`.
- Run application modules from the repository root, using the project's package
  path (for example, `PYTHONPATH=src python -m futures_intelligence.main`).
- Add a dependency only when it has a clear project need, is maintained, and is
  pinned to a compatible version range.

## Repository Responsibilities

- `src/futures_intelligence/collectors/`: obtain source material only; do not
  interpret markets here.
- `src/futures_intelligence/analyzer/`: filter information and model
  supply-demand, inventory, and transmission impacts.
- `src/futures_intelligence/generator/`: create research briefs from validated
  analysis.
- `src/futures_intelligence/database/`: own future persistence interfaces and
  implementations.
- `src/futures_intelligence/config/`: load and validate configuration.
- `knowledge/`: maintain commodity relationships and market-domain knowledge.
- `config/`: maintain watchlists and approved source definitions.
- `docs/`: record architecture, operating assumptions, and development guidance.

## Development Workflow

1. Read the relevant architecture, configuration, and knowledge files before
   changing behavior.
2. Keep each change focused on one layer or responsibility.
3. Add or update tests for behavior changes, then run applicable checks before
   review.
4. Preserve the chain from source event to research conclusion; make important
   assumptions explicit.
5. Do not add scraping, AI calls, delivery, database, or trading behavior until
   that phase is intentionally scoped.

## Git Commit Conventions

- Make small, reviewable commits with imperative summaries, such as
  `Add configuration loader` or `Document source validation`.
- Use a concise body when context, assumptions, or risks need explanation.
- Keep generated files, local environments, credentials, and unrelated
  formatting changes out of commits.
- Do not mix refactors with functional changes unless the relationship is
  necessary and documented.

## Configuration Management

- Keep non-secret, shared settings in version-controlled YAML under `config/`
  or `knowledge/`.
- Validate configuration shape and report actionable errors when loading fails.
- Treat commodity relationships as research assumptions: review changes for
  direction, mechanism, and affected instruments.
- Do not hard-code watchlists, source priorities, or environment-specific
  settings in application logic.

## Data Source Reliability

- Prefer primary, official, or established financial and research sources.
- Record source identity, publication time, retrieval time, and original link
  when data collection is introduced.
- Separate reported facts from model inference and label uncertainty.
- Cross-check market-moving claims when practical; do not treat a single source
  as conclusive without context.
- Respect source terms of use, licensing, rate limits, and applicable law.

## Security and Secret Management

- Store API keys, credentials, tokens, and email settings only in local
  environment variables or an untracked secret manager.
- Use `.env.example` only for variable names and safe example values; never put
  live secrets in it.
- Do not log credentials, private source content, personal data, or sensitive
  configuration values.
- Apply least-privilege access to future data sources, storage, and delivery
  integrations, and rotate exposed credentials immediately.
