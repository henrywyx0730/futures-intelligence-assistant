# Futures Intelligence Assistant

English | [简体中文](README.zh-CN.md)

Futures Intelligence Assistant is research infrastructure for turning unstructured market and broker information into structured, traceable, commodity-oriented research views. It does not try to replace a researcher's judgment or make trading decisions. It organizes the first pass of evidence and expresses a directional conclusion only when that evidence is sufficiently explicit.

**Core principle: evidence before conclusion.** A report can be confidently identified as being about a commodity while still providing no eligible bullish or bearish signal. In that case, abstention is the intended result—not a system failure.

### Try the bounded live demo

From the repository root, after creating the project virtual environment and installing `requirements.txt`:

```sh
NO_PROXY=htfc.com,www.htfc.com \
no_proxy=htfc.com,www.htfc.com \
PYTHONPATH=src .venv/bin/python3 -m futures_intelligence.main htfc-demo
```

The demo processes at most three Huatai Futures reports through the deterministic path. It requires live access to the official Huatai site, but it does not require OpenAI, an API key, or a database.

## Why this project exists

Futures researchers often begin the day with a large set of overnight reports, notices, data releases, and market updates. Before analysis can begin, someone must repeatedly open documents, identify the relevant contracts, separate direct evidence from background mentions, and organize the material by commodity.

This project reduces that mechanical first-pass workload. Its purpose is to help researchers spend more time evaluating evidence, assumptions, and market implications—not to automate the final judgment.

## What it does today

- Collects and normalizes source material while preserving source, URL, publication time, and extraction provenance.
- Supports bounded HTML and text-layer PDF research-report processing, including the current Huatai Futures demo path.
- Identifies commodities from title and body evidence and distinguishes a report's **Primary** focus from commodities that are only **Mentioned**.
- Applies deterministic, reviewable rules to explicit market movement and factual fundamental statements.
- Handles qualified language, same-market conflicts, horizon conflicts, and cross-commodity ambiguity conservatively.
- Records structural relative-value observations without turning them into unsupported bullish or bearish conclusions.
- Carries structured directional provenance and commodity-scoped evidence into deterministic commodity and global aggregation.
- Produces bounded report reasoning and a compact commodity-first demo brief.

The curated [commodity registry](knowledge/commodity_keywords.yaml) currently contains 19 tracked identities. Examples include Crude Oil, Fuel Oil, Low-Sulfur Fuel Oil, Bitumen, Copper, Aluminum, Silver, Gold, Iron Ore, Soybean Meal, Corn, Live Hog, Propylene, and Ethylene Glycol. This is useful working coverage, not a claim of comprehensive Chinese futures-market coverage.

## How the pipeline works

```text
Sources
  ↓
Collectors / Fetchers / Adapters
  ↓
MarketInformation
  ↓
Information Ranking
  ↓
Deterministic Report Analysis
  ↓
Commodity Relevance (Primary / Mentioned)
  ↓
Commodity and Global Aggregation
  ↓
Demo Brief / Morning Intelligence Layer
```

The architecture is source-neutral. Huatai Futures is one current research-report implementation, not the architecture itself. Additional broker research, exchange notices, official statistics, customs and inventory data, market data, and news can be added through the same collection and normalization boundaries as future work.

## Evidence-first analysis

The system keeps several questions separate:

1. **What is the report about?** Commodity matching records the exact title or body occurrence. Primary relevance requires stronger evidence than a contextual mention.
2. **Does the report contain directional evidence?** Direction is resolved only from reviewed deterministic signals. Commodity identity by itself is not directional evidence.
3. **Which commodity does the evidence belong to?** Commodity-scoped evidence prevents a statement about one market from being silently attributed to another.
4. **Should the evidence contribute to aggregation?** Directional provenance distinguishes direct evidence from qualification, conflict, structural context, and no-signal outcomes.

When evidence is qualified, contradictory, horizon-dependent, structurally non-directional, or attached to another commodity, the system prefers an explicit abstention to invented precision. Relative-value and spread observations remain structural observations rather than trading recommendations.

## Live demo example

The final bounded live demo processed current Huatai Futures reports and prioritized this title because it explicitly identifies a tracked commodity:

> 华泰期货石油沥青专题20260904：供应端矛盾支撑市场强现实，预期仍存变数——结合华南沥青调研情况分析

The report was identified as **Primary Bitumen**, while the deterministic analysis found no eligible directional signal:

```text
Primary commodity:                 Bitumen
Report direction:                  neutral
Report analysis confidence:        80/100
Directional provenance:            no_directional_signal

Bitumen aggregate direction:       neutral
Aggregate directional confidence:  0/100
Report count:                       1
```

These numbers are not contradictory. `80/100` is the confidence attached to the report-level deterministic analysis, including its recognized commodity focus; it is not an 80% probability that Bitumen is directionally neutral. `0/100` at the aggregate level means that this report supplied no eligible bullish or bearish contribution to directional aggregation.

This example demonstrates conservative separation between commodity identity and market direction. It is not a Bitumen forecast and does not imply that Bitumen reports are always neutral.

## Running the bounded Huatai demo

### Prerequisites

- Python 3 with standard virtual-environment support
- Live network access to the official Huatai Futures site

Create the repository-local environment and install the declared dependencies:

```sh
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
```

Windows users can use the repository's setup script:

```bat
scripts\setup_windows.bat
```

Run the demo from the repository root:

```sh
NO_PROXY=htfc.com,www.htfc.com \
no_proxy=htfc.com,www.htfc.com \
PYTHONPATH=src .venv/bin/python3 -m futures_intelligence.main htfc-demo
```

The isolated demo route:

- Selects at most three reports.
- Prioritizes reports whose **titles** explicitly identify a tracked commodity.
- Fills remaining slots with the newest broader reports when fewer than three title-matched reports are available.
- Selects before PDF extraction or analysis, so direction, confidence, provenance, and reasoning cannot influence membership or order.
- Preserves the selected order in report-detail presentation while retaining normal ranking for analytical processing.
- Uses the deterministic rule-based analyst and does not construct or call the LLM/OpenAI path.
- Does not invoke the production Morning Brief service or require database persistence.

The Huatai source remains disabled in ordinary configured collection; this command runs the deliberately isolated bounded demo path.

## Example output

```text
报告 1
标题：华泰期货石油沥青专题20260904：供应端矛盾支撑市场强现实，预期仍存变数——结合华南沥青调研情况分析
主要品种：Bitumen
报告方向：中性 (neutral)
报告分析置信度：80/100
判定依据：no_directional_signal

品种视图
Bitumen
方向：中性 (neutral)
聚合方向置信度：0/100
报告数：1
```

Output is bounded and intended for research support, not trading advice.

## Testing

Run the offline test suite from the repository root:

```sh
PYTHONPATH=src .venv/bin/python3 -m unittest discover -s tests -v
```

At the final demo checkpoint, the full offline test suite passed 474 tests. This is a checkpoint result, not a permanent test-count guarantee.

## Current boundaries

- Commodity coverage is curated rather than comprehensive, and coverage depth varies by commodity and rule family.
- Directional rules are deterministic and intentionally conservative; many reports will correctly remain neutral or non-contributing.
- Broad sector labels such as `黑色专题` are not automatically mapped to specific futures contracts without explicit identity evidence.
- The live Huatai demo is intentionally limited to three selected reports and is not a complete daily research universe.
- Structural spread and relative-value language is not converted into trade recommendations.
- The project is research and information infrastructure, not an automated trading or order-execution system.
- It does not predict returns, estimate trade profitability, or issue investment recommendations.

## Roadmap

- Broaden carefully reviewed commodity identity coverage.
- Expand deterministic evidence coverage without weakening abstention safeguards.
- Add further broker-research, official-data, market-data, and news sources through modular adapters.
- Strengthen morning intelligence generation and researcher-facing traceability.
- Improve presentation for reviewing evidence, provenance, and commodity-level conclusions.

## Project principles

- Evidence before conclusion
- Preserve source and analytical provenance
- Prefer abstention to false precision
- Separate commodity ownership from directional evidence
- Keep aggregation deterministic and inspectable
- Keep source integrations modular and bounded

## Disclaimer

This project is for research support and information organization. It does not provide investment advice, trading recommendations, or trade execution.
