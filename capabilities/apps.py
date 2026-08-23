"""macOS application control based on actual system state."""
from __future__ import annotations
import os, subprocess, time
from .filesystem import CapabilityError, resolve_path
from .protocol import fail, ok

def _escape(s): return str(s).replace("\\", "\\\\").replace('"', '\\"')
def _name(target):
    target=str(target).strip()
    return os.path.basename(target).removesuffix(".app") if target.endswith(".app") or "/" in target else target

def _run(script):
    try: return subprocess.run(["osascript","-e",script],capture_output=True,text=True,timeout=10),None
    except Exception as e: return None,str(e)

def app_running(target):
    name=_name(target)
    if not name: return False
    result,error=_run('tell application "System Events" to return exists process "'+_escape(name)+'"')
    if result is None or result.returncode: return None
    return result.stdout.strip().casefold()=="true"

def _activate(name):
    escaped=_escape(name)
    # Restore minimized windows when Accessibility is available; failure here is non-fatal.
    _run('tell application "System Events" to tell process "'+escaped+'"\nrepeat with w in windows\ntry\nset value of attribute "AXMinimized" of w to false\nend try\nend repeat\nend tell')
    result,error=_run('tell application "'+escaped+'" to activate')
    if result is None: return False,error
    if result.returncode: return False,(result.stderr or result.stdout or "activation failed").strip()
    return True,None

def _wait(target,expected,timeout=5):
    end=time.monotonic()+timeout; value=app_running(target)
    while time.monotonic()<end:
        if value is expected: return value
        time.sleep(.1); value=app_running(target)
    return value

def _kind(target):
    low=target.casefold()
    if low.startswith(("http://","https://")): return "url"
    if "/" in target or os.path.exists(os.path.expanduser(target)): return "path"
    return "app"

def open_target(target):
    if not isinstance(target,str) or not target.strip(): return fail("invalid_target","target должен быть непустой строкой.")
    target=target.strip(); kind=_kind(target)
    if kind=="path":
        try: target=str(resolve_path(target))
        except CapabilityError as e: return fail(e.code,str(e))
    if kind=="app":
        name=_name(target); running=app_running(name)
        if running is True:
            active,error=_activate(name)
            return ok({"target":target,"kind":"app","running":True,"activated":True,"verification":"process_state"}) if active else fail("activate_failed",error or "Не удалось активировать приложение.",target=target)
        try: result=subprocess.run(["open","-a",target],capture_output=True,text=True,timeout=15)
        except Exception as e: return fail("execution_error",str(e),target=target)
        if result.returncode: return fail("open_failed",(result.stderr or result.stdout or "Не удалось открыть приложение.").strip(),target=target)
        running=_wait(name,True)
        if running is False: return fail("open_unverified","Приложение не запустилось.",target=target)
        _activate(name)
        return ok({"target":target,"kind":"app","running":running,"activated":True,"verification":"process_state" if running is True else "unavailable"})
    try: result=subprocess.run(["open",target],capture_output=True,text=True,timeout=15)
    except Exception as e: return fail("execution_error",str(e),target=target)
    if result.returncode: return fail("open_failed",(result.stderr or result.stdout or "Не удалось открыть.").strip(),target=target)
    return ok({"target":target,"kind":kind})

def close_target(target):
    if not isinstance(target,str) or not target.strip(): return fail("invalid_target","target должен быть непустой строкой.")
    name=_name(target); running=app_running(name)
    if running is False: return ok({"target":target,"app":name,"running":False,"verification":"process_state"})
    result,error=_run('tell application "'+_escape(name)+'" to quit')
    if result is None: return fail("execution_error",error or "Не удалось закрыть приложение.",target=target)
    if result.returncode: return fail("close_failed",(result.stderr or result.stdout or "Не удалось закрыть приложение.").strip(),target=target)
    running=_wait(name,False)
    if running is True: return fail("close_unverified","Приложение всё ещё запущено.",target=target)
    return ok({"target":target,"app":name,"running":running,"verification":"process_state" if running is False else "unavailable"})
