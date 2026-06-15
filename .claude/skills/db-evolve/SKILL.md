# db-evolve

Database schema migration manager using Alembic.

## Description

Detects database schema changes, generates Alembic migration scripts, validates safety, and provides rollback plans. Prevents accidental data loss.

## When to Use

- Add new database tables
- Modify existing table structure
- Create indexes for performance
- Database schema version control

**Trigger:** "add new table", "modify orders table schema", "generate migration"

## Instructions

1. Detect schema changes via git diff in config/sql/
2. Generate Alembic migration script
3. Validate migration safety (no data deletion)
4. Create rollback script
5. Execute migration with user confirmation
6. Update schema documentation

Migration templates in ~/.claude/skills/db-evolve/templates/

## Examples

**Example 1:**
User: "Add strategy_performance table"
Assistant: [Generates migration, shows preview, asks confirmation, applies migration]

**Example 2:**
User: "Modify orders table to add stop_loss column"
Assistant: [Creates ALTER TABLE migration, includes rollback plan]
