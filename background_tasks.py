"""Compatibility tools for Akira background tasks.

Task lifecycle now belongs to TaskManager.  This module remains only as the
public tool surface registered in existing prompts and schemas.
"""

from task_manager import get_task_manager


def background_task_start(goal):
    return get_task_manager().start_background(goal)


def background_task_status(task_id):
    return get_task_manager().status(task_id)


def background_task_result(task_id):
    return get_task_manager().result(task_id)


def background_task_cancel(task_id):
    return get_task_manager().cancel(task_id)
