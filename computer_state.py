"""Authoritative macOS computer state and native application discovery."""
from __future__ import annotations

import json
import os
import plistlib
import re
import subprocess
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

_CYRILLIC_TO_LATIN = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"y",
    "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
    "х":"h","ц":"c","ч":"ch","ш":"sh","щ":"sch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
})


def _norm(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or "")).casefold().translate(_CYRILLIC_TO_LATIN)
    return re.sub(r"[^a-z0-9]+", "", value)


def _run(args: list[str], timeout: float = 2.5) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, timeout=timeout)


def _osascript(script: str, timeout: float = 2.5) -> str:
    result = _run(["osascript", "-e", script], timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "osascript failed")
    return result.stdout.strip()


@dataclass(frozen=True)
class Application:
    name: str
    path: str
    bundle_id: str = ""

    @property
    def normalized(self) -> str:
        return _norm(self.name)


class ApplicationResolver:
    """Resolve human app references against applications actually registered on Mac."""

    def __init__(self) -> None:
        self._cache: list[Application] | None = None

    def _installed(self) -> list[Application]:
        if self._cache is not None:
            return self._cache
        paths: set[str] = set()
        try:
            result = _run(["mdfind", "kMDItemContentType == 'com.apple.application-bundle'"], timeout=5)
            if result.returncode == 0:
                paths.update(p for p in result.stdout.splitlines() if p.endswith(".app"))
        except Exception:
            pass
        if not paths:
            for root in ("/Applications", "/System/Applications", str(Path.home() / "Applications")):
                if not os.path.isdir(root):
                    continue
                try:
                    result = _run(["find", root, "-maxdepth", "2", "-name", "*.app", "-type", "d"], timeout=4)
                    if result.returncode == 0:
                        paths.update(result.stdout.splitlines())
                except Exception:
                    continue

        apps: list[Application] = []
        for raw_path in sorted(paths):
            try:
                with (Path(raw_path) / "Contents" / "Info.plist").open("rb") as fh:
                    info = plistlib.load(fh)
                name = str(info.get("CFBundleDisplayName") or info.get("CFBundleName") or Path(raw_path).stem)
                bundle_id = str(info.get("CFBundleIdentifier") or "")
            except Exception:
                name, bundle_id = Path(raw_path).stem, ""
            apps.append(Application(name=name, path=raw_path, bundle_id=bundle_id))

        self._cache = apps
        return apps

    def running(self) -> list[Application]:
        try:
            raw = _osascript('tell application "System Events" to get name of every process whose background only is false')
        except Exception:
            return []
        names = [n.strip() for n in re.split(r",\s*", raw) if n.strip()]
        by_name = {_norm(app.name): app for app in self._installed()}
        return [by_name.get(_norm(name), Application(name=name, path="")) for name in names]

    def frontmost(self) -> Application | None:
        try:
            name = _osascript('tell application "System Events" to get name of first process whose frontmost is true')
        except Exception:
            return None
        for app in self._installed():
            if _norm(app.name) == _norm(name):
                return app
        return Application(name=name, path="") if name else None

    def resolve(self, query: str, *, running_only: bool = False) -> Application | None:
        raw = str(query or "").strip()
        if not raw:
            return None
        path = Path(raw).expanduser()
        if path.suffix == ".app" and path.exists():
            return Application(name=path.stem, path=str(path))
        candidates = self.running() if running_only else self._installed()
        q = _norm(raw.removesuffix(".app"))
        if not q:
            return None
        exact = [app for app in candidates if q in {_norm(app.name), _norm(Path(app.path).stem), _norm(app.bundle_id)}]
        if exact:
            return exact[0]
        scored: list[tuple[float, Application]] = []
        for app in candidates:
            n = app.normalized
            if not n:
                continue
            ratio = SequenceMatcher(None, q, n).ratio()
            subseq = 1.0 if _is_subsequence(q, n) else 0.0
            prefix = 1.0 if n.startswith(q) or q.startswith(n) else 0.0
            scored.append((max(ratio, 0.88 * subseq, 0.95 * prefix), app))
        scored.sort(key=lambda item: item[0], reverse=True)
        if not scored:
            return None
        best, app = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        threshold = 0.70 if len(q) >= 4 else 0.86
        margin = 0.04 if len(q) < 4 else 0.02
        return app if best >= threshold and best - second >= margin else None


def _is_subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(ch in it for ch in short)


def volume() -> dict[str, Any]:
    raw = _osascript("get volume settings")
    data: dict[str, Any] = {}
    for part in raw.split(","):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        try:
            data[key.strip()] = int(value.strip())
        except ValueError:
            data[key.strip()] = value.strip()
    return {"level": int(data.get("output volume", 0)), "muted": str(data.get("output muted", "false")).casefold() == "true"}


def frontmost_app() -> dict[str, Any]:
    app = ApplicationResolver().frontmost()
    return {"name": app.name if app else None, "path": app.path if app else None}


def running_apps() -> list[dict[str, str]]:
    return [{"name": app.name, "path": app.path, "bundle_id": app.bundle_id} for app in ApplicationResolver().running()]


def network() -> dict[str, Any]:
    interface = ""
    try:
        route = _run(["route", "get", "default"], timeout=1.5)
        match = re.search(r"interface:\s*(\S+)", route.stdout)
        interface = match.group(1) if match else ""
    except Exception:
        pass
    wifi = ""
    if interface:
        try:
            result = _run(["networksetup", "-getairportnetwork", interface], timeout=1.5)
            if result.returncode == 0:
                match = re.search(r"(?:Current Wi-Fi Network|Current WiFi Network):\s*(.+)", result.stdout.strip(), re.I)
                wifi = match.group(1).strip() if match else ""
        except Exception:
            pass
    return {"interface": interface, "wifi": wifi}


def _system_profiler(kind: str) -> dict[str, Any]:
    try:
        result = _run(["system_profiler", kind, "-json"], timeout=5)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception:
        pass
    return {kind: []}


def audio_devices() -> dict[str, Any]:
    return _system_profiler("SPAudioDataType")


def bluetooth_devices() -> dict[str, Any]:
    return _system_profiler("SPBluetoothDataType")


def snapshot() -> dict[str, Any]:
    return {"frontmost_app": frontmost_app(), "running_apps": running_apps(), "volume": volume(), "network": network(), "audio_devices": audio_devices(), "bluetooth_devices": bluetooth_devices()}
