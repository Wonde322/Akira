"""Bounded recovery for provider throttling and missing-tool validation.

A rejected generation is never executed. A missing registered schema may be
advertised once and the model is asked to generate a new, validated response.
"""
from __future__ import annotations

import json
import math
import re
import time
from threading import RLock

from execution_context import raise_if_execution_cancelled, report_execution_status

_REQUEST_LOCK = RLock()


def retry_seconds(error):
    headers = getattr(getattr(error, 'response', None), 'headers', {}) or {}
    try:
        value = float(headers.get('retry-after', ''))
        if 0 <= value < 86400:
            return value
    except (TypeError, ValueError):
        pass
    match = re.search(r'try again in\s+([\d.]+)\s*(ms|s|m)', str(error), re.I)
    if match:
        value = float(match.group(1))
        return value * {'ms': .001, 's': 1, 'm': 60}[match.group(2).lower()]
    return None


def _wait(seconds):
    deadline = time.monotonic() + seconds
    reported = None
    while time.monotonic() < deadline:
        raise_if_execution_cancelled()
        remaining = max(1, math.ceil(deadline - time.monotonic()))
        if reported != remaining:
            report_execution_status(f"Лимит модели: жду {remaining} с")
            reported = remaining
        time.sleep(min(.05, max(0, deadline - time.monotonic())))
    raise_if_execution_cancelled()
    report_execution_status("Выполняю запрос…")


def _missing_tool(error):
    if getattr(error, 'status_code', None) != 400 or 'not in request.tools' not in str(error):
        return None
    body = getattr(error, 'body', {})
    if isinstance(body, dict):
        body = body.get('error', body)
    if isinstance(body, dict):
        try:
            failed = json.loads(body.get('failed_generation', ''))
            name = failed.get('name')
            if isinstance(name, str):
                return name
        except (TypeError, ValueError, AttributeError):
            pass
    match = re.search(r"call tool ['\"]([a-zA-Z0-9_]+)['\"]", str(error))
    return match.group(1) if match else None


def create_completion(client, *, all_tools, **kwargs):
    repaired = False
    rate_retries = 0
    waited = 0.0
    reported_queue = False
    while not _REQUEST_LOCK.acquire(timeout=.05):
        raise_if_execution_cancelled()
        if not reported_queue:
            report_execution_status("Жду очереди модели…")
            reported_queue = True
    try:
        while True:
            raise_if_execution_cancelled()
            report_execution_status("Жду ответа модели…")
            try:
                return client.chat.completions.create(**kwargs)
            except Exception as error:
                status = getattr(error, 'status_code', None)
                if status == 429 and rate_retries < 3:
                    delay = retry_seconds(error)
                    if delay is not None and waited + delay + .25 <= 60:
                        rate_retries += 1
                        waited += delay + .25
                        _wait(delay + .25)
                        continue
                name = _missing_tool(error)
                tools = kwargs.get('tools', [])
                known = next((schema for schema in all_tools if schema.get('function', {}).get('name') == name), None)
                if not repaired and known is not None and all(schema.get('function', {}).get('name') != name for schema in tools):
                    repaired = True
                    kwargs['tools'] = [*tools, known]
                    continue
                raise
    finally:
        _REQUEST_LOCK.release()
