"""Direct desktop command router with per-session action context."""
from __future__ import annotations
import re

APPS={"spotify":"Spotify","спотифай":"Spotify","спотифая":"Spotify","спотифае":"Spotify","спотифаи":"Spotify","спотифаю":"Spotify","discord":"Discord","дискорд":"Discord","дискорда":"Discord","дискорду":"Discord","safari":"Safari","сафари":"Safari","chrome":"Google Chrome","хром":"Google Chrome","гугл хром":"Google Chrome","terminal":"Terminal","терминал":"Terminal","finder":"Finder","файндер":"Finder"}
STOP_WORDS={"стоп","остановись","отмена","отмени","хватит","stop","cancel"}
MORE_WORDS={"еще","ещё","еще раз","ещё раз","повтори","продолжай","дальше"}
_LAST_TARGETS={}
_LAST_ACTION={}

def normalize(message):
    text=str(message or "").casefold().replace("ё","е").strip()
    text=re.sub(r"^акира[,:;\-]?\s*","",text); text=re.sub(r"\s+"," ",text)
    text=re.sub(r"спотифа(?:й|я|е|и|ю)\b","спотифай",text); text=re.sub(r"дискорд(?:а|у|ом|е)?\b","дискорд",text)
    return text.strip(" .,!?:;")

def _name(value):
    value=re.sub(r"^(?:к|ко|в|на)\s+","",value.strip(" .,!?:;"))
    return APPS.get(value,value)

def _targets(value):
    return [name for part in re.split(r"\s*(?:,|\bи\b|\bа также\b|\bпотом\b)\s*",value.strip()) if (name:=_name(part))]

def parse(message):
    text=normalize(message)
    if text in STOP_WORDS:return ("stop",None)
    if text in MORE_WORDS:return ("repeat",None)
    if text in {"закрой","выключи"}:return ("close_context",None)
    m=re.match(r"^(?:включи|поставь|сыграй)\s+(.+?)\s+(?:на|в)\s+спотифай$",text)
    if m and m.group(1).strip():return ("spotify",m.group(1).strip())
    m=re.match(r"^(открой|запусти|закрой|выключи)\s+(?:к|ко)?\s*(.+)$",text)
    if m:
        verb,raw=m.groups(); return ("close" if verb in {"закрой","выключи"} else "open",_targets(raw))
    m=re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})(?:\s*%|\s*процент\w*)?$",text)
    if m:return ("volume",max(0,min(100,int(m.group(1)))))
    if re.search(r"\b(?:громче|прибавь|увеличь)\b",text):return ("volume_delta",10)
    if re.search(r"\b(?:тише|убавь|уменьши)\b",text):return ("volume_delta",-10)
    if re.search(r"(?:выключи|убери)\s+(?:звук|громкость)",text):return ("volume",0)
    return None

def _volume(value=None,delta=None):
    from capabilities.apps import _run
    if delta is not None:
        current=_run("output volume of (get volume settings)")
        if current.returncode!=0:raise RuntimeError(current.stderr.strip() or "Не удалось прочитать громкость")
        value=int(current.stdout.strip())+int(delta)
    value=max(0,min(100,int(value))); result=_run(f"set volume output volume {value}")
    if result.returncode!=0:raise RuntimeError(result.stderr.strip() or "Не удалось изменить громкость")
    return value

def ask(message,session_id="desktop"):
    command=parse(message)
    if command is None:
        import agent_loop; return agent_loop.ask(message,session_id=session_id)
    kind,value=command
    if kind=="stop":
        _LAST_ACTION.pop(session_id,None); return "Остановил."
    if kind=="repeat":
        previous=_LAST_ACTION.get(session_id)
        if previous is None:return "Не понимаю, что повторить."
        kind,value=previous
    if kind=="close_context":
        value=_LAST_TARGETS.get(session_id,[])
        if not value:return "Не понимаю, что закрыть."
        kind="close"
    if kind=="spotify":
        from spotify_control import play
        _LAST_TARGETS[session_id]=["Spotify"]; _LAST_ACTION[session_id]=(kind,value); return play(value)
    if kind in {"open","close"}:
        from capabilities.apps import open_target,close_target
        done=[]; failed=[]
        for target in value:
            result=open_target(target) if kind=="open" else close_target(target)
            (done if result.get("success") else failed).append(target if result.get("success") else f"{target}: {result.get('error') or 'не удалось'}")
        if done:_LAST_TARGETS[session_id]=done
        _LAST_ACTION[session_id]=(kind,value)
        if failed and not done:return "Не удалось выполнить: "+"; ".join(failed)
        answer=f"{'Открыл' if kind=='open' else 'Закрыл'}: {', '.join(done)}."
        return answer if not failed else answer+" Не удалось: "+"; ".join(failed)
    if kind=="volume":
        _LAST_ACTION[session_id]=(kind,value); return f"Громкость: {_volume(value=value)}%"
    _LAST_ACTION[session_id]=(kind,value)
    return f"Громкость: {_volume(delta=value)}%"

def get_session(session_id="desktop"):
    import agent_loop; return agent_loop.get_session(session_id)
