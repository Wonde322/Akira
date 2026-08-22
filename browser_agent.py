from typing import Any


class BrowserAgent:
    """Observe -> action -> observe -> verify."""

    def __init__(self, browser: Any):
        self.browser = browser
        self.last_observation = None

    def _call(self, name, **kwargs):
        method = getattr(self.browser, name, None)

        if method is None:
            return {
                "success": False,
                "error": f"Unsupported browser action: {name}",
            }

        try:
            result = method(**kwargs)
        except Exception as exc:
            return {
                "success": False,
                "error": str(exc),
            }

        if isinstance(result, dict):
            return result

        return {"success": True, "result": result}

    def observe(self):
        for name in ("observe", "read_page", "get_page", "screenshot"):
            if hasattr(self.browser, name):
                result = self._call(name)
                if result.get("success", True):
                    self.last_observation = result
                return result

        return {
            "success": False,
            "error": "Browser backend has no observation method",
        }

    def execute_and_verify(self, action, **kwargs):
        before = self.observe()
        result = self._call(action, **kwargs)

        if not result.get("success", True):
            return {
                **result,
                "verified": False,
                "before": before,
            }

        after = self.observe()

        return {
            **result,
            "verified": after.get("success", True),
            "before": before,
            "after": after,
        }

    def navigate(self, url):
        for name in ("navigate", "open_url", "open"):
            if hasattr(self.browser, name):
                return self.execute_and_verify(name, url=url)

        return {
            "success": False,
            "verified": False,
            "error": "Browser backend has no navigation method",
        }

    def search(self, query):
        for name in ("search", "web_search", "google_search"):
            if hasattr(self.browser, name):
                return self.execute_and_verify(name, query=query)

        return {
            "success": False,
            "verified": False,
            "error": "Browser backend has no search method",
        }

    def interact(self, action, **kwargs):
        return self.execute_and_verify(action, **kwargs)
