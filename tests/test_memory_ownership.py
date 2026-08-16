from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ALLOWED = {
    "config.py",
    "memory.py",
}


def test_only_allowed_modules_reference_memory_json_directly():
    direct_references = []

    for path in ROOT.rglob("*.py"):
        if "tests" in path.parts or ".venv" in path.parts:
            continue

        if path.name in ALLOWED:
            continue

        if "memory.json" in path.read_text(encoding="utf-8"):
            direct_references.append(path.relative_to(ROOT))

    assert direct_references == []
