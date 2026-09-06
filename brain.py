"""Compatibility facade for the canonical Akira agent loop."""
from __future__ import annotations
from pathlib import Path
import shutil
from config import COMPUTER_USE_MAX_STEPS, MAX_TOOL_ITERATIONS, MAX_ACTIONS_WITHOUT_OBSERVE, NO_PROGRESS_LIMIT, MODEL
from permissions import get_permission, request_confirmation
from tool_registry import get_tool_implementation, get_tool_schemas
from capabilities.protocol import result_to_text, is_structured
import agent_loop as _agent_loop
from agent_loop import get_session as _canonical_get_session

_ACTION_FIRST_RULES = """

ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА ПОВЕДЕНИЯ:
- Пользователь — твой создатель и уже знает, кто ты. Никогда не представляйся при
  обычном приветствии и не объясняй, что ты «персональный помощник». На короткое
  приветствие отвечай коротко и естественно.
- Ты работаешь на macOS и реально управляешь компьютером через доступные tools.
  Никогда не отвечай шаблонным «я не могу напрямую открыть приложение», не давай
  инструкции для Windows/меню Пуск и не отправляй пользователя делать вручную то,
  что можешь сделать tool'ом.
- Если пользователь просит выполнить действие на компьютере, сначала ВЫПОЛНИ его
  доступным tool/capability. Текстовая инструкция вместо вызова доступного tool —
  неправильный ответ.
- Для медиа-запросов используй соответствующую зарегистрированную capability и
  сначала попробуй выполнить запрос, а не объяснять пользователю, как сделать его вручную.
- Отсутствие capability в текущем динамическом срезе tools не означает, что её нет:
  используй discover_capability и продолжай.
- О реальном ограничении сообщай только после фактической ошибки инструмента и
  попытки самостоятельного recovery.
"""

SYSTEM_PROMPT = _agent_loop.SYSTEM_PROMPT + _ACTION_FIRST_RULES
_agent_loop.SYSTEM_PROMPT = SYSTEM_PROMPT
SYSTEM=SYSTEM_PROMPT; TOOLS=get_tool_schemas(); client=None
conversation=_canonical_get_session(None).history
conversation.clear()

def _ensure_client():
    import config
    global client
    if config._client is None: client=config.create_groq_client()
    else: client=config._client
    return config._client

def _tool_result_text(result): return result_to_text(result)
def _invalid_arguments_result(function_name,error): return {"success":False,"error":"invalid_arguments","output":"Невалидный JSON аргументов для "+function_name+": "+str(error)}

def execute_tool_result(function_name,arguments,source=None):
    arguments=dict(arguments or {}); permission=get_permission(function_name)
    if permission=="blocked": return {"success":False,"error":"permission_denied","output":"Инструмент заблокирован настройками разрешений."}
    if permission=="confirm" and not request_confirmation(function_name,arguments): return {"success":False,"error":"confirmation_denied","output":"Пользователь не разрешил выполнение действия."}
    implementation=get_tool_implementation(function_name)
    if implementation is None: return {"success":False,"error":"unknown","output":"Неизвестный инструмент."}
    try:
        result=implementation(**arguments)
        if is_structured(result): return result
        return {"success":True,"error":None,"output":str(result)}
    except Exception as exc: return {"success":False,"error":"execution_error","output":f"Ошибка выполнения инструмента: {exc}"}

def execute_tool(function_name,arguments): return execute_tool_result(function_name,arguments)["output"]
def _should_stop(session):
    from agent_loop import _should_stop as canonical_should_stop
    return canonical_should_stop(session)

def _sync_compat_audit(agent_loop):
    try:
        import audit
        destination=Path(audit.AUDIT_FILE)
        if destination.exists(): return
        old_globals=getattr(agent_loop.record_tool_execution,"__globals__",{})
        source=Path(old_globals.get("AUDIT_FILE", ""))
        if source.exists() and source.resolve()!=destination.resolve(): destination.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,destination)
    except (OSError,TypeError,ValueError): pass

class Brain:
    def ask(self,message,session_id=None): return ask(message,session_id=session_id)
    def run(self,message,session_id=None): return self.ask(message,session_id=session_id)
    def handle(self,message,session_id=None): return self.ask(message,session_id=session_id)
    def process(self,message,session_id=None): return self.ask(message,session_id=session_id)
    def decide(self,goal,context=None): raise RuntimeError("Structured decisions are owned by agent_loop.ask; use Brain.ask.")

def ask(message,session_id=None):
    import agent_loop
    if _ACTION_FIRST_RULES not in agent_loop.SYSTEM_PROMPT:
        agent_loop.SYSTEM_PROMPT += _ACTION_FIRST_RULES
    injected_client=client
    if injected_client is not None: agent_loop.client=injected_client
    agent_loop.get_permission=get_permission; agent_loop.get_tool_implementation=get_tool_implementation; agent_loop.request_confirmation=request_confirmation; agent_loop._invalid_arguments_result=_invalid_arguments_result
    try: return agent_loop.ask(message,session_id=session_id)
    finally:
        _sync_compat_audit(agent_loop)
        if injected_client is not None: agent_loop.client=None

def get_session(session_id=None): return _canonical_get_session(session_id)
