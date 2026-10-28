"""Direct Spotify playback controller."""
from __future__ import annotations
import json, os, ssl, subprocess, sys, tempfile, threading, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
import certifi
from config import SPOTIFY_TOKEN_FILE
from capabilities.protocol import fail, ok
from execution_context import ExecutionCancelled, raise_if_execution_cancelled

CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "71886dbe05744e1c9ea56d7ffd1eec1c"); API = "https://api.spotify.com/v1"; TOKEN_URL = "https://accounts.spotify.com/api/token"
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_TOKEN_PATH = Path(SPOTIFY_TOKEN_FILE)
_auth_lock = threading.RLock()

# Natural-language intent words often survive ASR and should not become part
# of the Spotify search query.  This keeps "включи исполнителя X" equivalent
# to "включи X" without adding an application-specific command router.
_QUERY_PREFIXES = (
    "исполнитель ", "исполнителя ", "песню ", "трек ", "альбом ",
    "музыку ", "артиста ", "артист ",
)


def load_token():
    return json.loads(_TOKEN_PATH.read_text(encoding="utf-8"))

def save_token(token):
    _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".spotify-", dir=_TOKEN_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(token, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, _TOKEN_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)

def ensure_token():
    while not _auth_lock.acquire(timeout=0.1):
        raise_if_execution_cancelled()
    try:
        raise_if_execution_cancelled()
        if _TOKEN_PATH.is_file():
            try:
                token = load_token()
                if isinstance(token, dict) and token.get("access_token"):
                    return token
            except (OSError, ValueError):
                pass
        from spotify_auth import authorize
        return authorize()
    finally:
        _auth_lock.release()

def refresh_token(token):
    body = urllib.parse.urlencode({"client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": token["refresh_token"]}).encode()
    req = urllib.request.Request(TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=15) as response:
        fresh = json.loads(response.read().decode("utf-8"))
    fresh.setdefault("refresh_token", token["refresh_token"]); save_token(fresh); return fresh

def api(method, endpoint, token, data=None, retry=True):
    raise_if_execution_cancelled()
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(API + endpoint, data=body, method=method, headers={"Authorization": "Bearer " + token["access_token"], "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, context=SSL_CONTEXT, timeout=15) as response:
            raw = response.read().strip()
            raise_if_execution_cancelled()
            if not raw: return None
            content_type = response.headers.get("Content-Type", "").casefold()
            if "json" not in content_type: return raw.decode("utf-8", errors="replace")
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 401 and retry and token.get("refresh_token"):
            return api(method, endpoint, refresh_token(token), data, False)
        raise RuntimeError(f"Spotify API {exc.code}: {exc.read().decode(errors='replace')}")

def _norm(value): return " ".join(str(value or "").casefold().replace("ё", "е").split())

def _clean_query(query):
    value = " ".join(str(query or "").strip().split())
    normalized = value.casefold().replace("ё", "е")
    for prefix in _QUERY_PREFIXES:
        if normalized.startswith(prefix):
            return value[len(prefix):].strip()
    return value

def _activate_desktop():
    subprocess.Popen(["open", "-a", "Spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["osascript", "-e", 'tell application "Spotify" to activate'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)

def _search(query, token, kind=None):
    result = api("GET", "/search?" + urllib.parse.urlencode({"q": query, "type": kind or "track,artist,album", "limit": 5}), token) or {}
    if kind:
        items = result.get(kind + "s", {}).get("items", [])
        return (kind, items[0]) if items else (None, None)
    artists = result.get("artists", {}).get("items", []); tracks = result.get("tracks", {}).get("items", []); wanted = _norm(query)
    exact = next((x for x in artists if _norm(x.get("name")) == wanted), None)
    if exact: return "artist", exact
    if tracks: return "track", tracks[0]
    albums = result.get("albums", {}).get("items", [])
    if albums: return "album", albums[0]
    if artists: return "artist", artists[0]
    return None, None

def _wait_for_device(token, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        raise_if_execution_cancelled()
        devices = (api("GET", "/me/player/devices", token) or {}).get("devices", [])
        usable = [x for x in devices if not x.get("is_restricted")]
        if usable:
            active = next((x for x in usable if x.get("is_active")), usable[0])
            if not active.get("is_active"):
                api("PUT", "/me/player", token, {"device_ids": [active["id"]], "play": False})
            return active["id"]
        time.sleep(.4)
    return None

def _control(method, endpoint, success, activate=False):
    try:
        token = ensure_token()
        if activate:
            _activate_desktop()
        device_id = _wait_for_device(token)
        if not device_id: return fail("spotify_device_missing", "Устройство воспроизведения Spotify не найдено.")
        api(method, endpoint + "?" + urllib.parse.urlencode({"device_id": device_id}), token)
        return ok(success)
    except ExecutionCancelled: raise
    except Exception as exc: return fail("spotify_error", str(exc))

def pause(): return _control("PUT", "/me/player/pause", "Остановил Spotify.")
def next_track(): return _control("POST", "/me/player/next", "Следующий трек.")

def play(query):
    lowered = str(query or "").strip().casefold()
    kind = "album" if lowered.startswith("альбом ") else "artist" if lowered.startswith(("исполнитель ", "исполнителя ", "артист ", "артиста ")) else "track" if lowered.startswith(("трек ", "песню ")) else None
    query = _clean_query(query)
    if not query:
        return _control("PUT", "/me/player/play", "Продолжил Spotify.", activate=True)
    try:
        token = ensure_token(); kind, item = _search(query, token, kind)
        if item is None: return fail("spotify_not_found", f"Не нашёл: {query}")
        _activate_desktop(); device_id = _wait_for_device(token)
        if not device_id: return fail("spotify_device_missing", "Spotify открыт, но устройство воспроизведения не найдено.")
        playback = {"context_uri": item["uri"]} if kind in {"album", "artist"} else {"uris": [item["uri"]]}
        api("PUT", "/me/player/play?" + urllib.parse.urlencode({"device_id": device_id}), token, playback)
        artists = ", ".join(a["name"] for a in item.get("artists", []))
        return ok("Включил: " + item["name"] + (" — " + artists if artists else ""))
    except ExecutionCancelled: raise
    except Exception as exc: return fail("spotify_error", str(exc))

if __name__ == "__main__":
    print(play(" ".join(sys.argv[1:])))
