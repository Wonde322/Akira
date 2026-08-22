from akira import Akira


class Runtime:
    def __init__(self):
        self.request = None

    def route_request(self, request):
        self.request = request
        return {"success": True}


def test_ask_uses_runtime_public_entry_point():
    runtime = Runtime()
    akira = Akira(runtime=runtime)

    result = akira.ask(text="привет", source="api")

    assert result == {"success": True}
    assert runtime.request["text"] == "привет"
    assert runtime.request["source"] == "api"
