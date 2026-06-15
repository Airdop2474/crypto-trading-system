# dev-log

Development progress logger and tracker.

## Description

Records daily development activities, tracks phase completion, and maintains project history. Stored in .claude/dev-log/YYYY-MM-DD.md files.

## When to Use

- End of day to log progress
- After completing tasks
- To query development history
- Track blockers and decisions

**Trigger:** "log today's work", "show recent progress", "what did we do last week"

## Instructions

**Log entry:**
1. Create/append to .claude/dev-log/YYYY-MM-DD.md
2. Use template: Task, Files Changed, Status, Notes
3. Update phase progress if applicable

**Query:**
1. Read recent log files (last 7 days)
2. Summarize completed tasks
3. Show current blockers

## Examples

User: "log: implemented RSI indicator"
Assistant: [Adds entry to today's log with timestamp, files, status]

User: "what did we do this week"
Assistant: [Reads last 7 days, summarizes: 5 tasks completed, 2 in progress]
