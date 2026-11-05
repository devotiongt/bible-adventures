"""Renders 4 views of a generated object (front, right, back, left), in flat gray on a white background,
for Gemini to paint by material (references/PROMPTS.md, no. 17). The cameras are fixed (VIEWS), so
paint_materials.py knows exactly where each pixel is seen from.

Usage:
    blender --background --factory-startup --python tools/blender/gemini_views.py -- well
Saves references/views/<name>_<view>.png and a sheet with all 4: references/views/<name>_sheet.png.
"""

import math
import os
import sys

import bpy
from mathutils import Vector

ROOT = os.getcwd()
_ns = {"__name__": "process_generated"}
exec(open(os.path.join(ROOT, "tools/blender/process_generated.py"), encoding="utf-8").read()
     .replace("\nmain()\n", "\n"), _ns)
load, clean, place, base, KEEP_CHUNKS = _ns["load"], _ns["clean"], _ns["place"], _ns["base"], _ns["KEEP_CHUNKS"]

# Camera yaw (degrees around Z, 0 = front, looking toward +Y) and elevation (degrees above the horizon).
VIEWS = {"front": (0, 25), "right": (90, 25), "back": (180, 25), "left": (270, 25)}
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
    clean(obj, base(name) in KEEP_CHUNKS)
    place(obj, name)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "SINGLE"
    scene.display.shading.single_color = (0.75, 0.75, 0.75)
    scene.display.shading.show_cavity = True
    scene.render.resolution_x = scene.render.resolution_y = RES
    scene.render.film_transparent = True        # Put on white afterwards.
    world = bpy.data.worlds.new("white")
    world.color = (1, 1, 1)
    scene.world = world
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (1, 1, 1)
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.data.type = "ORTHO"
    out = os.path.join(ROOT, "references/views")
    os.makedirs(out, exist_ok=True)
    for view, (yaw, elev) in VIEWS.items():
        loc, target, scale = camera_for(obj, yaw, elev)
        cam.location = loc
        cam.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()
        cam.data.ortho_scale = scale
        scene.render.filepath = os.path.join(out, f"{name}_{view}.png")
        bpy.ops.render.render(write_still=True)
        img = bpy.data.images.load(scene.render.filepath)
        px = list(img.pixels[:])
        for k in range(0, len(px), 4):               # On a white background.
            a = px[k + 3]
            for c in range(3):
                px[k + c] = px[k + c] * a + (1 - a)
            px[k + 3] = 1.0
        img.pixels[:] = px
        img.save()
    print("VIEWS", name, "->", out)


if __name__ == "__main__":
    main()
