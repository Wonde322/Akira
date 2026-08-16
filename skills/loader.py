"""Dynamic discovery of Akira skills.

A skill is a directory inside skills/ containing skill.py.

skill.py may expose:
    TOOLS = (
        ToolDefinition(...),
        ...
    )

The loader deliberately imports only local Python modules. It never executes
code from the network and never changes permissions by itself.
"""

from importlib import import_module
from pathlib import Path


def discover_skill_modules():
    root = Path(__file__).resolve().parent
    modules = []

    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue

        if directory.name.startswith("_"):
            continue

        skill_file = directory / "skill.py"
        if skill_file.exists():
            modules.append(f"skills.{directory.name}.skill")

    return modules


def load_skill_tools():
    tools = []
    errors = []

    for module_name in discover_skill_modules():
        try:
            module = import_module(module_name)
            candidates = getattr(module, "TOOLS", ())

            for tool in candidates:
                tools.append(tool)

        except Exception as exc:
            errors.append({
                "module": module_name,
                "error": repr(exc),
            })

    return tools, errors
