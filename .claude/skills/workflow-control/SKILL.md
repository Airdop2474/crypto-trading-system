# workflow-control

Master workflow controller for development process. Ensures proper analysis before code changes.

## Description

This is the MASTER SKILL that controls the development workflow. It prevents jumping straight to code changes by enforcing a structured process: understand requirements → analyze context → plan changes → verify → execute with confirmation.

**Key principle: Think first, code later.**

## When to Use

**ALWAYS use this skill for:**
- Adding new features
- Modifying existing code
- Refactoring modules
- Implementing user requests

**DO NOT use for:**
- Simple documentation updates
- Reading/viewing files
- Running tests only

**Trigger:** "add feature X", "implement Y", "modify Z", or any code change request

## Instructions

### Phase 1: Requirement Understanding

1. **Parse user request**
   - Extract what needs to be done
   - Identify unclear points
   - Ask clarifying questions if needed

2. **Call /project-context**
   - Understand current project state
   - Identify relevant modules
   - Check current development phase

3. **Check existing implementation**
   - Use Grep to find related code
   - Check if feature already exists
   - Identify dependencies

### Phase 2: Impact Analysis

4. **List affected files**
   ```
   Files to modify:
   - src/strategy/indicators.py (add new indicator)
   - tests/unit/test_indicators.py (add tests)
   - config/strategies/example.yaml (update config)
   ```

5. **Estimate complexity**
   - Lines of code to add/modify
   - New dependencies needed
   - Token cost estimate

6. **Recommend Skills to use**
   ```
   Recommended workflow:
   1. /code-style - Check current code style
   2. Implement changes
   3. /config-lint - Validate configuration
   4. /risk-audit - Security check (if touching execution/)
   ```

### Phase 3: Planning

7. **Generate task checklist**
   ```
   [ ] Read existing indicator implementations
   [ ] Add RSI calculation function
   [ ] Update indicator registry
   [ ] Write unit tests
   [ ] Update configuration schema
   [ ] Run /code-style verification
   ```

8. **Show execution plan**
   ```
   Execution Plan:
   
   Step 1: Read context
     - Read src/strategy/indicators.py (current)
     
   Step 2: Implement
     - Add calculate_rsi() function
     - Register in INDICATOR_REGISTRY
     
   Step 3: Test
     - Add test_rsi_calculation()
     - Add test_rsi_edge_cases()
     
   Step 4: Verify
     - Run /code-style
     - Run pytest
   
   Estimated tokens: ~3000
   Estimated time: 10 minutes
   ```

### Phase 4: Confirmation

9. **Wait for user approval**
   ```
   📋 Plan Summary:
   - Files to modify: 2
   - Tests to add: 2
   - Token cost: ~3000
   - Risk level: LOW
   
   Proceed with execution? [y/n]
   ```

10. **If approved, execute**
    - Follow the plan step by step
    - Call verification Skills as planned
    - Log to /dev-log

### Phase 5: Post-Execution

11. **Verification**
    - Run planned verification Skills
    - Check all tests pass
    - Confirm no regressions

12. **Log to dev-log**
    ```
    Call /dev-log with:
    - What was done
    - Files changed
    - Tests added
    - Verification results
    ```

## Examples

### Example 1: Feature Addition

```
User: "Add MACD indicator to the strategy system"

Assistant (via /workflow-control):

🔍 Phase 1: Understanding
- Requirement: Add MACD (Moving Average Convergence Divergence) indicator
- Calling /project-context to check strategy structure...

📊 Current Context:
- Strategy layer: src/strategy/
- Indicators module exists: src/strategy/indicators.py
- Tests exist: tests/unit/test_indicators.py

🎯 Phase 2: Impact Analysis
Files to modify:
  1. src/strategy/indicators.py - Add calculate_macd()
  2. tests/unit/test_indicators.py - Add test cases
  
Dependencies: pandas-ta (already installed ✓)

📝 Phase 3: Plan
Task Checklist:
  [ ] Read current indicator implementations
  [ ] Implement MACD calculation (signal, histogram)
  [ ] Add to indicator registry
  [ ] Write unit tests (3 test cases)
  [ ] Verify with /code-style

Token estimate: ~2500
Risk level: LOW (no execution layer changes)

Proceed? [y/n]
```

### Example 2: Refactoring

```
User: "Refactor the backtest engine to improve performance"

Assistant (via /workflow-control):

🔍 Phase 1: Understanding
- Requirement: Performance optimization of backtest engine
- Need clarification: Which part is slow?

❓ Questions:
1. Have you run /perf-analyze? What did it find?
2. Is the bottleneck in data loading or calculation?
3. Target speedup goal? (2x, 5x, 10x?)

[Wait for user answers before proceeding]
```

### Example 3: Safety Check

```
User: "Modify order execution to increase position size"

Assistant (via /workflow-control):

🔍 Phase 1: Understanding
- Requirement: Increase position size in order execution
- ⚠️ HIGH RISK: Affects fund safety

📊 Phase 2: Analysis
File affected: src/execution/order_manager.py
Risk level: HIGH

⚠️ Required verifications:
  1. /risk-audit - MANDATORY before changes
  2. /config-lint - Validate new limits
  3. Review by human - Position sizing logic

Calling /risk-audit first...

[Risk audit results]

Proceed only after:
  ✓ Risk audit passes
  ✓ You review the limits
  ✓ Configuration updated
  
Proceed? [y/n]
```

## Decision Tree

```
User Request
    ↓
Is it a code change?
    ├─ No → Direct response
    └─ Yes → /workflow-control
        ↓
Understand requirement
    ├─ Clear? → Continue
    └─ Unclear? → Ask questions → Wait
        ↓
Call /project-context
        ↓
Analyze impact
    ├─ High risk? → Call /risk-audit first
    └─ Low risk? → Continue
        ↓
Generate plan
        ↓
Estimate cost
        ↓
Show plan & wait for confirmation
    ├─ Approved → Execute → Verify → Log
    └─ Rejected → Revise plan
```

## Token Optimization

- Only read files that will be modified
- Use Grep instead of reading multiple files
- Cache project structure (from /project-context)
- Reuse previous analysis if request similar
- Show plan before executing (avoid wasted work)

## Integration with Other Skills

```
/workflow-control orchestrates:
    │
    ├─→ /project-context (understand current state)
    ├─→ /code-style (verify before/after)
    ├─→ /risk-audit (security check)
    ├─→ /config-lint (validate configs)
    ├─→ /token-budget (estimate cost)
    └─→ /dev-log (record completion)
```

## Notes

**This skill should be invoked AUTOMATICALLY by Claude Code when:**
- User requests code changes
- User says "implement", "add", "modify", "refactor"
- Task involves writing/editing code

**Skip this skill only when:**
- User explicitly says "skip workflow" or "direct implementation"
- Simple file reading/viewing
- Documentation only changes
- Running existing scripts
