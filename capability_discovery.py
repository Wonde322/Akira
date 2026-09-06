"""Runtime adapter for Akira's canonical capability discovery."""

from capabilities.discovery import discover_capability


class CapabilityDiscovery:
    """Thin adapter; the canonical discovery algorithm remains in capabilities.discovery."""

    def choose(self, request):
        if isinstance(request, dict):
            query = (
                request.get("query")
                or request.get("goal")
                or request.get("text")
                or ""
            )
            limit = request.get("limit", 8)
        else:
            query = str(request or "")
            limit = 8

        result = discover_capability(query, limit=limit)
        data = result.get("data") or {}
        tools = data.get("tools") or []

        if not tools:
            return {
                "success": False,
                "capability": None,
                "alternatives": [],
                "output": result.get("output"),
            }

        return {
            "success": True,
            "capability": tools[0]["name"],
            "alternatives": [item["name"] for item in tools[1:5]],
            "tools": tools,
            "output": result.get("output"),
        }

    def discover(self, query, limit=8):
        return discover_capability(query, limit=limit)

    def list_capabilities(self):
        result = discover_capability("", limit=12)
        return (result.get("data") or {}).get("tools") or []
