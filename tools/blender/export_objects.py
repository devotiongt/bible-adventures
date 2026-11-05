"""Gathers the hand-touched village objects (one file per object in tools/blender/objects/)
and exports them to the game, all in assets/village/generated.glb.

Usage (without opening Blender):
    blender --background --factory-startup --python tools/blender/export_objects.py

Each <name>.blend file has a single mesh object, with its origin on the ground and its color painted on
the vertices. The object takes the file's name (that's what the piece is called in the game).
"""

import glob
import os

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "tools/blender/objects")
OUT = os.path.join(ROOT, "assets/village/generated.glb")

bpy.ops.wm.read_factory_settings(use_empty=True)
names = []
for path in sorted(glob.glob(os.path.join(SRC, "*.blend"))):
    name = os.path.splitext(os.path.basename(path))[0]
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = list(src.objects)
    meshes = [o for o in dst.objects if o is not None and o.type == "MESH"]
    if len(meshes) != 1:
        print("WARNING", name, "has", len(meshes), "meshes; taking the first one")
    obj = meshes[0]
    bpy.context.scene.collection.objects.link(obj)
    obj.name = name
    obj.location = (0, 0, 0)
    names.append(name)
bpy.ops.object.select_all(action="SELECT")
bpy.ops.export_scene.gltf(filepath=OUT, export_format="GLB", use_selection=True, export_yup=True,
                          export_vertex_color="ACTIVE")
print("EXPORTED", len(names), "objects ->", OUT)
