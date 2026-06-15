# token-budget

Token usage analyzer and optimizer.

## Description

Analyzes token consumption patterns, identifies wasteful operations, and suggests optimizations. Helps keep development costs under control.

## When to Use

- Before large operations
- When sessions feel expensive
- To optimize workflow

**Trigger:** "analyze token usage", "how much will this cost", "optimize tokens"

## Instructions

1. Estimate tokens for planned operation
2. Identify high-cost patterns:
   - Reading large files repeatedly
   - Unnecessary full-file reads
   - Redundant searches
3. Suggest optimizations:
   - Use Grep instead of Read
   - Cache results
   - Use incremental analysis
4. Show cost breakdown

## Examples

User: "how much to implement MACD indicator"
Assistant: [Estimates: Read (500), Write (800), Tests (600) = ~1900 tokens]

User: "analyze last session"
Assistant: [Reports: 15k tokens, suggests: "Use Grep for searches saved 3k tokens"]
