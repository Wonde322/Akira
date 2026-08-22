"""
ЭТАП 18/20 — Capability Discovery.
Адаптер поверх существующего ToolDefinition.
"""

from tool_registry import ToolDefinition


class CapabilityDiscovery:

    def __init__(self, registry=None):
        self.registry = registry if registry is not None else ToolDefinition()

    def _collect_tools(self):
        registry = self.registry

        # Сначала пробуем существующие публичные методы.
        for method_name in (
            "list_tools",
            "get_all_tools",
            "all_tools",
            "tools",
            "list",
        ):
            method = getattr(registry, method_name, None)

            if callable(method):
                try:
                    result = method()
                except TypeError:
                    continue

                if isinstance(result, dict):
                    return result

                if isinstance(result, (list, tuple)):
                    return {
                        getattr(item, "name", str(index)): item
                        for index, item in enumerate(result)
                    }

        # Затем существующие поля.
        for attr in ("tools", "_tools", "registry", "_registry"):
            value = getattr(registry, attr, None)

            if isinstance(value, dict):
                return value

            if isinstance(value, (list, tuple)):
                return {
                    getattr(item, "name", str(index)): item
                    for index, item in enumerate(value)
                }

        return {}

    def list_capabilities(self):
        result = []

        for name, tool in self._collect_tools().items():
            if isinstance(tool, dict):
                description = (
                    tool.get("description")
                    or tool.get("help")
                    or ""
                )
            else:
                description = (
                    getattr(tool, "description", None)
                    or getattr(tool, "help", None)
                    or ""
                )

            result.append({
                "name": str(name),
                "description": str(description),
            })

        return result

    def discover(self, query):
        words = {
            word.lower()
            for word in str(query).replace("_", " ").split()
            if len(word) > 1
        }

        matches = []

        for capability in self.list_capabilities():
            searchable = (
                capability["name"] + " " +
                capability["description"]
            ).lower()

            score = sum(
                1 for word in words
                if word in searchable
            )

            if score > 0:
                matches.append({
                    **capability,
                    "score": score,
                })

        return sorted(
            matches,
            key=lambda item: item["score"],
            reverse=True,
        )

    def choose(self, query):
        matches = self.discover(query)

        if not matches:
            return {
                "success": False,
                "capability": None,
                "alternatives": [],
            }

        return {
            "success": True,
            "capability": matches[0]["name"],
            "alternatives": [
                item["name"]
                for item in matches[1:5]
            ],
        }
