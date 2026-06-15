# strategy-new

Quick strategy scaffolding generator for crypto trading system.

## Description

Creates new trading strategy from templates including strategy file, config, and unit tests. Minimizes boilerplate and ensures consistent structure.

## When to Use

- Create a new trading strategy from scratch
- Initialize strategy with proper structure
- Generate strategy configuration and tests together

**Trigger:** "create new strategy", "initialize momentum strategy", "new grid strategy"

## Instructions

1. Ask user for strategy type (grid/trend/arbitrage/custom)
2. Generate strategy file from template in src/strategy/
3. Create YAML config in config/strategies/
4. Generate test skeleton in tests/unit/
5. Register strategy in strategy registry
6. Output summary of created files

Templates stored in ~/.claude/skills/strategy-new/templates/

## Examples

**Example 1:**
User: "Create a new trend following strategy"
Assistant: [Prompts for parameters, generates src/strategy/trend_following.py, config/strategies/trend_following.yaml, tests/unit/test_trend_following.py]

**Example 2:**
User: "Initialize momentum strategy with RSI"
Assistant: [Creates strategy skeleton with RSI indicator placeholders]
