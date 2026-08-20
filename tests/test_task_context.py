from task_context import TaskContextLinker, link_context_to_active_task


class Runtime:
    def __init__(self, tasks):
        self.tasks = tasks

    def list_tasks(self, limit=50):
        return {"success": True, "tasks": self.tasks}


def test_links_context_to_related_running_task():
    runtime = Runtime([
        {"id": "a", "goal": "Проверить макет Figma для клиента", "status": "running"},
        {"id": "b", "goal": "Скачать документы", "status": "running"},
    ])
    match = TaskContextLinker(runtime).match({"app": "Figma", "title": "Макет клиента"})
    assert match["task_id"] == "a"
    assert match["confidence"] > 0


def test_ignores_completed_and_unrelated_tasks():
    runtime = Runtime([
        {"id": "done", "goal": "Figma макет", "status": "completed"},
        {"id": "other", "goal": "Скачать документы", "status": "running"},
    ])
    assert link_context_to_active_task({"app": "Figma"}, runtime=runtime) is None


def test_returns_best_match():
    runtime = Runtime([
        {"id": "weak", "goal": "Проверить проект", "status": "running"},
        {"id": "best", "goal": "Проверить Figma проект poster", "status": "running"},
    ])
    match = TaskContextLinker(runtime).match({"app": "Figma", "title": "Poster проект"})
    assert match["task_id"] == "best"
