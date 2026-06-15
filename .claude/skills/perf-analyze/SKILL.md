# perf-analyze

Performance bottleneck analyzer for trading system.

## Description

Analyzes system performance by scanning logs for slow operations, checking database query efficiency, and detecting redundant computations. Suggests optimization strategies.

## When to Use

- Backtest is too slow
- Database queries taking too long
- System performance degradation
- Before optimizing with Rust

**Trigger:** "why is backtest slow", "analyze performance", "find bottlenecks"

## Instructions

1. Analyze recent logs for operations >1s
2. Check database queries for missing indexes
3. Detect repeated calculations in loops
4. Check memory usage patterns
5. Suggest optimizations (caching, batching, indexes, Rust)
6. Generate performance report

Optimization patterns in ~/.claude/skills/perf-analyze/patterns/

## Examples

**Example 1:**
User: "Backtest is too slow, analyze why"
Assistant: [Scans logs, finds: "Database query repeated 10000x in loop. Suggest: batch load data before loop"]

**Example 2:**
User: "Optimize database performance"
Assistant: [Checks queries, recommends: "Add index on (symbol, time) for 10x speedup"]
