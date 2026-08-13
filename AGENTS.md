# Akira — Development Rules

## Identity

Akira is a male character.
Always refer to Akira with masculine pronouns in Russian:
- он
- его
- ему
- сам

Never use feminine pronouns for Akira.

## Core Architecture Principle

Akira is a general-purpose computer agent, not a collection of hardcoded commands for individual applications.

The agent should understand a user's goal and compose general capabilities to accomplish it.

Do NOT create a new tool merely because a new application or task appears.

Prefer general capabilities such as:
- observe
- open
- close
- find
- read
- write
- create
- move
- copy
- rename
- delete
- select
- click
- type
- key
- scroll
- drag
- wait
- shell execution

Specialized integrations are allowed when a service provides an API that is substantially more reliable or efficient than GUI interaction.

Spotify is an example of a specialized API integration.

## Tool Design

Before creating a new tool:

1. Check whether an existing tool can accomplish the task.
2. Check whether the task can be composed from general computer/shell capabilities.
3. Only create a specialized tool if there is a clear architectural reason.

Never create tools such as:
- open_photoshop
- open_calculator
- export_photoshop
- generate_castles
- run_specific_project
- click_spotify_button

unless there is a strong, documented reason why the general agent cannot reasonably perform the operation.

## Separation of Responsibilities

Keep these responsibilities separate:

- Brain: reasoning, planning, tool selection and conversation.
- Computer: interaction with the graphical computer environment.
- Shell: terminal and command execution.
- Filesystem: general file operations.
- Integrations: service-specific APIs.
- Memory: persistent user/project memory.
- Analysis: activity, goals and proactive analysis.
- Voice: speech input/output.
- Permissions: safety and authorization.

Do not move unrelated responsibilities into brain.py.

## Memory

memory.json must have a single programmatic owner: the memory layer.

Other modules must not directly open or parse memory.json.

Use the memory module/API instead.

Keep these concepts logically distinct:
- memory
- events
- tasks
- goals
- activity

Do not silently change the memory schema without checking all consumers.

## Permissions

Every executable tool must have a clear permission policy.

Do not add permissions for tools that do not exist.

Do not bypass the permission system.

Potentially destructive operations must require confirmation unless an explicit safe policy exists.

## Development Workflow

Before changing code:

1. Inspect the existing implementation.
2. Identify the root cause or architectural reason.
3. Avoid duplicate implementations.
4. Make the smallest coherent change.
5. Run relevant tests/checks.
6. Inspect the resulting diff.
7. Only then consider the task complete.

Do not repeatedly patch the same symptom without identifying the underlying cause.

## Backups and Temporary Files

Do not create ad-hoc backup copies such as:
- *.backup
- *.backup_*
- *.before_*
- *.final_backup

Use Git for version history.

Temporary files must not become part of the production architecture.

## Testing

Every bug that can reasonably be reproduced by an automated test should receive a regression test.

A change is not considered complete merely because the code parses.

At minimum, check:
- syntax
- imports
- relevant unit/integration tests
- tool registration
- permissions
- architectural invariants when applicable

## Git

Keep commits small and coherent.

Never commit:
- API keys
- access tokens
- OAuth tokens
- .env files
- private credentials
- personal memory data
- virtual environments
- caches
- logs

Review `git diff` before committing.

Do not rewrite or delete working functionality without a clear reason.

## Refactoring Rule

Do not perform large speculative rewrites.

Prefer incremental refactoring:

inspect
→ change
→ test
→ verify
→ commit

Preserve working behavior unless the purpose of the change is explicitly to alter it.

## Communication

When working autonomously, explain:
- what you found
- what you changed
- why you changed it
- what tests/checks were run
- whether anything remains uncertain

Never claim that a change was tested if it was not actually tested.

