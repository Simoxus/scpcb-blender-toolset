import os
import bpy
import json

from pathlib import Path
from .process_b3d import B3DTree
from mathutils import Matrix, Vector, Quaternion
from math import radians
from bpy_extras.io_utils import unpack_list
from .common_functions import RandomColorGenerator, get_file, is_string_empty, DX_MATRIX_IMPORT

def flip(v):
    return ((v[0],v[2],v[1]) if len(v)<4 else (v[0], v[1],v[3],v[2]))

def import_mesh(context, data, node, material_list):
    if data.get("brush_count") is None:
        data["brush_count"] = 0

    vertices = [Vector(flip(vertex)) for vertex in node["vertices"]]
    faces = [face for brush in node["faces"] for face in brush["indices"]]

    mesh = bpy.data.meshes.new("%s_brush" % data["brush_count"])

    mesh.from_pydata(vertices, [], faces)

    object_mesh = bpy.data.objects.new("brush_%s" % data["brush_count"], mesh)
    context.collection.objects.link(object_mesh)

    poly = 0
    for face in node["faces"]:
        for face_idx in face["indices"]:
            brush_mat = material_list[face["brush_id"]]
            if brush_mat.name not in object_mesh.data.materials.keys():
                object_mesh.data.materials.append(brush_mat)

            mat_id = object_mesh.data.materials.keys().index(brush_mat.name)
            object_mesh.data.polygons[poly].material_index = mat_id
            poly += 1

    uv_count = len(node["uvs"][0]) / 2
    layer_color = object_mesh.data.color_attributes.new("color", "BYTE_COLOR", "CORNER")
    layer_uv_0 = object_mesh.data.uv_layers.new(name="uvmap_render")
    if uv_count > 1:
        layer_uv_1 = object_mesh.data.uv_layers.new(name="uvmap_lightmap")

    for poly in object_mesh.data.polygons:
        poly.use_smooth = True
        for loop_index in poly.loop_indices:
            vert_index = object_mesh.data.loops[loop_index].vertex_index
            if uv_count == 1:
                U0, V0 = node["uvs"][vert_index]
            else:
                U0, V0, U1, V1 = node["uvs"][vert_index]

            layer_uv_0.data[loop_index].uv = (U0, 1 - V0)
            if uv_count > 1:
                layer_uv_1.data[loop_index].uv = (U1, 1 - V1)
            
            rgba_count = len(node["rgba"])
            if rgba_count > 0:
                layer_color.data[loop_index].color = node["rgba"][vert_index]

    mesh.transform(Matrix.Scale(0.00625, 4))

    data["brush_count"] += 1

    return object_mesh

def parse_kv_string(s):
    if not s:
        return s

    result = {}
    found_kv = False

    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue

        if "=" not in line:
            continue

        found_kv = True
        key, value = line.split("=", 1)
        value = value.strip()
        if " " in value:
            parts = value.split()
            parsed = []
            for p in parts:
                try:
                    parsed.append(int(p))
                except ValueError:
                    try:
                        parsed.append(float(p))
                    except ValueError:
                        parsed.append(p)
            result[key] = parsed
        else:
            try:
                result[key] = int(value)
            except ValueError:
                try:
                    result[key] = float(value)
                except ValueError:
                    result[key] = value

    if not found_kv:
        return {"classname": s.strip()}

    return result

def import_node_recursive(context, data, nodes, material_list, parent_ob=None):
    for node in nodes:
        result = parse_kv_string(node["name"])
        if result["classname"] == "brush" and node.get("mesh"):
            object_mesh = import_mesh(context, data, node["mesh"], material_list)

        elif result["classname"] == "soundemitter":
            if data.get("soundemitter_count") is None:
                data["soundemitter_count"] = 0

            speaker_data = bpy.data.speakers.new("%s soundemitter" % data["soundemitter_count"])
            object_mesh = bpy.data.objects.new("%s_soundemitter" % data["soundemitter_count"], speaker_data)
            context.collection.objects.link(object_mesh)

            data["soundemitter_count"] += 1

        elif result["classname"] == "light":
            if data.get("light_count") is None:
                data["light_count"] = 0

            object_data = bpy.data.lights.new("%s light" % data["light_count"], "POINT")
            object_mesh = bpy.data.objects.new("%s_light" % data["light_count"], object_data)
            context.collection.objects.link(object_mesh)

            object_data.energy = result["intensity"] * 50
            object_data.shadow_soft_size = result["range"] / 1000
            r, g, b = result["color"]
            object_data.color = (r / 255, g / 255, b / 255)

            data["light_count"] += 1

        elif result["classname"] == "spotlight":
            if data.get("spotlight_count") is None:
                data["spotlight_count"] = 0

            object_data = bpy.data.lights.new("%s spotlight" % data["spotlight_count"], "SPOT")
            object_mesh = bpy.data.objects.new("%s_spotlight" % data["spotlight_count"], object_data)
            context.collection.objects.link(object_mesh)

            object_data.energy = result["intensity"] * 50
            object_data.shadow_soft_size = result["range"] / 1000
            r, g, b = result["color"]
            object_data.color = (r / 255, g / 255, b / 255)

            outer_deg: float = max(1.0, min(180.0, result["outerconeangle"]))
            inner_deg: float = max(1.0, min(180.0, result["innerconeangle"]))
            ratio = inner_deg / outer_deg if outer_deg > 0.0 else 1.0

            object_data.spot_size = radians(outer_deg)
            object_data.spot_blend = max(0.0, min(1.0, 1.0 - ratio))

            data["spotlight_count"] += 1

        else:
            if node.get("mesh"):
                object_mesh = import_mesh(context, data, node["mesh"], material_list)
            else:
                object_mesh = bpy.data.objects.new(result["classname"], None)
                context.collection.objects.link(object_mesh)

        if parent_ob is not None:
            object_mesh.parent = parent_ob
            object_mesh.matrix_world = parent_ob.matrix_world
        
        object_mesh.matrix_local = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))

        import_node_recursive(context, data, node["nodes"], material_list, object_mesh)

def export_scene(context, filepath, report):
    print()

def import_scene(context, filepath, report):
    game_path = Path(bpy.context.preferences.addons["io_scene_rmesh"].preferences.game_path)

    local_asset_path = ""
    if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
        local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

    data = B3DTree().parse(Path(filepath))

    random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    material_list = []
    texture_count = len(data["textures"])
    for material_dict in data["materials"]:
        material = bpy.data.materials.new(material_dict["name"])
        material.diffuse_color = random_color_gen.next()

        material.use_nodes = True
        nodes = material.node_tree.nodes
        bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')

        r, g, b, a = material_dict["rgba"]
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
        bsdf.inputs["Alpha"].default_value = a

        material.blend_method = 'BLEND' if a < 1.0 else 'OPAQUE'

        for tid_element in material_dict["tids"]:
            if tid_element != -1 and texture_count > tid_element:
                texture = data["textures"][tid_element]
                texture_asset = get_file(os.path.basename(texture['name']), True, True, directory_path=local_asset_path)

                material.use_nodes = True
                bsdf = material.node_tree.nodes["Principled BSDF"]
                texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
                texImage.image = texture_asset
                if not "_lm" in texture['name']:
                    material.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])

        material_list.append(material)

    import_node_recursive(context, data, data["nodes"], material_list)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
