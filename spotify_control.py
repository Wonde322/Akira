import ssl
import certifi
import json
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
    with open(TOKEN_FILE) as f:
        return json.load(f)


def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f, indent=2)


def refresh_token(token):
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": token["refresh_token"],
    }).encode()

    request = urllib.request.Request(
        TOKEN_URL,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    with urllib.request.urlopen(request, context=SSL_CONTEXT) as response:
        new_token = json.loads(response.read())

    if "refresh_token" not in new_token:
        new_token["refresh_token"] = token["refresh_token"]

    save_token(new_token)
    return new_token


def api(method, endpoint, token, data=None, retry=True):
    body = None

    if data is not None:
        body = json.dumps(data).encode()

    request = urllib.request.Request(
        API + endpoint,
        data=body,
        method=method,
        headers={
            "Authorization": "Bearer " + token["access_token"],
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, context=SSL_CONTEXT) as response:
            raw = response.read()
            return json.loads(raw) if raw else None

    except urllib.error.HTTPError as e:
        if e.code == 401 and retry and "refresh_token" in token:
            token = refresh_token(token)
            return api(method, endpoint, token, data, False)

        error = e.read().decode(errors="replace")
        raise RuntimeError(f"Spotify API {e.code}: {error}")


def play(query):
    token = load_token()

    # Find the most relevant track.
    params = urllib.parse.urlencode({
        "q": query,
        "type": "track",
        "limit": 1,
    })

    result = api(
        "GET",
        "/search?" + params,
        token,
    )

    tracks = result.get("tracks", {}).get("items", [])

    if not tracks:
        return f"Не нашёл трек: {query}"

    track = tracks[0]

    # Make sure Spotify desktop is open.
    subprocess.run(
        ["osascript", "-e", 'tell application "Spotify" to activate'],
        check=False,
    )

    time.sleep(1)

    # Start the exact track on the current Spotify device.
    api(
        "PUT",
        "/me/player/play",
        token,
        {
            "uris": [track["uri"]],
        },
    )

    artists = ", ".join(
        artist["name"] for artist in track["artists"]
    )

    return f"Включил: {track['name']} — {artists}"


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]).strip()

    if not query:
        print("Укажи название трека.")
        raise SystemExit(1)

    print(play(query))
