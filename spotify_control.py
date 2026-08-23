"""Spotify playback controller.

Direct path: authenticate -> resolve a track or artist -> wake Spotify -> wait for
an actual Spotify Connect device -> play the selected URI.
"""
from __future__ import annotations

import json
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

import certifi
from config import SPOTIFY_TOKEN_FILE

CLIENT_ID = "71886dbe05744e1c9ea56d7ffd1eec1c"
API = "https://api.spotify.com/v1"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def load_token():
    with open(SPOTIFY_TOKEN_FILE, encoding="utf-8") as file:
        return json.load(file)


def save_token(token):
    with open(SPOTIFY_TOKEN_FILE, "w", encoding="utf-8") as file:
        json.dump(token, file, ensure_ascii=False, indent=2)


def refresh_token(token):
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    }).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(request, context=SSL_CONTEXT, timeout=15) as response:
        fresh = json.loads(response.read())
    fresh.setdefault("refresh_token", token["refresh_token"])
    save_token(fresh)
    return fresh


def api(method, endpoint, token, data=None, retry=True):
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(API + endpoint, data=body, method=method, headers={
        "Authorization": "Bearer " + token["access_token"],
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(request, context=SSL_CONTEXT, timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and retry and token.get("refresh_token"):
            return api(method, endpoint, refresh_token(token), data, False)
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Spotify API {exc.code}: {detail}")


def _norm(value):
    return " ".join(str(value or "").casefold().replace("ё", "е").split())


def _activate_desktop():
    subprocess.run(["open", "-a", "Spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    subprocess.run(["osascript", "-e", 'tell application "Spotify" to activate'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)


def _search(query, token):
    params = urllib.parse.urlencode({"q": query, "type": "track,artist", "limit": 5})
    result = api("GET", "/search?" + params, token) or {}
    artists = result.get("artists", {}).get("items", [])
    tracks = result.get("tracks", {}).get("items", [])
    wanted = _norm(query)
    exact_artist = next((item for item in artists if _norm(item.get("name")) == wanted), None)
    if exact_artist:
        return "artist", exact_artist
    if tracks:
        return "track", tracks[0]
    if artists:
        return "artist", artists[0]
    return None, None


def _artist_track(artist, token):
    artist_id = artist["id"]
    data = api("GET", f"/artists/{artist_id}/top-tracks?market=US", token) or {}
    tracks = data.get("tracks", [])
    return tracks[0] if tracks else None


def _wait_for_device(token, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        devices = (api("GET", "/me/player/devices", token) or {}).get("devices", [])
        usable = [item for item in devices if not item.get("is_restricted")]
        if usable:
            active = next((item for item in usable if item.get("is_active")), usable[0])
            if not active.get("is_active"):
                api("PUT", "/me/player", token, {"device_ids": [active["id"]], "play": False})
                time.sleep(0.4)
            return active["id"]
        time.sleep(0.5)
    return None


def play(query):
    query = str(query or "").strip()
    if not query:
        return "Не указано, что включить."
    try:
        token = load_token()
        kind, item = _search(query, token)
        if item is None:
            return f"Не нашёл: {query}"
        if kind == "artist":
            track = _artist_track(item, token)
            if track is None:
                return f"Не нашёл треки исполнителя: {item.get('name', query)}"
        else:
            track = item

        _activate_desktop()
        device_id = _wait_for_device(token)
        if not device_id:
            return "Spotify открыт, но не появился в списке устройств воспроизведения."
        endpoint = "/me/player/play?" + urllib.parse.urlencode({"device_id": device_id})
        api("PUT", endpoint, token, {"uris": [track["uri"]]})
        artists = ", ".join(a["name"] for a in track.get("artists", []))
        return f"Включил: {track['name']} — {artists}"
    except FileNotFoundError:
        return "Не найден файл авторизации Spotify."
    except Exception as exc:
        return f"Не удалось включить в Spotify: {exc}"


if __name__ == "__main__":
    import sys
    print(play(" ".join(sys.argv[1:])))
