"""Saca 4 vistas de un objeto generado (frente, derecha, atrás, izquierda), en gris liso y con fondo blanco,
para que Gemini las pinte por material (referencias/PROMPTS.md, n.º 17). Las cámaras son fijas (VISTAS), así
pintar_materiales.py sabe exactamente desde dónde se ve cada píxel.

Uso:
    blender --background --factory-startup --python herramientas/blender/vistas_gemini.py -- pozo
Guarda referencias/vistas/<nombre>_<vista>.png y una hoja con las 4: referencias/vistas/<nombre>_hoja.png.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.getcwd()
_ns = {"__name__": "procesar_generados"}
exec(open(os.path.join(ROOT, "herramientas/blender/procesar_generados.py"), encoding="utf-8").read()
     .replace("\nmain()\n", "\n"), _ns)
load, clean, place, base, CONSERVAR_TROZOS = _ns["load"], _ns["clean"], _ns["place"], _ns["base"], _ns["CONSERVAR_TROZOS"]

# Giro (grados alrededor de Z, 0 = frente, mirando hacia +Y) y altura de la cámara (grados sobre el horizonte).
VISTAS = {"frente": (0, 25), "derecha": (90, 25), "atras": (180, 25), "izquierda": (270, 25)}
RES = 768


def camera_for(obj, yaw, elev):
    d = max(obj.dimensions)
    center = Vector((0, 0, obj.dimensions.z / 2))
    direction = Vector((math.sin(math.radians(yaw)) * math.cos(math.radians(elev)),
                        -math.cos(math.radians(yaw)) * math.cos(math.radians(elev)),
                        math.sin(math.radians(elev))))
    return center + direction * d * 4, center, d * 1.55


def main():
    name = sys.argv[sys.argv.index("--") + 1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    obj = load(name)
    clean(obj, base(name) in CONSERVAR_TROZOS)
    place(obj, name)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.75, 0.75, 0.75)
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.film_transparent = True        # Luego se pone sobre blanco.
    world = bpy.data.worlds.new("blanco")
    world.color = (1, 1, 1)
    scene.world = world
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (1, 1, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    out = os.path.join(ROOT, "referencias/vistas")
    os.makedirs(out, exist_ok=True)
    for view, (yaw, elev) in VISTAS.items():
        loc, target, scale = camera_for(obj, yaw, elev)
        cam.location = loc
        cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = scale
        scene.render.filepath = os.path.join(out, f"{name}_{view}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(scene.render.filepath)
        px = list(img.pixels[:])
        for k in range(0, len(px), 4):               # Sobre fondo blanco.
            a = px[k + 3]
            for c in range(3):
                px[k + c] = px[k + c] * a + (1 - a)
            px[k + 3] = 1.0
        img.pixels[:] = px
        img.save()
    print("VISTAS", name, "->", out)


if __name__ == "__main__":
    main()
