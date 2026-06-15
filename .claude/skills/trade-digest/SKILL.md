# trade-digest

Trading performance report generator with visualizations.

## Description

Generates comprehensive trading reports for specified time periods. Queries database for aggregated metrics, creates charts, and exports reports in Markdown/HTML format.

## When to Use

- Generate weekly/monthly performance reports
- Summarize recent trading activity
- Compare strategy performance
- Create reports for review

**Trigger:** "generate weekly report", "trading summary this month", "performance digest"

## Instructions

1. Query database for time period (aggregated, not raw trades)
2. Calculate key metrics (return, win rate, drawdown)
3. Generate Plotly charts (equity curve, drawdown)
4. Compare multiple strategies if applicable
5. Render Markdown report from template
6. Save to data/reports/ with timestamp

Report templates in ~/.claude/skills/trade-digest/templates/

## Examples

**Example 1:**
User: "Generate this week's trading report"
Assistant: [Queries last 7 days, outputs: "7 trades, 57% win rate, +3.2% return", saves report with charts]

**Example 2:**
User: "Compare grid vs trend strategy this month"
Assistant: [Generates side-by-side comparison report with performance metrics]
