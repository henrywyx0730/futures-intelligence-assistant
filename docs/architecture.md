# Futures Intelligence Assistant Architecture

## 1. Project Overview

Futures Intelligence Assistant is a personal AI-powered futures research system.

The goal is not automated trading.

The goal is to help understand:

Market Event
↓
Supply / Demand Impact
↓
Commodity Transmission
↓
Futures Market Interpretation
↓
Research Brief

The system acts as a personal futures research assistant that collects market information, analyzes fundamental impacts, and generates daily morning briefs before futures research meetings.

---

# 2. Core Design Principle

This project is not a simple news summarizer.

A traditional news system:

News
↓
Summary

This project:

Market Event
↓
Fundamental Analysis
↓
Supply Impact
↓
Demand Impact
↓
Inventory Impact
↓
Cost Transmission
↓
Affected Futures Products
↓
Research Interpretation

Example:

Middle East conflict escalation
↓
Transportation risk increases
↓
Effective crude oil supply decreases
↓
Crude oil price increases
↓
Petrochemical costs increase
↓
BR / Styrene receive cost support

---

# 3. System Architecture

```
Data Sources
    ↓
Research Reports + News Sources
    ↓
Information Collector
    ↓
Information Filter
    ↓
AI Analysis Engine
    ↓
Commodity Knowledge Layer
    ↓
Morning Brief Generator
    ↓
Email Delivery
```

---

# 4. Major Components

## 4.1 Data Collection Layer

Responsible for collecting market information.

Sources include:

- Futures company research reports
- Financial news
- Macro data
- Commodity-specific information

Examples:

- Reuters
- Financial news platforms
- Futures company research departments

The collector only collects information.

It does not perform market interpretation.

---

## 4.2 Information Filtering Layer

Purpose:

Reduce information noise.

Responsibilities:

- Remove irrelevant information
- Classify information
- Identify affected commodities

Categories:

- Macro
- Energy
- Metals
- Black commodities
- Chemicals
- Agriculture
- Financial futures

---

## 4.3 Commodity Knowledge Layer

The core intelligence layer.

It stores relationships between:

Events
↓
Market Factors
↓
Commodities

Example:

```
Crude Oil

Input Factors:
- Geopolitics
- OPEC production
- Inventory

Downstream Impact:

Crude Oil ↑
↓
Petrochemical Cost ↑
↓
BR ↑
```

This layer allows AI to reason using commodity industry knowledge.

---

## 4.4 AI Analysis Engine

The AI engine transforms collected information into futures research logic.

Every analysis should answer:

### Supply

Does this event affect supply?

Example:

Factory shutdown
↓
Supply decreases
↓
Price pressure increases


### Demand

Does this event affect demand?

Example:

Infrastructure investment
↓
Copper demand increases
↓
Copper bullish


### Inventory

Does this event affect inventory?

Bullish:

- Inventory decline
- Supply shortage

Bearish:

- Inventory accumulation
- Oversupply

---

# 5. Output Layer

The first output format:

Daily Morning Futures Brief

Example:

```
Morning Futures Brief

1. Overnight Market Summary

2. Major Commodity Movements

3. Supply-Demand Explanation

4. Important Events Today

5. Watchlist Impact

6. Hedging Opportunities
```

---

# 6. Watchlist

The initial watchlist focuses on:

## Energy

- Crude Oil

## Chemical

- BR
- Styrene
- PTA

## Metals

- Copper
- Aluminum
- Silver

## Black

- Iron Ore
- Rebar
- Coal

## Agriculture

- Soybean Meal
- Corn

## Financial Futures

- IF
- IM
- T

---

# 7. Development Philosophy

## Phase 1

Build reliable information collection.

## Phase 2

Generate AI-powered morning briefs.

## Phase 3

Build commodity relationship knowledge.

## Phase 4

Create personal futures research assistant.

Long-term goal:

A personal Bloomberg-style research assistant.

Not a trading bot.

A learning and decision-support system.