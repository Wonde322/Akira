from browser_agent import BrowserAgent


ACTION_MAP = {'open': 'navigate', 'navigate': 'navigate', 'read': 'observe', 'observe': 'observe', 'search': 'search'}


class BrowserCapability:
    def __init__(self, backend=None):
        self.backend = backend if backend is not None else BrowserAgent()

    def execute(self, action, arguments=None):
        arguments = arguments or {}

        method_name = ACTION_MAP.get(action)
        if method_name is None:
            return {
                "success": False,
                "error": f"Unsupported browser action: {action}",
            }

        method = getattr(self.backend, method_name)

        attempts = [
            lambda: method(**arguments),
            lambda: method(arguments),
        ]

        last_error = None
        for attempt in attempts:
            try:
                return attempt()
            except TypeError as exc:
                last_error = exc

        raise last_error
