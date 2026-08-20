from proactive_action_handlers import ProactiveActionHandlers


def test_help_request_spawns_selected_goal():
    calls=[]
    handlers=ProactiveActionHandlers(lambda goal, **kw: calls.append((goal,kw)) or {"success":True,"task_id":"t1"})
    result=handlers.handle({"id":"e1","correlation_id":"c1","type":"proactive.help_requested","payload":{"goal":"Fix the layout"}})
    assert result["success"] is True
    assert calls[0][0]=="Fix the layout"
    assert calls[0][1]["session_id"]=="proactive:c1"


def test_inspect_request_uses_context_goal():
    calls=[]
    handlers=ProactiveActionHandlers(lambda goal, **kw: calls.append(goal) or {"success":True})
    result=handlers.handle({"id":"e2","type":"proactive.inspect_requested","payload":{"goal":"Figma frame"}})
    assert result["success"] is True
    assert "Figma frame" in calls[0]


def test_dismiss_never_spawns_work():
    handlers=ProactiveActionHandlers(lambda *a,**k: (_ for _ in ()).throw(AssertionError("must not spawn")))
    result=handlers.handle({"type":"proactive.dismissed","payload":{}})
    assert result=={"handled":True,"success":True,"kind":"dismiss"}


def test_unknown_event_is_ignored():
    handlers=ProactiveActionHandlers(lambda *a,**k: {"success":True})
    assert handlers.handle({"type":"other"})=={"handled":False}
