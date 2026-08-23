"""Direct desktop command router."""
from __future__ import annotations
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

APPS={"spotify":"Spotify","спотифай":"Spotify","спотифая":"Spotify","спотифае":"Spotify","спотифаи":"Spotify","спотифаю":"Spotify","discord":"Discord","дискорд":"Discord","дискорда":"Discord","дискорду":"Discord","дискордом":"Discord","safari":"Safari","сафари":"Safari","chrome":"Google Chrome","хром":"Google Chrome","гугл хром":"Google Chrome","terminal":"Terminal","терминал":"Terminal","finder":"Finder","файндер":"Finder"}
STOP_WORDS={"стоп","остановись","отмена","отмени","хватит","stop","cancel"}; MORE_WORDS={"еще","ещё","еще раз","ещё раз","повтори","продолжай","дальше"}; _CONTEXT={}
_ACTION_WORDS={"открой":"open","запусти":"open","закрой":"close","выключи":"close"}; _ACTION_RE=re.compile(r"(?:^|(?<=\s))(открой|запусти|закрой|выключи)(?=\s)",re.I); _SPLIT_TARGETS=re.compile(r"\s*(?:,|\bи\b|\bа также\b)\s*",re.I)

def normalize(message):
    text=str(message or "").casefold().replace("ё","е").strip(); text=re.sub(r"^акира[,:;\-]?\s*","",text); text=re.sub(r"\s+"," ",text)
    text=re.sub(r"спотифа(?:й|я|е|и|ю)\b","спотифай",text); text=re.sub(r"дискорд(?:а|у|ом|е)?\b","дискорд",text); return text.strip(" .,!?:;")

def _name(value):
    value=re.sub(r"^(?:к|ко|в|на)\s+","",value.strip(" .,!?:;")); return APPS.get(value,value)

def _parse_compound_apps(text):
    matches=list(_ACTION_RE.finditer(text))
    if not matches or matches[0].start()!=0:return None
    actions=[]
    for index,match in enumerate(matches):
        end=matches[index+1].start() if index+1<len(matches) else len(text); chunk=text[match.end():end].strip(" ,.!?:;")
        chunk=re.sub(r"\s+(?:и|а затем|потом)\s*$","",chunk,flags=re.I); targets=[_name(part) for part in _SPLIT_TARGETS.split(chunk) if part.strip()]
        if not targets:return None
        actions.append((_ACTION_WORDS[match.group(1).casefold()],targets))
    return actions

def parse(message):
    text=normalize(message)
    if text in STOP_WORDS:return "stop",None
    if text in MORE_WORDS:return "more",None
    if text in {"закрой","выключи"}:return "context_stop",None
    if text in {"следующий","следующий трек","скип","пропусти"}:return "spotify_next",None
    music=re.match(r"^(?:включи|поставь|сыграй)\s+(.+?)\s+(?:на|в)\s+спотифай$",text)
    if music and music.group(1).strip():return "spotify_play",music.group(1).strip()
    actions=_parse_compound_apps(text)
    if actions:return "apps",actions
    if re.search(r"^(?:(?:какая|какой|сколько|текущая)\s+)?(?:сейчас\s+)?(?:громкость|уровень звука|звук)(?:\s+сейчас)?\??$",text):return "volume_get",None
    volume=re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})(?:\s*%|\s*процент\w*)?$",text)
    if volume:return "volume",max(0,min(100,int(volume.group(1))))
    if re.search(r"\b(?:громче|прибавь|увеличь)\b",text):return "volume_delta",10
    if re.search(r"\b(?:тише|убавь|уменьши)\b",text):return "volume_delta",-10
    if re.search(r"(?:выключи|убери)\s+(?:звук|громкость)",text):return "volume",0
    return None

def _current_volume():
    from capabilities.apps import _run
    current=_run("output volume of (get volume settings)")
    if getattr(current,"returncode",1)!=0:raise RuntimeError("Не удалось прочитать громкость")
    return max(0,min(100,int(current.stdout.strip())))

def _volume(value=None,delta=None):
    from capabilities.apps import _run
    if delta is not None:value=_current_volume()+int(delta)
    value=max(0,min(100,int(value))); result=_run(f"set volume output volume {value}")
    if getattr(result,"returncode",1)!=0:raise RuntimeError("Не удалось изменить громкость")
    return value

def _run_apps(actions):
    from capabilities.apps import open_target,close_target
    messages=[]; last_done=[]
    for operation,targets in actions:
        worker=open_target if operation=="open" else close_target; results={}
        with ThreadPoolExecutor(max_workers=len(targets)) as pool:
            futures={pool.submit(worker,target):target for target in targets}
            for future in as_completed(futures):
                target=futures[future]
                try:results[target]=future.result()
                except Exception as exc:results[target]={"success":False,"error":str(exc)}
        done=[]; failed=[]
        for target in targets:
            result=results[target]
            if result.get("success"):done.append(target); last_done.append(target)
            else:failed.append(f"{target}: {result.get('error') or 'не удалось'}")
        if done:messages.append(f"{'Открыл' if operation=='open' else 'Закрыл'}: {', '.join(done)}.")
        if failed:messages.append("Не удалось: "+"; ".join(failed))
    return " ".join(messages) or "Не удалось выполнить действие.",last_done

def _set_context(session_id,kind,value=None,target=None):_CONTEXT[session_id]={"kind":kind,"value":value,"target":target}

def ask(message,session_id="desktop"):
    command=parse(message)
    if command is None:
        import agent_loop; return agent_loop.ask(message,session_id=session_id)
    kind,value=command; context=_CONTEXT.get(session_id,{})
    if kind=="stop":_CONTEXT.pop(session_id,None); return "Остановил."
    if kind=="more":
        if context.get("kind")=="spotify_play":
            from spotify_control import next_track; return next_track()
        if context.get("kind")=="volume_delta":kind,value="volume_delta",context.get("value",10)
        else:return "Не понимаю, что продолжить."
    if kind=="context_stop":
        if context.get("kind")=="spotify_play":
            from spotify_control import pause; return pause()
        if context.get("kind")=="apps" and context.get("target"):kind,value="apps",[("close",[context["target"]])]
        else:return "Не понимаю, что выключить."
    if kind=="spotify_play":
        from spotify_control import play
        result=play(value); _set_context(session_id,"spotify_play",value,"Spotify"); return result
    if kind=="spotify_next":
        from spotify_control import next_track
        result=next_track(); _set_context(session_id,"spotify_play",context.get("value"),"Spotify"); return result
    if kind=="apps":
        result,done=_run_apps(value)
        if done:_set_context(session_id,"apps",value,done[-1])
        return result
    if kind=="volume_get":return f"Громкость: {_current_volume()}%"
    if kind=="volume":
        result=f"Громкость: {_volume(value=value)}%"; _set_context(session_id,"volume",value); return result
    result=f"Громкость: {_volume(delta=value)}%"; _set_context(session_id,"volume_delta",value); return result

def get_session(session_id="desktop"):
    import agent_loop; return agent_loop.get_session(session_id)
