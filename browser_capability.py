from browser_agent import BrowserAgent


ACTION_MAP = {
    "open": "navigate",
    "navigate": "navigate",
    "read": "observe",
    "observe": "observe",
    "search": "search",
}


class _BrowserBackend:
    """Adapter from BrowserAgent to Akira's canonical CDP browser capability."""

    def _module(self):
        from capabilities import browser
        return browser

    def navigate(self, url):
        return self._module().browser_navigate(url=url)

    def observe(self):
        return self._module().browser_current()

    def search(self, query):
        return {
            "success": False,
            "error": "Browser search is not a core CDP operation; use browser_navigate with a search URL or a dedicated search capability.",
            "query": query,
        }


class BrowserCapability:
    def __init__(self, backend=None):
        self.backend = backend if backend is not None else _BrowserBackend()
        self.agent = BrowserAgent(self.backend)

    def execute(self, action, arguments=None):
        arguments = arguments or {}
        method_name = ACTION_MAP.get(action)

        if method_name is None:
            return {
                "success": False,
                "error": f"Unsupported browser action: {action}",
            }

        method = getattr(self.agent, method_name)
        try:
            return method(**arguments)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }
