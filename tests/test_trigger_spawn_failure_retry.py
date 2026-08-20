import event_bus


class RetryRuntime:
    def __init__(self): self.calls=0
    def handle(self,event,goals):
        self.calls+=1
        if self.calls==1:
            return {"success":False,"decision":{"action":"spawn_task"},"spawn":{"success":False,"error":"temporary"},"launched":[]}
        return {"success":True,"decision":{"action":"spawn_task"},"spawn":{"success":True,"task_id":"retry-ok"},"launched":[{"task_id":"retry-ok"}]}


def test_failed_spawn_releases_correlation_for_same_chain_retry(monkeypatch,tmp_path):
    monkeypatch.setattr(event_bus,"RUNTIME_DIR",tmp_path)
    monkeypatch.setattr(event_bus,"TRIGGER_FILE",tmp_path/"triggers.json")
    monkeypatch.setattr(event_bus,"EVENT_LOG",tmp_path/"events.jsonl")
    import proactive_runtime
    runtime=RetryRuntime()
    monkeypatch.setattr(proactive_runtime,"get_proactive_runtime",lambda:runtime)
    bus=event_bus.EventBus();tid=bus.create_trigger("demo","goal")["trigger_id"]
    first=bus.emit("demo",{},correlation_id="root")
    assert first["launched"]==[]
    trigger={item["id"]:item for item in bus.list_triggers()["triggers"]}[tid]
    assert trigger["last_error"]=="temporary"
    assert "root" not in trigger["recent_correlations"]
    second=bus.emit("demo",{},correlation_id="root")
    assert second["launched"]==[{"task_id":"retry-ok"}]
    assert runtime.calls==2
