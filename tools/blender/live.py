"""Sends a tools/blender script to an open Blender, step by step, to watch it live.

Uses the blender-mcp add-on server (localhost:9876), which starts on its own when Blender opens.
    python3 tools/blender/live.py tunic step_import step_slim ... [--pause 2]
Each step is a function of the script; between steps Blender redraws the scene.
"""

import json
import os
import socket
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# Runs each step with the 3D view's context, so Blender operators
# work even though the code arrives from the add-on.
RUNNER = """
def _live_run(fn):
    import bpy
    wm = bpy.context.window_manager
    override = {}
    if wm and wm.windows:
        win = wm.windows[0]
        override = {"window": win, "screen": win.screen}
        for area in win.screen.areas:
            if area.type == "VIEW_3D":
                override["area"] = area
                override["region"] = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(**override):
        return fn()
"""


def send(code, timeout=1800):
    with socket.create_connection(("localhost", 9876), timeout=timeout) as sock:
        sock.sendall(json.dumps({"type": "execute_code", "params": {"code": code}}).encode())
        data = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
            try:
                return json.loads(data.decode())
            except json.JSONDecodeError:
                continue
    return {"status": "error", "message": "no response"}


def main():
    args = sys.argv[1:]
    pause = 2.0
    if "--pause" in args:
        i = args.index("--pause")
        pause = float(args[i + 1])
        del args[i:i + 2]
    script, steps = args[0], args[1:]
    with open(os.path.join(ROOT, "tools", "blender", script + ".py"), encoding="utf-8") as f:
        source = f.read()
    for step in steps:
        call = step if "(" in step else step + "()"
        code = f"LIVE = True\nPROJECT_ROOT = {ROOT!r}\n{source}\n{RUNNER}\n_live_run(lambda: {call})\n"
        result = send(code)
        ok = result.get("status") == "success"
        output = (result.get("result") or {}).get("result", "") if ok else result.get("message", "")
        print(f"{'✓' if ok else '✗'} {step}  {output.strip()[:1500]}")
        if not ok:
            sys.exit(1)
        time.sleep(pause)


main()
