# risk-audit

Trading system security and risk control auditor.

## Description

Scans trading system code for security vulnerabilities and risk control issues. Focuses on API keys, order limits, fund safety, and SQL injection risks.

## When to Use

- Pre-deployment security check
- After modifying order execution logic
- Before going live with real funds
- Regular security audits

**Trigger:** "audit risk controls", "security check before live", "check for vulnerabilities"

## Instructions

1. Scan execution/ and strategy/ modules for risk controls
2. Check for hardcoded API keys or secrets
3. Verify order amount limits exist
4. Check SQL injection vulnerabilities
5. Validate environment variable usage
6. Generate security audit report with fix recommendations

Audit rules in ~/.claude/skills/risk-audit/rules/

## Examples

**Example 1:**
User: "Audit risk controls before going live"
Assistant: [Scans code, finds: "⚠️ No daily loss limit in execution/order_manager.py", suggests fix]

**Example 2:**
User: "Security check for API keys"
Assistant: [Detects hardcoded key in old file, recommends moving to .env]
