import argparse, json, sys
from collections import Counter
from config import MODEL, create_groq_client

TOOLS = [
{"type":"function","function":{"name":"open","description":"Open an application, URL, or file.","parameters":{"type":"object","properties":{"target":{"type":"string"}},"required":["target"]}}},
{"type":"function","function":{"name":"observe","description":"Observe the current computer screen.","parameters":{"type":"object","properties":{}}}},
{"type":"function","function":{"name":"type","description":"Type text into the focused field.","parameters":{"type":"object","properties":{"text":{"type":"string"}},"required":["text"]}}},
{"type":"function","function":{"name":"click","description":"Click a UI target by coordinates.","parameters":{"type":"object","properties":{"x":{"type":"integer"},"y":{"type":"integer"}},"required":["x","y"]}}},
{"type":"function","function":{"name":"verify_goal","description":"Verify whether the requested goal is actually satisfied.","parameters":{"type":"object","properties":{}}}},
{"type":"function","function":{"name":"finish_task","description":"Finish only after the goal has been verified.","parameters":{"type":"object","properties":{"result":{"type":"string"}},"required":["result"]}}},
{"type":"function","function":{"name":"shell","description":"Execute an arbitrary shell command.","parameters":{"type":"object","properties":{"command":{"type":"string"}},"required":["command"]}}},
]

SYSTEM = """You are Akira's computer-use reasoning model.
Use the supplied tools to perform the task. Never claim an action happened
without a tool result. Prefer universal computer tools over shell.
After changing the screen, observe again. Do not finish until the result is
actually visible and verified. Use verify_goal and then finish_task."""

GOAL = """Open http://example.test/akira.
The page contains an input id=name and a Submit button.
Enter AKIRA_OK, click Submit, and verify that the page shows HELLO_AKIRA_OK.
Only then finish the task."""

OBS0 = """Browser is frontmost.
URL: http://example.test/akira
Visible UI:
input id=name at x=500 y=300, empty
Submit button at x=600 y=350
result: NOT_SUBMITTED"""

OBS1 = """Browser is frontmost.
URL: http://example.test/akira
Visible UI:
input id=name at x=500 y=300, value=AKIRA_OK
Submit button at x=600 y=350
result: NOT_SUBMITTED"""

OBS2 = """Browser is frontmost.
URL: http://example.test/akira
Visible UI:
input id=name at x=500 y=300, value=AKIRA_OK
Submit button at x=600 y=350
result: HELLO_AKIRA_OK"""

def ask(client, messages, forced_tool=None):
    if forced_tool:
        tool_choice = {
            "type": "function",
            "function": {"name": forced_tool},
        }
    else:
        tool_choice = "auto"

    r = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice=tool_choice,
        temperature=0,
        max_tokens=800,
    )
    return r.choices[0].message

def run(client):
    m = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": GOAL},
    ]

    seq = []
    no_tool_streak = 0

    for step in range(16):
        a = ask(client, m, forced_tool=None)
        calls = a.tool_calls or []

        # Это именно тот случай, который сейчас ломал qualification:
        # модель иногда отвечает текстом, хотя задача ещё активна.
        # Реальный brain.py делает recovery, поэтому harness тоже должен.
        if not calls:
            no_tool_streak += 1
            content = a.content or ""

            if no_tool_streak >= 3:
                return False, seq, f"no_tool_progress:{content[:120]}"

            m.append({
                "role": "assistant",
                "content": content,
            })

            m.append({
                "role": "system",
                "content": (
                    "The task is still active. A text response is not an "
                    "action and does not complete the task. Continue using "
                    "the available tools. After changing the screen, "
                    "observe again. Verify the goal before finishing."
                ),
            })
            continue

        no_tool_streak = 0

        if len(calls) != 1:
            names = [c.function.name for c in calls]
            return False, seq, f"multi_tool_call:{names}"

        c = calls[0]
        name = c.function.name
        seq.append(name)

        m.append({
            "role": "assistant",
            "content": a.content,
            "tool_calls": [{
                "id": c.id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": c.function.arguments,
                },
            }],
        })

        try:
            args = json.loads(c.function.arguments or "{}")
        except Exception:
            return False, seq, "invalid_json"

        if name == "open":
            if args.get("target") != "http://example.test/akira":
                return False, seq, "bad_open"
            result = "opened"

        elif name == "observe":
            if "click" in seq:
                result = OBS2
            elif "type" in seq:
                result = OBS1
            else:
                result = OBS0

        elif name == "type":
            if args.get("text") != "AKIRA_OK":
                return False, seq, "bad_type"
            result = "typed"

        elif name == "click":
            if args.get("x") != 600 or args.get("y") != 350:
                return False, seq, "bad_click"
            result = "submitted"

        elif name == "verify_goal":
            current_page = (
                OBS2
                if "click" in seq
                else OBS1
                if "type" in seq
                else OBS0
            )

            if "HELLO_AKIRA_OK" not in current_page:
                return False, seq, "bad_verification"

            result = "verified"

        elif name == "finish_task":
            ok = seq[-2:] == ["verify_goal", "finish_task"]
            return (
                ok,
                seq,
                None if ok else "finished_without_verify",
            )

        elif name == "shell":
            return False, seq, "used_shell"

        else:
            return False, seq, "unexpected_tool"

        m.append({
            "role": "tool",
            "tool_call_id": c.id,
            "content": result,
        })

    return False, seq, "max_steps"

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--runs",type=int,default=10)
    n=p.parse_args().runs
    client=create_groq_client()
    results=[]
    print("MODEL:",MODEL)
    print("RUNS:",n)
    print("REAL COMPUTER ACTIONS: NONE")
    print()
    for i in range(1,n+1):
        ok,seq,err=run(client)
        results.append((ok,err))
        print(f"{i:02d} {'PASS' if ok else 'FAIL'} {seq} {err or ''}",flush=True)
    passed=sum(x[0] for x in results)
    fails=Counter(e for ok,e in results if not ok)
    print("\n"+"="*60)
    print(f"PASSED: {passed}/{n}")
    print(f"SUCCESS RATE: {passed/n*100:.1f}%")
    if fails:
        print("FAILURES:",dict(fails))
    sys.exit(0 if passed==n else 1)

if __name__=="__main__":
    main()
