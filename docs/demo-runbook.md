# Futures Intelligence Assistant — Demo Runbook

English | [简体中文](demo-runbook.zh-CN.md)

This runbook is for presenting the bounded Huatai Futures demo clearly and safely. It complements the main README: the README explains the project, while this document gives the operator a practical narrative, checks, fallback options, and concise answers for a live demonstration.

## Demo goal

By the end of the demo, the audience should understand three things:

1. The system can turn live broker research into structured, commodity-oriented research intelligence.
2. It preserves evidence and treats commodity identity separately from directional evidence.
3. It abstains instead of inventing a bullish or bearish conclusion when the evidence is insufficient.

The system performs the mechanical first pass—collection, extraction, commodity identification, evidence preservation, deterministic analysis, and commodity aggregation. It supports researcher judgment; it does not replace it.

## 30-second opening

> Futures researchers receive more reports and market updates than they should have to organize manually. This system handles that first pass: it collects the material, identifies the relevant commodities, preserves the evidence, and builds traceable commodity views. It does not make trading decisions for the researcher. The important design choice is that it only expresses direction when the available evidence supports one.

## Pre-demo checklist

- [ ] Open a terminal at the repository root.
- [ ] Confirm the branch is `main` and the worktree is clean.
- [ ] Confirm the repository-local `.venv` exists.
- [ ] Confirm the machine has normal network access to the Huatai Futures website.
- [ ] Do not prepare an OpenAI key; this demo does not require one.
- [ ] Do not start a database or Morning Brief service.
- [ ] Use a terminal width that keeps the report output readable.
- [ ] Keep the verified fallback excerpt below available in case the live source is unavailable.

Useful preflight commands:

```sh
git status --short
git branch --show-current
git log -1 --oneline
test -x .venv/bin/python3
```

Expected state before the demo: `git status --short` prints nothing, the branch is `main`, and the virtual-environment check succeeds. A separate network probe is optional; the demo command itself is the meaningful live check.

## 3–5 minute main demo

| Time | Operator action | Audience takeaway |
| --- | --- | --- |
| 0:00–0:30 | Frame the research workflow problem. | The system reduces mechanical first-pass work. |
| 0:30–1:00 | Explain the bounded live source and pre-analysis selection. | The sample is controlled and cannot be chosen by its result. |
| 1:00–2:30 | Run the command and let the pipeline complete. | Live reports become structured, deterministic output. |
| 2:30–4:00 | Walk through the first commodity-specific report. | Commodity identity and directional evidence are separate. |
| 4:00–5:00 | Explain the commodity view, broader reports, and boundaries. | Abstention and traceability are deliberate trust properties. |

### Step 1 — Explain the problem

> Researchers should spend their time judging evidence and market implications, not repeatedly opening PDFs, finding the commodity, and reorganizing the same basic information. This tool automates that mechanical first pass so the researcher can begin from a structured, traceable view.

### Step 2 — Explain what the command will do

> This command reads the live Huatai research listing and selects at most three reports. Titles that explicitly identify a tracked commodity come first; newer broader reports fill any remaining slots. Selection happens before PDF extraction and analysis, so direction, confidence, provenance, and reasoning cannot be used to cherry-pick the sample.

The sequence is:

```text
title identity and recency
  → selection
  → PDF retrieval and extraction
  → information ranking
  → deterministic analysis
  → commodity and global aggregation
  → bounded presentation
```

`InformationRanker` remains part of analytical processing. Report details are presented in the earlier selected/collected order so the audience sees the same sample order that was chosen before analysis.

### Step 3 — Run the exact command

From the repository root:

```sh
NO_PROXY=htfc.com,www.htfc.com \
no_proxy=htfc.com,www.htfc.com \
PYTHONPATH=src .venv/bin/python3 -m futures_intelligence.main htfc-demo
```

Expected runtime behavior:

- Access the live Huatai listing.
- Select no more than three reports.
- Retrieve and extract the selected PDFs.
- Run deterministic rule-based analysis.
- Print bounded report details, commodity views, a global view, and a compact demo brief.

These statements apply specifically to `htfc-demo`: it does not construct or call `LLMAnalyst` or an OpenAI client, invoke `MorningBriefService`, require database persistence, write trading orders, or issue trade recommendations.

Do not promise a fixed duration or a particular set of reports. Both depend on the current source and network conditions.

### Step 4 — What to point at first

If a commodity-specific report appears, point to these fields in order:

1. `主要品种`
2. `报告方向`
3. `报告分析置信度`
4. `判定依据`

The previously accepted live Bitumen example showed:

```text
主要品种：Bitumen
报告方向：中性 (neutral)
报告分析置信度：80/100
判定依据：no_directional_signal
```

Suggested explanation:

> The most important result here is not whether the report is bullish. The system first identified Bitumen as the report's primary commodity. It then found that the current deterministic rules did not have sufficiently explicit directional evidence, so it kept the report neutral instead of forcing a view.

### Step 5 — Explain the commodity view

Point to the corresponding section:

```text
品种视图

Bitumen
方向：中性 (neutral)
聚合方向置信度：0/100
报告数：1
```

Suggested explanation:

> The commodity view groups report evidence by commodity. A non-directional report can still belong to a commodity view, but it does not become a bullish or bearish contributor. In this accepted example, one Bitumen report was represented, and because it supplied no eligible directional evidence, aggregate directional confidence remained zero.

The report count reflects the current selected sample; it is not expected to be one on every run.

### Step 6 — Explain broader reports

The accepted run also included a macro policy report and a broad black-sector report as fallbacks. They were processed successfully without being forced into a Primary commodity identity.

> That is another conservative boundary. A broad title such as `黑色专题` does not automatically identify a specific tracked contract such as Iron Ore or Coal. The system requires explicit commodity identity evidence rather than guessing from a sector label.

## How to explain 80/100 versus 0/100

Use this wording if the audience notices the two scores:

> Report analysis confidence of `80/100` does not mean an 80% probability that Bitumen is neutral. It is confidence in the deterministic report-level analysis, including the confidently recognized Primary commodity. Aggregate directional confidence of `0/100` means that the report supplied no eligible bullish or bearish evidence to directional aggregation. The system recognized the report, but deliberately declined to manufacture a direction. That is a trust feature, not a failure.

Avoid describing either value as a market probability.

## What not to say

- “It predicts the market.”
- “The system thinks Bitumen is always neutral.”
- “An 80 score means an 80% probability.”
- “A zero score means the model failed.”
- “It replaces the researcher.”
- “It automatically recommends or executes trades.”
- “It covers every futures commodity.”
- “It uses AI to read everything.”

Prefer precise language: the demo organizes research evidence, applies reviewed deterministic rules, and abstains when direction is unsupported.

## Likely questions and good answers

### Why is Bitumen report analysis confidence 80 but aggregate directional confidence 0?

The report-level score describes confidence in the deterministic analysis, including its Primary commodity focus. The aggregate score considers eligible directional contributions. This report had no qualifying bullish or bearish evidence, so its directional contribution was zero.

### Why does the system sometimes stay neutral?

Because a report can identify a commodity, provide background, or use qualified or conflicting language without supporting a reliable directional conclusion. Neutral or non-contributing output is the correct conservative result in those cases.

### Why was the black-sector report not assigned to a specific commodity?

`黑色专题` is a broad sector label. Without explicit commodity evidence, the system does not guess which contract the report primarily concerns.

### Does the demo use ChatGPT or OpenAI?

The bounded `htfc-demo` route is deterministic and requires neither OpenAI nor an API key. It does not construct or call the LLM analyst path. The wider repository can contain other analysis components; this statement applies specifically to this demo route.

### Why only three reports?

The current demo is deliberately bounded so its behavior remains inspectable and reproducible. The architecture itself is not fundamentally limited to three reports.

### Can it support other brokers or sources?

The collection and normalization boundaries are modular and source-neutral. Other broker research, official data, or market-data sources are natural extensions, but they should not be presented as completed live integrations unless they have actually been implemented and verified.

### Can it make trading decisions?

No. It organizes research evidence and produces research views. It does not issue trading recommendations, place orders, or replace researcher judgment.

### Why use deterministic rules instead of an LLM here?

Deterministic rules make evidence boundaries inspectable, behavior stable, and unsupported conclusions easier to prevent and test. LLMs may be useful in other layers or future work, but this demo deliberately shows that the core pipeline can operate without one. This is a design choice for this bounded workflow, not a claim that deterministic rules are always superior.

## Live-output variation

Huatai's live listing changes over time. The exact selected reports can differ, and Bitumen may not appear on a future day. Judge the demo by the pipeline behavior rather than by one hard-coded title.

If no tracked-commodity title is available, the selector may legitimately return broader fallback reports and the output may contain zero commodity views. Explain it this way:

> Today's current listing does not contain a report title that explicitly matches the tracked commodity registry, so the system followed its declared fallback and selected the newest broader reports. It did not invent commodity ownership from a broad title.

Do not rerun the command repeatedly in search of a more attractive result.

## Failure and fallback playbook

| Situation | What to do | What not to do |
| --- | --- | --- |
| The command succeeds, but the selected reports differ. | Continue normally and explain that the live listing changes. | Do not claim that the accepted Bitumen example must appear every time. |
| The command succeeds with zero commodity views. | Explain the conservative fallback and curated commodity coverage. | Do not rerun repeatedly hoping for a prettier result. |
| Huatai times out or is unavailable. | State that the source endpoint is temporarily unavailable, then use the previously verified excerpt below. | Do not change code or increase timeouts during the demo; do not imply the command succeeded. |
| Python or dependency startup fails. | Confirm that the command uses `.venv/bin/python3` and that the repository-local environment exists. | Do not switch to system `python3` for the demo command. |
| An unexpected traceback appears. | Stop the live execution and continue with the verified excerpt and conceptual walkthrough. | Do not improvise code changes in front of the audience. |

## Previously verified live output

Use this short historical excerpt only as a fallback. If the live command fails, clearly say that this is previously verified output—not the current run.

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

## 20-second closing

> The system is not trying to replace the researcher's conclusion. It turns a large volume of daily research into traceable commodity views and makes clear where directional evidence does—or does not—exist. The most valuable next steps are broader reviewed commodity and evidence coverage, additional reliable sources, and tighter integration with the morning research workflow.

## Technical appendix

Run the bounded live demo from the repository root:

```sh
NO_PROXY=htfc.com,www.htfc.com \
no_proxy=htfc.com,www.htfc.com \
PYTHONPATH=src .venv/bin/python3 -m futures_intelligence.main htfc-demo
```

Run the full offline test suite:

```sh
PYTHONPATH=src .venv/bin/python3 -m unittest discover -s tests -v
```

At the accepted application/demo checkpoint before this documentation-only package:

- 474 offline tests passed.
- The curated commodity registry contained 19 tracked identities.
- The bounded demo selected at most three reports.

For product and architecture context, see the [English README](../README.md) or [简体中文 README](../README.zh-CN.md).
