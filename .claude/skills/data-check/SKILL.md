# data-check

Time-series data health checker for crypto trading system.

## Description

Validates historical market data integrity using SQL queries. Detects gaps, anomalies, and quality issues without loading full datasets into memory.

## When to Use

- Check data completeness before backtest
- Detect missing time intervals (gaps)
- Find anomalous price movements
- Validate data quality after download

**Trigger:** "check data integrity", "validate BTC data", "data quality check"

## Instructions

1. Query database metadata (not full data)
2. Run gap detection SQL query
3. Run anomaly detection (price spikes, zero volume)
4. Generate data health report
5. Suggest fixes (re-download, interpolation)

SQL queries stored in ~/.claude/skills/data-check/queries/

## Examples

**Example 1:**
User: "Check if BTC/USDT data is complete"
Assistant: [Queries ohlcv table, finds 3 gaps in February, suggests re-download]

**Example 2:**
User: "Validate all data quality"
Assistant: [Scans all symbols, reports anomalies: ETH spike on 2024-03-15]
