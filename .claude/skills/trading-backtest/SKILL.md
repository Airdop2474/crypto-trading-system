# trading-backtest

Strategy backtest executor for crypto trading system.

## Description

Executes strategy backtests against historical market data with optimized token usage. Loads only necessary data from database, uses templated reports, and outputs actionable metrics.

## When to Use

- Test a trading strategy against historical data
- Validate strategy changes before deployment  
- Compare strategy performance across parameters
- Generate performance reports for analysis

**Trigger:** "backtest grid strategy", "test on historical data", "run backtest BTC/USDT"

## Instructions

1. Validate environment and database connection
2. Load strategy config from YAML (not source code)
3. Query historical data from database efficiently
4. Execute backtest engine
5. Generate report from template
6. Output key metrics summary

See detailed implementation in project documentation.

## Examples

**Example 1:**
User: "Backtest grid strategy on BTC/USDT last year"
Assistant: [Loads config/strategies/grid_trading.yaml, queries DB, runs backtest, outputs metrics]

**Example 2:**
User: "Test trend strategy with 50-day MA"
Assistant: [Validates strategy exists, runs backtest, generates report in data/reports/]
