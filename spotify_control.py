"""Direct Spotify playback controller.

Searches Spotify, ensures the desktop client is running, selects an available
playback device and starts the selected track. No agent loop is involved.
"""
from __future__ import annotations

import certifi
import json
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from config import SPOTIFY_TOKEN_FILE

CLIENT_ID = "71886dbe05744e1c9ea56d7ffd1eec1c"
TOKEN_FILE = SPOTIFY_TOKEN_FILE
API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def load_token():
    with open(TOKEN_FILE, encoding="utf-8") as file:
        return json.load(file)


def save_token(token):
    with open(TOKEN_FILE, "w", encoding="utf-8") as file:
        json.dump(token, file, indent=2)


def refresh_token(token):
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    }).encode()
    request = urllib.request.Request(
        TOKEN_URL, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(request, context=SSL_CONTEXT, timeout=15) as response:
        fresh = json.loads(response.read())
    fresh.setdefault("refresh_token", token["refresh_token"])
    save_token(fresh)
    return fresh


def api(method, endpoint, token, data=None, retry=True):
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(
        API + endpoint, data=body, method=method,
        headers={"Authorization": "Bearer " + token["access_token"], "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, context=SSL_CONTEXT, timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and retry and token.get("refresh_token"):
            return api(method, endpoint, refresh_token(token), data, False)
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Spotify API {exc.code}: {detail}")


def _activate_desktop():
    subprocess.run(["open", "-a", "Spotify"], capture_output=True, text=True, timeout=10)
    subprocess.run(["osascript", "-e", 'tell application "Spotify" to activate'], capture_output=True, text=True, timeout=10)


def _device(token):
    devices = (api("GET", "/me/player/devices", token) or {}).get("devices", [])
    if not devices:
        return None
    active = next((item for item in devices if item.get("is_active")), None)
    return active or next((item for item in devices if not item.get("is_restricted")), None)


def _activate_device(token):
    device = _device(token)
    if not device:
        return None
    if not device.get("is_active"):
        api("PUT", "/me/player", token, {"device_ids": [device["id"]], "play": False})
        time.sleep(0.3)
    return device["id"]


def play(query):
    query = str(query or "").strip()
    if not query:
        return "Не указано, что включить."
    token = load_token()
    params = urllib.parse.urlencode({"q": query, "type": "track", "limit": 1})
    result = api("GET", "/search?" + params, token)
    tracks = result.get("tracks", {}).get("items", [])
    if not tracks:
        return f"Не нашёл: {query}"
    track = tracks[0]

    _activate_desktop()
    time.sleep(0.8)
    device_id = _activate_device(token)
    if not device_id:
        return "Spotify открыт, но устройство воспроизведения ещё не появилось."

    endpoint = "/me/player/play?" + urllib.parse.urlencode({"device_id": device_id})
    api("PUT", endpoint, token, {"uris": [track["uri"]]})
    artists = ", ".join(item["name"] for item in track.get("artists", []))
    return f"Включил: {track['name']} — {artists}"


if __name__ == "__main__":
    import sys
    print(play(" ".join(sys.argv[1:])))
