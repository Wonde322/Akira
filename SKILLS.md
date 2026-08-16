# Akira Skills

Skills are optional capability modules loaded automatically at startup.

Structure:

    skills/
      my_skill/
        __init__.py
        skill.py

`skill.py` exports:

    TOOLS = (
        ToolDefinition(...),
    )

A ToolDefinition uses the same registry format as core tools:

- `name`
- `description`
- `parameters`
- `implementation_module`
- `implementation_name`
- `permission_policy`

The brain does not need to know that a tool came from a skill.

## Rules

1. Skills are local code, not downloaded dynamically.
2. Skills do not bypass the permission manager.
3. Skills should expose narrow capabilities rather than application-specific
   conversational logic.
4. Prefer universal capabilities over one-off commands.
5. A broken optional skill must not prevent Akira from starting.
