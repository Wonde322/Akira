import event_bus


class MixedRuntime:
    def __init__(self): self.calls=[]
    def handle(self,event,goals):
        self.calls.append((event,goals))
        if goals[0]=="bad": raise RuntimeError("boom")
        return {"success":True,"decision":{"action":"spawn_task"},"spawn":{"success":True,"task_id":"ok-task"},"launched":[{"task_id":"ok-task"}]}


def test_one_matching_trigger_failure_does_not_rollback_success(monkeypatch,tmp_path):
    monkeypatch.setattr(event_bus,"RUNTIME_DIR",tmp_path);monkeypatch.setattr(event_bus,"TRIGGER_FILE",tmp_path/"triggers.json");monkeypatch.setattr(event_bus,"EVENT_LOG",tmp_path/"events.jsonl")
    import proactive_runtime
    runtime=MixedRuntime();monkeypatch.setattr(proactive_runtime,"get_proactive_runtime",lambda:runtime)
    bus=event_bus.EventBus();bad=bus.create_trigger("demo","bad")["trigger_id"];good=bus.create_trigger("demo","good")["trigger_id"]
    result=bus.emit("demo",{},correlation_id="root")
    assert [goals[0] for _,goals in runtime.calls]==["bad","good"]
    assert result["launched"]==[{"task_id":"ok-task"}]
    triggers={t["id"]:t for t in bus.list_triggers()["triggers"]}
    assert triggers[bad]["last_error"]=="boom"
    assert "root" not in triggers[bad]["recent_correlations"]
    assert triggers[good]["fire_count"]==1
    assert "root" in triggers[good]["recent_correlations"]
