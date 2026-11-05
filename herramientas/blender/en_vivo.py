"""Envía un script de herramientas/blender a un Blender abierto, paso a paso, para verlo en vivo.

Usa el servidor del add-on blender-mcp (localhost:9876), que arranca solo al abrir Blender.
    python3 herramientas/blender/en_vivo.py tunica paso_importar paso_torso ... [--pausa 2]
Cada paso es una función del script; entre pasos Blender redibuja la escena.
"""

import json
import os
import socket
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# Ejecuta cada paso con el contexto de la vista 3D, para que los operadores de Blender
# funcionen aunque el código llegue desde el add-on.
RUNNER = """
def _en_vivo_run(fn):
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
    return {"status": "error", "message": "sin respuesta"}


def main():
    args = sys.argv[1:]
    pause = 2.0
    if "--pausa" in args:
        i = args.index("--pausa")
        pause = float(args[i + 1])
        del args[i:i + 2]
    script, steps = args[0], args[1:]
    with open(os.path.join(ROOT, "herramientas", "blender", script + ".py"), encoding="utf-8") as f:
        source = f.read()
    for step in steps:
        call = step if "(" in step else step + "()"
        code = f"EN_VIVO = True\nPROJECT_ROOT = {ROOT!r}\n{source}\n{RUNNER}\n_en_vivo_run(lambda: {call})\n"
        result = send(code)
        ok = result.get("status") == "success"
        output = (result.get("result") or {}).get("result", "") if ok else result.get("message", "")
        print(f"{'✓' if ok else '✗'} {step}  {output.strip()[:1500]}")
        if not ok:
            sys.exit(1)
        time.sleep(pause)


main()
