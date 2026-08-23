"""Desktop router: explicit OS commands or direct LLM conversation."""
from __future__ import annotations

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

APPS = {"spotify":"Spotify","спотифай":"Spotify","discord":"Discord","дискорд":"Discord","safari":"Safari","сафари":"Safari","chrome":"Google Chrome","хром":"Google Chrome","гугл хром":"Google Chrome","terminal":"Terminal","терминал":"Terminal","finder":"Finder","файндер":"Finder"}
STOP = {"стоп","остановись","отмена","отмени","хватит","stop","cancel"}
MORE = {"дальше","следующий","следующий трек","скип","пропусти"}
CONTEXT: dict[str, dict] = {}
CHAT: dict[str, list[dict]] = {}
LOCK = threading.Lock()
SYSTEM = "Ты Акира, мужской персональный ассистент. Отвечай на русском, естественно и по делу. В обычном разговоре отвечай как AI-модель, используя свои знания и рассуждение. Не подменяй ответы заранее прописанными шаблонами. Не утверждай, что выполнил действие на компьютере, если оно не выполнялось."


def norm(value):
    value = str(value or "").casefold().replace("ё", "е").strip()
    value = re.sub(r"^акира[,:;\-]?\s*", "", value)
    value = re.sub(r"спотифа(?:й|я|е|и|ю)\b", "спотифай", value)
    value = re.sub(r"дискорд(?:а|у|ом|е)?\b", "дискорд", value)
    return re.sub(r"\s+", " ", value).strip(" .,!?:;")


def remember(session, kind, **data):
    CONTEXT[session] = {"kind": kind, **data}


def app_names(chunk):
    names=[]
    for part in re.split(r"\s*(?:,|\bи\b|\bа также\b)\s*", chunk):
        part=re.sub(r"^(?:к|ко|в|на)\s+", "", part.strip())
        if part: names.append(APPS.get(part, part))
    return names


def parse_apps(text):
    matches=list(re.finditer(r"(?:^|\s)(открой|запусти|закрой)\s+", text))
    if not matches or matches[0].start()!=0: return None
    actions=[]
    for i,m in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        chunk=re.sub(r"\s+(?:и|а затем|потом)\s*$", "", text[m.end():end].strip(" ,.!?:;"))
        targets=app_names(chunk)
        if not targets: return None
        actions.append(("open" if m.group(1) in {"открой","запусти"} else "close",targets))
    return actions


def run_apps(actions):
    from capabilities.apps import open_target,close_target
    lines=[]; done=[]
    for operation,targets in actions:
        fn=open_target if operation=="open" else close_target
        results={}
        with ThreadPoolExecutor(max_workers=max(1,len(targets))) as pool:
            futures={pool.submit(fn,t):t for t in targets}
            for future in as_completed(futures):
                target=futures[future]
                try: results[target]=future.result()
                except Exception as exc: results[target]={"success":False,"error":str(exc)}
        ok=[]; bad=[]
        for target in targets:
            result=results[target]
            if result.get("success"): ok.append(target); done.append(target)
            else: bad.append(f"{target}: {result.get('error') or 'не удалось'}")
        if ok: lines.append(("Открыл" if operation=="open" else "Закрыл")+": "+", ".join(ok)+".")
        if bad: lines.append("Не удалось: "+"; ".join(bad))
    return " ".join(lines) or "Не удалось выполнить действие.",done


def volume_get():
    from capabilities.apps import _run
    result=_run("output volume of (get volume settings)")
    if result.returncode: raise RuntimeError("не удалось прочитать громкость")
    return max(0,min(100,int(result.stdout.strip())))


def volume_set(value):
    from capabilities.apps import _run
    value=max(0,min(100,int(value)))
    result=_run(f"set volume output volume {value}")
    if result.returncode: raise RuntimeError("не удалось изменить громкость")
    return value


def conversation(message, session_id):
    from config import MODEL,create_groq_client
    with LOCK: history=list(CHAT.get(session_id,[]))[-16:]
    messages=[{"role":"system","content":SYSTEM},*history,{"role":"user","content":str(message)}]
    client=create_groq_client()
    response=client.chat.completions.create(model=MODEL,messages=messages,temperature=0.7,max_completion_tokens=800)
    answer=str(response.choices[0].message.content or "").strip() or "Не получил ответ."
    with LOCK:
        history=CHAT.setdefault(session_id,[])
        history.extend([{"role":"user","content":str(message)},{"role":"assistant","content":answer}])
        del history[:-16]
    return answer


def ask(message, session_id="desktop"):
    raw=str(message or "").strip(); text=norm(raw)
    if not text: return ""
    if text in STOP:
        CONTEXT.pop(session_id,None); return "Остановил."
    context=CONTEXT.get(session_id,{})
    if text in {"выключи","поставь на паузу","пауза"} and context.get("kind")=="spotify":
        from spotify_control import pause
        return pause()
    if text=="закрой" and context.get("kind")=="apps" and context.get("target"):
        return run_apps([("close",[context["target"]])])[0]
    if text in MORE and context.get("kind")=="spotify":
        from spotify_control import next_track
        return next_track()
    music=re.match(r"^(?:включи|поставь|сыграй)\s+(.+?)\s+(?:на|в)\s+спотифай$",text)
    if music:
        from spotify_control import play
        query=music.group(1).strip(); answer=play(query); remember(session_id,"spotify",query=query); return answer
    if text in MORE:
        from spotify_control import next_track
        return next_track()
    if re.search(r"^(?:(?:какая|какой|сколько|текущая)\s+)?(?:сейчас\s+)?(?:громкость|уровень звука|звук)(?:\s+сейчас)?$",text): return f"Громкость: {volume_get()}%"
    match=re.search(r"(?:громкость|звук)(?:\s+на)?\s+(\d{1,3})(?:\s*%|\s*процент\w*)?$",text)
    if match:
        value=volume_set(match.group(1)); remember(session_id,"volume",delta=10); return f"Громкость: {value}%"
    if re.search(r"\b(?:громче|прибавь|увеличь)\b",text):
        value=volume_set(volume_get()+10); remember(session_id,"volume",delta=10); return f"Громкость: {value}%"
    if re.search(r"\b(?:тише|убавь|уменьши)\b",text):
        value=volume_set(volume_get()-10); remember(session_id,"volume",delta=-10); return f"Громкость: {value}%"
    if re.search(r"(?:выключи|убери)\s+(?:звук|громкость)",text): return f"Громкость: {volume_set(0)}%"
    actions=parse_apps(text)
    if actions:
        answer,done=run_apps(actions)
        if done: remember(session_id,"apps",target=done[-1])
        return answer
    return conversation(raw,session_id)


def get_session(session_id="desktop"):
    with LOCK: return {"session_id":session_id,"history":list(CHAT.get(session_id,[]))}
