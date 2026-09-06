from capability_layer import CAPABILITIES
"""Lightweight relevance router for Akira tools."""

import math
import re

_STOPWORDS = {"и","или","а","но","что","это","как","мне","ты","я","в","на","из","по","для","с","со","у","к","от","до","the","a","an","and","or","to","of","for","in","on","with","is","it","my","me","please"}
ALIASES = {
    "открой":{"open","launch","app","url"}, "открыть":{"open","launch","app","url"}, "запусти":{"open","launch","app","shell","execute","command"}, "запустить":{"open","launch","app","shell","execute","command"},
    "закрой":{"close","quit","app"}, "закрыть":{"close","quit","app"}, "закройся":{"close","quit","app"}, "найди":{"find","search"}, "найти":{"find","search"}, "поиск":{"find","search"},
    "файл":{"file","filesystem","read","write","create"}, "файлы":{"file","filesystem","read","write","create"}, "прочитай":{"read","file"}, "прочитать":{"read","file"}, "запиши":{"write","file"}, "записать":{"write","file"}, "создай":{"create","write","file"}, "создать":{"create","write","file"},
    "перемести":{"move","file"}, "переместить":{"move","file"}, "скопируй":{"copy","file"}, "скопировать":{"copy","file"}, "переименуй":{"rename","file"}, "переименовать":{"rename","file"}, "удали":{"delete","file"}, "удалить":{"delete","file"},
    "терминал":{"shell","command","terminal"}, "команда":{"shell","command","terminal"}, "выполни":{"shell","execute","command"}, "экран":{"observe","screen","vision"}, "посмотри":{"observe","screen","vision"}, "посмотреть":{"observe","screen","vision"}, "скрин":{"observe","screen","vision"},
    "кликни":{"click","select","gui"}, "клик":{"click","select","gui"}, "нажми":{"click","key","gui"}, "нажать":{"click","key","gui"}, "напиши":{"type","text","gui"}, "введи":{"type","text","gui"}, "ввести":{"type","text","gui"}, "напечатай":{"type","text","gui"}, "перетащи":{"drag","gui"}, "перетащить":{"drag","gui"}, "прокрути":{"scroll","gui"}, "прокрутить":{"scroll","gui"}, "подожди":{"wait"}, "подождать":{"wait"},
    # Media/app colloquialisms commonly produced by Russian speech input.
    "ютуб":{"youtube","video","browser","open"}, "ютюб":{"youtube","video","browser","open"}, "youtube":{"youtube","video","browser","open"},
    "спотифай":{"spotify","music","browser","open"}, "споти":{"spotify","music","browser","open"}, "спотик":{"spotify","music","browser","open"}, "спотифайка":{"spotify","music","browser","open"}, "spotify":{"spotify","music","browser","open"},
    "телеграм":{"telegram","app","close","open"}, "телеграмм":{"telegram","app","close","open"}, "тг":{"telegram","app","close","open"}, "тгшка":{"telegram","app","close","open"}, "телега":{"telegram","app","close","open"},
    "музыка":{"spotify","music","audio"}, "музыку":{"spotify","music","audio"}, "песня":{"spotify","music","audio"}, "песню":{"spotify","music","audio"}, "трек":{"spotify","music","audio"}, "альбом":{"spotify","music","audio"},
    "включи":{"spotify","music","play","audio"}, "включить":{"spotify","music","play","audio"}, "проиграй":{"spotify","music","play","audio"}, "проиграть":{"spotify","music","play","audio"},
    "исполнитель":{"spotify","music","artist","play"}, "исполнителя":{"spotify","music","artist","play"}, "артист":{"spotify","music","artist","play"}, "артиста":{"spotify","music","artist","play"},
    # Volume requests must keep both read and write volume tools available so
    # the model can inspect the current level before changing it.
    "громкость":{"volume","audio","get_volume","set_volume"}, "громко":{"volume","audio","set_volume"}, "громче":{"volume","audio","set_volume","get_volume"}, "тише":{"volume","audio","set_volume","get_volume"}, "тихо":{"volume","audio","set_volume","get_volume"}, "звук":{"volume","audio","mute_volume","get_volume"}, "беззвучный":{"volume","audio","mute_volume"}, "мут":{"volume","audio","mute_volume"},
    "память":{"memory","remember"}, "запомни":{"memory","remember"}, "вспомни":{"memory","recall"}, "задача":{"task","plan"}, "задачу":{"task","plan"}, "план":{"plan","task"}, "спланируй":{"plan","task"}, "сделай":{"task","plan","execute"},
}

def _tokens(text):
    if not text: return set()
    result=set()
    for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9_]+",str(text).lower()):
        if token not in _STOPWORDS:
            result.add(token); result.update(ALIASES.get(token,()))
    return result

def _score(query,schema):
    function=schema.get("function",{}) if isinstance(schema,dict) else {}
    name=str(function.get("name","")).lower(); description=str(function.get("description","")).lower()
    query_tokens=_tokens(str(query or "").lower()); schema_tokens=_tokens(name+" "+description)
    score=math.log1p(len(query_tokens & schema_tokens)) if query_tokens & schema_tokens else 0.0
    if name in query_tokens: score += 2.0
    semantic_tokens=set()
    for capability in CAPABILITIES:
        try:
            if capability.tool.lower()==name:
                semantic_tokens.update(_tokens(capability.operation)); semantic_tokens.update(_tokens(capability.name))
        except Exception: continue
    overlap=query_tokens & semantic_tokens
    if overlap: score += 0.75*math.log1p(len(overlap))
    return score

def _always_include(task_active):
    # observe is intentionally NOT mandatory: screenshots are evidence only for
    # visual questions. System actions use their authoritative state checks.
    base={"finish_task","discover_capability","verify_goal"}
    if task_active: base.update({"plan_task","update_task_plan","complete_plan_step","fail_plan_step"})
    return base

def select_tool_schemas(query,schemas,limit=12,task_active=False,pinned_tools=None):
    if not schemas: return []
    scored=[]
    for schema in schemas:
        name=schema.get("function",{}).get("name",""); scored.append((_score(query,schema),name,schema))
    scored.sort(key=lambda item:(-item[0],item[1]))
    mandatory=_always_include(task_active)
    if pinned_tools: mandatory.update(str(name) for name in pinned_tools if name)
    selected=[]; selected_names=set()
    for _,name,schema in scored:
        if name in mandatory: selected.append(schema); selected_names.add(name)
    remaining=max(0,limit-len(selected)); added=0
    for score,name,schema in scored:
        if name in selected_names: continue
        if added>=remaining: break
        if score<=0: continue
        selected.append(schema); selected_names.add(name); added+=1
    useful=[score for score,_,_ in scored if score>0]
    if not useful or max(useful)<1.0: return list(schemas)
    return selected

def explain_selection(query,schemas,limit=12,task_active=False,pinned_tools=None):
    selected=select_tool_schemas(query,schemas,limit=limit,task_active=task_active,pinned_tools=pinned_tools)
    return {"query":query,"selected":[schema.get("function",{}).get("name") for schema in selected],"count":len(selected),"total":len(schemas)}
