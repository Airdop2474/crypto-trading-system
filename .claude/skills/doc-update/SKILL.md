# doc-update

Automatic documentation synchronizer from code to docs.

## Description

Extracts docstrings and configuration changes, updates API documentation automatically. Keeps docs in sync with code using git diff to detect changes.

## When to Use

- After adding new modules or functions
- When configuration options change
- Regular documentation maintenance
- Before releases

**Trigger:** "update documentation", "sync API docs", "generate module docs"

## Instructions

1. Detect changed files via git diff
2. Extract docstrings using AST parser
3. Update docs/API.md with new signatures
4. Sync config file comments to documentation
5. Update module dependency diagram
6. Generate changelog of doc updates

Templates in ~/.claude/skills/doc-update/templates/

## Examples

**Example 1:**
User: "Update API documentation"
Assistant: [Scans changed files, updates docs/API.md with 3 new function signatures]

**Example 2:**
User: "Sync configuration docs"
Assistant: [Extracts comments from .env.example, updates configuration guide]
