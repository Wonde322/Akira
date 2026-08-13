import json
import os
from datetime import datetime

MEMORY_FILE = "memory.json"


def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {
            "goals": [],
            "tasks": [],
            "events": []
        }

    try:
        with open(MEMORY_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {
            "goals": [],
            "tasks": [],
            "events": []
        }


def save_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as file:
        json.dump(memory, file, ensure_ascii=False, indent=2)


memory = load_memory()


def add_goal(goal: str) -> str:
    memory["goals"].append({
        "text": goal,
        "created": datetime.now().isoformat(timespec="seconds")
    })

    save_memory(memory)
    return "Цель сохранена: " + goal


def get_goals(limit: int = 20) -> str:
    if not memory["goals"]:
        return "Сохранённых целей пока нет."

    result = "Текущие цели:\n"

    for number, goal in enumerate(memory["goals"][-limit:], 1):
        result += str(number) + ". " + goal["text"] + "\n"

    return result.strip()


def add_task(task: str, goal: str = None) -> str:
    memory["tasks"].append({
        "text": task,
        "goal": goal,
        "completed": False,
        "created": datetime.now().isoformat(timespec="seconds")
    })

    save_memory(memory)

    if goal:
        return "Задача добавлена: " + task + " → цель: " + goal

    return "Задача добавлена: " + task

def get_tasks() -> str:
    active_tasks = [
        task for task in memory["tasks"]
        if not task["completed"]
    ]

    if not active_tasks:
        return "Активных задач нет."

    result = "Текущие задачи:\n"

    for number, task in enumerate(active_tasks, 1):
        result += str(number) + ". " + task["text"] + "\n"

    return result.strip()


def complete_task(task_text: str) -> str:
    for task in memory["tasks"]:
        if not task["completed"] and task_text.lower() in task["text"].lower():
            task["completed"] = True
            task["completed_at"] = datetime.now().isoformat(timespec="seconds")

            save_memory(memory)
            return "Задача выполнена: " + task["text"]

    return "Я не нашёл такую активную задачу."


def add_event(event: str) -> str:
    memory["events"].append({
        "text": event,
        "time": datetime.now().isoformat(timespec="seconds")
    })

    save_memory(memory)
    return "Событие записано."


def get_recent_events(limit: int = 20) -> str:
    events = memory["events"][-limit:]

    if not events:
        return "История событий пока пуста."

    result = "Последние события:\n"

    for event in events:
        result += event["time"] + " — " + event["text"] + "\n"

    return result.strip()
