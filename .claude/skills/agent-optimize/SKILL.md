# agent-optimize

AI Agent analysis trigger and optimizer for trading strategies.

## Description

Collects trading data, calls AI Agent API (Hermes/OpenClaw) for analysis, parses structured recommendations, and generates actionable optimization plans.

## When to Use

- Analyze recent trading performance
- Get AI-driven parameter optimization suggestions
- Diagnose strategy issues
- Generate improvement recommendations

**Trigger:** "let agent analyze performance", "optimize strategy with AI", "agent review trades"

## Instructions

1. Collect analysis data (trades, metrics, equity curve) from database
2. Load appropriate prompt template from prompts/
3. Call Agent API with structured schema
4. Parse JSON recommendations
5. Generate optimization plan (requires human approval)
6. Save analysis report to database

Prompt templates in ~/.claude/skills/agent-optimize/prompts/

## Examples

**Example 1:**
User: "Let agent analyze last week's performance"
Assistant: [Collects 7-day data, calls Hermes API, outputs: "Recommendation: Increase grid spacing by 15%, reduce position size"]

**Example 2:**
User: "AI optimize grid parameters"
Assistant: [Analyzes grid strategy, suggests parameter adjustments with reasoning]
