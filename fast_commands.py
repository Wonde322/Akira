"""Low-latency deterministic command path for common computer actions."""
from __future__ import annotations

import re
import subprocess
from typing import Any

from app_control import close_target, open_target
from computer_state import audio_devices, bluetooth_devices, frontmost_app, network, running_apps, volume

_GREETING = re.compile(r"^(?:привет|приветик|здарова|здорово|здравствуй|хай|hello|hi)[!. ]*$", re.I)
_WAKE_PREFIX = re.compile(r"^(?:эй\s+)?акира\s*[,!:\-]?\s*|^(?:hey\s+akira)\s*[,!:\-]?\s*", re.I)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _strip_wake_prefix(text: str) -> str:
    return _WAKE_PREFIX.sub("", text, count=1).strip()


def _target_after(text: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        match = re.match(pattern, text, re.I)
        if match:
            target = re.sub(r"^[,.:;\-\s]+|[,.:;\-\s]+$", "", match.group(1))
            target = re.sub(r"^(пожалуйста|ка|мне)\s+", "", target, flags=re.I)
            return target.strip() or None
    return None


def _set_volume(level: int) -> str:
    level = max(0, min(100, int(level)))
    result = subprocess.run(
        ["osascript", "-e", f"set volume output volume {level}"],
        text=True,
        capture_output=True,
        timeout=2,
    )
    return f"Громкость: {level}%." if result.returncode == 0 else "Не удалось изменить громкость."


def _adjust_volume(direction: str, step: int = 10) -> str:
    state = volume()
    old = int(state.get("level", 0))
    delta = step if direction == "up" else -step
    return _set_volume(old + delta)


def _format_apps() -> str:
    names = [item["name"] for item in running_apps()]
    return "Запущены: " + ", ".join(names) if names else "Нет запущенных приложений."


def _format_network() -> str:
    state = network()
    if state.get("wifi"):
        return f"Сеть Wi‑Fi: {state['wifi']}."
    if state.get("interface"):
        return f"Сейчас используется интерфейс {state['interface']}; имя Wi‑Fi не определилось."
    return "Не удалось определить текущее сетевое подключение."


def _device_count(data: Any) -> int:
    def walk(value: Any) -> int:
        if isinstance(value, dict):
            count = 0
            for key, child in value.items():
                if isinstance(child, list) and any(k in str(key).casefold() for k in ("device", "device_list", "devices")):
                    count += len(child)
                else:
                    count += walk(child)
            return count
        if isinstance(value, list):
            return sum(walk(item) for item in value)
        return 0
    return walk(data)


def handle(text: str) -> dict[str, Any] | None:
    text = _clean(text)
    if not text:
        return None
    if _GREETING.fullmatch(text):
        return {"handled": True, "response": "Привет.", "action": "greeting"}
    if re.fullmatch(r"(?:акира|эй\s+акира|akira|hey\s+akira)[!. ]*", text, re.I):
        return {"handled": True, "response": "Да?", "action": "wake"}

    text = _strip_wake_prefix(text)
    if not text:
        return {"handled": True, "response": "Да?", "action": "wake"}

    target = _target_after(text, (
        r"^(?:открой|открывай|запусти|запускай|запуск)\s+(.+)$",
    ))
    if target and not re.match(r"^(?:музыку|песню|трек|ютуб|youtube)\b", target, re.I):
        result = open_target(target)
        if result.get("success"):
            app = result.get("data", {}).get("application") or target
            return {"handled": True, "response": f"Открыл {app}.", "action": "open", "result": result}
        return {"handled": True, "response": f"Не нашёл приложение «{target}».", "action": "open", "result": result}

    target = _target_after(text, (
        r"^(?:закрой|закрывай|выйди\s+из|заверши)\s+(.+)$",
    ))
    if target:
        result = close_target(target)
        if result.get("success"):
            app = result.get("data", {}).get("application") or target
            return {"handled": True, "response": f"Закрыл {app}.", "action": "close", "result": result}
        if result.get("error") == "application_not_running":
            return {"handled": True, "response": f"{target} сейчас не запущен.", "action": "close", "result": result}
        return {"handled": True, "response": f"Не удалось закрыть {target}.", "action": "close", "result": result}

    if re.search(r"(?:какая|сколько|уровень).*громк|громкость.*(?:сейчас|какая|сколько)|(?:какая|сколько).*звук", text, re.I):
        state = volume()
        muted = " (звук выключен)" if state.get("muted") else ""
        return {"handled": True, "response": f"Громкость: {state.get('level', 0)}%{muted}.", "action": "volume_get", "result": state}

    if re.search(r"(?:сделай|снизь|уменьши|потише|тише)\b", text, re.I) or re.fullmatch(r"тише[!. ]*", text, re.I):
        return {"handled": True, "response": _adjust_volume("down"), "action": "volume_down"}
    if re.search(r"(?:сделай|увеличь|прибавь|погромче|громче)\b", text, re.I) or re.fullmatch(r"громче[!. ]*", text, re.I):
        return {"handled": True, "response": _adjust_volume("up"), "action": "volume_up"}

    match = re.search(r"(?:громкость|звук)\s*(?:на|до)\s*(\d{1,3})", text, re.I)
    if match:
        level = int(match.group(1))
        return {"handled": True, "response": _set_volume(level), "action": "volume_set", "result": {"level": max(0, min(100, level))}}

    if re.search(r"(?:какая|какой|что).*сеть|(?:к|какой).*wifi|(?:какой|какая).*вай.?фай|интернет.*(?:сеть|подключ)", text, re.I):
        return {"handled": True, "response": _format_network(), "action": "network"}

    if re.search(r"(?:что|какие).*подключ|(?:подключено|подключены).*устройства|устройства.*подключ", text, re.I):
        bt = bluetooth_devices()
        audio = audio_devices()
        return {
            "handled": True,
            "response": f"Bluetooth-устройств: {_device_count(bt)}; аудиоустройств: {_device_count(audio)}.",
            "action": "devices",
            "result": {"bluetooth": bt, "audio": audio},
        }

    if re.search(r"(?:что|какие).*запущ|(?:открытые|запущенные).*приложения|какие.*приложения", text, re.I):
        return {"handled": True, "response": _format_apps(), "action": "running_apps"}

    if re.search(r"(?:какое|какая|что).*активн|(?:какое|что).*сейчас.*открыт|текущее.*приложени", text, re.I):
        state = frontmost_app()
        name = state.get("name") or "неизвестно"
        return {"handled": True, "response": f"Сейчас активно: {name}.", "action": "frontmost", "result": state}

    return None
