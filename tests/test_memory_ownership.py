from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_only_memory_module_references_memory_json_directly():
    direct_references = []

    for path in ROOT.rglob("*.py"):
        if "tests" in path.parts or ".venv" in path.parts:
            continue

        if path.name == "memory.py":
            continue

        if "memory.json" in path.read_text(encoding="utf-8"):
            direct_references.append(path.relative_to(ROOT))

    assert direct_references == []
