"""Spotify playback controller with direct play, pause and next-track actions."""
from __future__ import annotations
import json, ssl, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
import certifi
from config import SPOTIFY_TOKEN_FILE

CLIENT_ID="71886dbe05744e1c9ea56d7ffd1eec1c"; API="https://api.spotify.com/v1"; TOKEN_URL="https://accounts.spotify.com/api/token"
SSL_CONTEXT=ssl.create_default_context(cafile=certifi.where())
_TOKEN_PATH=Path(SPOTIFY_TOKEN_FILE)

def load_token():
    with _TOKEN_PATH.open(encoding="utf-8") as f:return json.load(f)

def save_token(token):_TOKEN_PATH.write_text(json.dumps(token,ensure_ascii=False,indent=2),encoding="utf-8")

def ensure_token():
    if _TOKEN_PATH.is_file():return load_token()
    auth=Path(__file__).with_name("spotify_auth.py")
    if not auth.is_file():raise RuntimeError("Не найден модуль авторизации Spotify.")
    process=subprocess.Popen([sys.executable,str(auth)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+120
    while time.monotonic()<deadline:
        if _TOKEN_PATH.is_file():return load_token()
        if process.poll() is not None:raise RuntimeError("Авторизация Spotify была отменена или завершилась ошибкой.")
        time.sleep(.25)
    process.terminate(); raise RuntimeError("Spotify ждёт авторизацию в открывшемся окне браузера.")

def refresh_token(token):
    body=urllib.parse.urlencode({"client_id":CLIENT_ID,"grant_type":"refresh_token","refresh_token":token["refresh_token"]}).encode()
    req=urllib.request.Request(TOKEN_URL,data=body,headers={"Content-Type":"application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req,context=SSL_CONTEXT,timeout=15) as r:fresh=json.loads(r.read())
    fresh.setdefault("refresh_token",token["refresh_token"]); save_token(fresh); return fresh

def api(method,endpoint,token,data=None,retry=True):
    body=json.dumps(data).encode() if data is not None else None
    req=urllib.request.Request(API+endpoint,data=body,method=method,headers={"Authorization":"Bearer "+token["access_token"],"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,context=SSL_CONTEXT,timeout=15) as r:
            raw=r.read(); return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if exc.code==401 and retry and token.get("refresh_token"):return api(method,endpoint,refresh_token(token),data,False)
        raise RuntimeError(f"Spotify API {exc.code}: {exc.read().decode(errors='replace')}")

def _norm(value):return " ".join(str(value or "").casefold().replace("ё","е").split())

def _activate_desktop():
    subprocess.run(["open","-a","Spotify"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
    subprocess.run(["osascript","-e",'tell application "Spotify" to activate'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)

def _search(query,token):
    result=api("GET","/search?"+urllib.parse.urlencode({"q":query,"type":"track,artist","limit":5}),token) or {}
    artists=result.get("artists",{}).get("items",[]); tracks=result.get("tracks",{}).get("items",[]); wanted=_norm(query)
    exact=next((x for x in artists if _norm(x.get("name"))==wanted),None)
    if exact:return "artist",exact
    if tracks:return "track",tracks[0]
    if artists:return "artist",artists[0]
    return None,None

def _artist_track(artist,token):
    tracks=(api("GET",f"/artists/{artist['id']}/top-tracks?market=US",token) or {}).get("tracks",[])
    return tracks[0] if tracks else None

def _wait_for_device(token,seconds=10):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        devices=(api("GET","/me/player/devices",token) or {}).get("devices",[])
        usable=[x for x in devices if not x.get("is_restricted")]
        if usable:
            active=next((x for x in usable if x.get("is_active")),usable[0])
            if not active.get("is_active"):
                api("PUT","/me/player",token,{"device_ids":[active["id"]],"play":False}); time.sleep(.5)
            return active["id"]
        time.sleep(.5)
    return None

def _control(endpoint,success):
    try:
        token=ensure_token(); _activate_desktop(); device_id=_wait_for_device(token)
        if not device_id:return "Spotify открыт, но не появился в списке устройств воспроизведения."
        api("POST",endpoint+"?"+urllib.parse.urlencode({"device_id":device_id}),token)
        return success
    except Exception as exc:return f"Не удалось выполнить действие в Spotify: {exc}"

def pause():return _control("/me/player/pause","Остановил Spotify.")
def next_track():return _control("/me/player/next","Следующий трек.")

def play(query):
    query=str(query or "").strip()
    if not query:return "Не указано, что включить."
    try:
        token=ensure_token(); kind,item=_search(query,token)
        if item is None:return f"Не нашёл: {query}"
        track=_artist_track(item,token) if kind=="artist" else item
        if track is None:return f"Не нашёл треки исполнителя: {item.get('name',query)}"
        _activate_desktop(); device_id=_wait_for_device(token)
        if not device_id:return "Spotify открыт, но не появился в списке устройств воспроизведения."
        api("PUT","/me/player/play?"+urllib.parse.urlencode({"device_id":device_id}),token,{"uris":[track["uri"]]})
        return "Включил: "+track["name"]+" — "+", ".join(a["name"] for a in track.get("artists",[]))
    except Exception as exc:return f"Не удалось включить в Spotify: {exc}"

if __name__=="__main__":
    import sys; print(play(" ".join(sys.argv[1:])))
