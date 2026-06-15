# config-lint

Configuration file validator using JSON Schema.

## Description

Validates YAML/JSON configuration files against schemas. Checks required fields, parameter ranges, and cross-validates consistency between related configs.

## When to Use

- After editing strategy configuration
- Before running backtest or live trading
- Validating .env file completeness
- Configuration error troubleshooting

**Trigger:** "validate config", "check strategy yaml", "lint configuration"

## Instructions

1. Load appropriate JSON schema for config type
2. Validate YAML/JSON structure
3. Check required fields present
4. Verify parameter ranges (e.g., stop_loss in 0-1)
5. Cross-validate consistency (strategy config vs code)
6. Generate validation report

Schemas in ~/.claude/skills/config-lint/schemas/

## Examples

**Example 1:**
User: "Validate grid strategy configuration"
Assistant: [Checks config/strategies/grid_trading.yaml against schema, finds: "Error: num_grids must be integer, got '20'"]

**Example 2:**
User: "Check if .env is complete"
Assistant: [Compares .env with .env.example, reports: "Missing: HERMES_API_KEY"]
