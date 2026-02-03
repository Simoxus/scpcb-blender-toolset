import os
import bpy
import json

from pathlib import Path
from .process_b3d import B3DTree
from mathutils import Matrix, Vector, Quaternion
from math import radians, sqrt
from .common_functions import RandomColorGenerator, get_file, is_string_empty
from collections import defaultdict
from bpy_extras import anim_utils


def flip(v):
    return ((v[0],v[2],v[1]) if len(v)<4 else (v[0], v[1],v[3],v[2]))

def import_mesh(data, node, material_list):
    vertices = []
    faces = []
    loop_normals = []
    for vertex in node["vertices"]:
        x, y, z = vertex
        vertices.append(Vector((x, z, y)))

    for brush in node["faces"]:
        for face in brush["indices"]:
            x, y, z = face
            faces.append((x, z, y))
        
    mesh = bpy.data.meshes.new("mesh")
    mesh.from_pydata(vertices, [], faces)

    # One of these is for some reason fixing a crash I get when I set custom normals. - Gen
    mesh.validate(clean_customdata=True)
    mesh.update(calc_edges=True)
    bpy.context.view_layer.update()

    normal_count = len(node["normals"])
    rgba_count = len(node["rgba"])

    material_indicies = []
    for brush in node["faces"]:
        brush_id = brush["brush_id"]
        if brush_id >= 0:
            for face in brush["indices"]:
                brush_mat = material_list[brush_id]
                if brush_mat.name not in mesh.materials.keys():
                    mesh.materials.append(brush_mat)

                material_indicies.append(mesh.materials.keys().index(brush_mat.name))

    uv_count = len(node["uvs"][0]) / 2
    layer_color = mesh.color_attributes.new("color", "BYTE_COLOR", "CORNER")
    layer_uv_0 = mesh.uv_layers.new(name="uvmap_render")
    if uv_count > 1:
        layer_uv_1 = mesh.uv_layers.new(name="uvmap_lightmap")

    material_count = len(material_indicies)
    for poly_idx, poly in enumerate(mesh.polygons):
        poly.use_smooth = True
        if material_count > poly_idx:
            poly.material_index = material_indicies[poly_idx]
        for loop_index in poly.loop_indices:
            vert_index = mesh.loops[loop_index].vertex_index
            if normal_count > 0:
                i, j, k = node["normals"][vert_index]
                loop_normals.append((i, k, j))

            if uv_count == 1:
                U0, V0 = node["uvs"][vert_index]
            else:
                U0, V0, U1, V1 = node["uvs"][vert_index]

            layer_uv_0.data[loop_index].uv = (U0, 1 - V0)
            if uv_count > 1:
                layer_uv_1.data[loop_index].uv = (U1, 1 - V1)
            

            if rgba_count > 0:
                layer_color.data[loop_index].color = node["rgba"][vert_index]

    if normal_count > 0:
        mesh.normals_split_custom_set(loop_normals)

    mesh.transform(Matrix.Scale(0.00625, 4))

    return mesh

def get_fcurve(fcurves, data_path, index):
    for fc in fcurves:
        if fc.data_path == data_path and fc.array_index == index:
            return fc
    return None

def import_fcurve_data(ob, strips, bone_name, keyframe_dict, node_transform, is_bone=True):
    last_position = Vector()
    last_rotation = Quaternion()
    last_scale = Vector((1,1,1))
    for strip in strips:
        action = strip.action
        fcurve_map = defaultdict(lambda: defaultdict(dict))
        data_paths={
            "location": 3,
            "rotation_euler": 3,
            "rotation_quaternion": 4,
            "scale": 3
        }

        for path,count in data_paths.items():
            for index in range(count):
                if is_bone:
                    fcurve_data_path = f'pose.bones["{bone_name}"].{path}'
                    group_name = bone_name
                    slot_name = ob.name

                else:
                    fcurve_data_path  =path
                    group_name = ob.name
                    slot_name = ob.name

                if (5,0,0)<=bpy.app.version:
                    if action.slots:
                        action_slot = action.slots[0]

                    else:
                        action_slot = action.slots.new(id_type='OBJECT', name=slot_name)
                        strip.action_slot = action_slot

                    channelbag = anim_utils.action_ensure_channelbag_for_slot(action, action_slot)
                    fcurve = channelbag.fcurves.ensure(fcurve_data_path, index=index, group_name=group_name)

                else:
                    fcurve = get_fcurve(action.fcurves, fcurve_data_path, index)
                    if not fcurve:
                        fcurve = action.fcurves.new(data_path=fcurve_data_path, index=index, action_group=group_name)

                fcurve_map[group_name][path][index] = fcurve

        for keyframe_section in keyframe_dict:
            for frame_data in keyframe_section:
                frame_number = frame_data["frame"]
                if action.frame_start <= frame_number <= action.frame_end:
                    position_field = frame_data.get("position")
                    rotation_field = frame_data.get("rotation")
                    scale_field = frame_data.get("scale")
                    if position_field is not None:
                        last_position = Matrix.Scale(0.00625,4) @ Vector(flip(position_field))

                    if rotation_field is not None:
                        last_rotation = Quaternion(flip(rotation_field))

                    if scale_field is not None:
                        last_scale = Vector(flip(scale_field))

                    if is_bone:
                        transform_matrix = node_transform.inverted() @ Matrix.LocRotScale(last_position, last_rotation, last_scale)
                    else:
                        transform_matrix = Matrix.LocRotScale(last_position, last_rotation, last_scale)
                    loc, rot_quat, scl = transform_matrix.decompose()
                    rot_euler = rot_quat.to_euler('XYZ')
                    for i in range(3):
                        fcurve_map[group_name]['location'][i].keyframe_points.insert(frame_number, loc[i], options={'FAST'})
                        fcurve_map[group_name]['scale'][i].keyframe_points.insert(frame_number, scl[i], options={'FAST'})
                        fcurve_map[group_name]['rotation_quaternion'][i].keyframe_points.insert(frame_number, rot_quat[i], options={'FAST'})
                        fcurve_map[group_name]['rotation_euler'][i].keyframe_points.insert(frame_number, rot_euler[i], options={'FAST'})

                    fcurve_map[group_name]['rotation_quaternion'][3].keyframe_points.insert(frame_number, rot_quat[3], options={'FAST'})

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

def vector_length(v):
    return v.length if hasattr(v, "length") else sqrt(sum(c * c for c in v))

def avg_length(node):
    final_length = 0.001
    vectors = []
    for node in node["nodes"]:
        x, y, z = node["position"]
        vectors.append(Matrix.Scale(0.00625, 4) @ Vector((x, z, y)))

    if len(vectors) >= 1:
        final_length = sum(vector_length(v) for v in vectors) / len(vectors)

    return final_length

def import_node_recursive(context, data, nodes, material_list, parent_ob=None, armature=None, armature_mesh=None, strips=None):
    for node in nodes:
        has_bones = node.get("bones") is not None

        result = parse_kv_string(node["name"])
        if has_bones and armature is None:
            object_data = bpy.data.armatures.new(result["classname"])
            object_mesh = armature =  bpy.data.objects.new(result["classname"], object_data)
            context.collection.objects.link(object_mesh)

            if armature_mesh:
                armature_modifier = armature_mesh.modifiers.new("Armature", type='ARMATURE')
                armature_modifier.object = armature

            node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            if parent_ob is not None:
                object_mesh.parent = parent_ob
                node_transform = parent_ob.matrix_world @ node_transform

            object_mesh.matrix_world = node_transform

            context.view_layer.objects.active = armature
            bpy.ops.object.mode_set(mode='EDIT')

            actions = []
            for anim_node in data["nodes"]:
                anim_dict = anim_node.get("anim")
                if anim_dict is not None:
                    bpy.data.scenes["Scene"].frame_end = anim_dict["frames"]

            for sequence_node in data["nodes"]:
                sequences_dict = sequence_node.get("sequences")
                if sequences_dict is not None:
                    for sequence_element in sequences_dict:
                        action = bpy.data.actions.new(name=sequence_element["name"])
                        action.use_frame_range = True
                        action.frame_start = sequence_element["start"]
                        action.frame_end = sequence_element["end"]
                        actions.append(action)

            anim_data = armature.animation_data_create()
            anim_data.action = None 
            track = anim_data.nla_tracks.get("anim")
            if track is None:
                track = anim_data.nla_tracks.new()
                track.name = "anim"

            strips = []
            for action in actions:
                strip = track.strips.new(name=action.name, start=int(action.frame_start), action=action)
                strips.append(strip)

            if node.get("mesh"):
                mesh_data = import_mesh(data, node["mesh"], material_list)
                armature_mesh = mesh_ob = bpy.data.objects.new("mesh_%s" % node["name"], mesh_data)
                context.collection.objects.link(mesh_ob)

                #mesh_ob.parent = object_mesh

                armature_modifier = mesh_ob.modifiers.new("Armature", type='ARMATURE')
                armature_modifier.object = armature

            keyframe_dict = node.get("key")
            if keyframe_dict is not None:
                import_fcurve_data(armature, strips, object_mesh.name, keyframe_dict, Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(), Vector((1,1,1))), False)

        elif has_bones and armature:
            object_mesh = armature.data.edit_bones.new(node["name"])
            if parent_ob is not None and isinstance(parent_ob, bpy.types.EditBone):
                object_mesh.head = parent_ob.tail
            else:
                object_mesh.head = (0, 0, 0)

            object_mesh.length = avg_length(node)

            node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            if parent_ob is not None :
                if isinstance(parent_ob, bpy.types.EditBone):
                    object_mesh.parent = parent_ob
                    object_mesh.matrix = parent_ob.matrix @ node_transform
                else:
                   object_mesh.matrix = node_transform

            if node.get("mesh"):
                mesh_ob = import_mesh(data, node["mesh"], material_list)
                object_mesh = bpy.data.objects.new("mesh_%s" % node["name"], mesh_ob)
                context.collection.objects.link(object_mesh)

            group_name = object_mesh.name
            if not group_name in armature_mesh.vertex_groups.keys():
                armature_mesh.vertex_groups.new(name = group_name)

            group_index = armature_mesh.vertex_groups.keys().index(group_name)
            for bone_idx, bone_element in enumerate(node["bones"]):
                armature_mesh.vertex_groups[group_index].add([bone_element["vertex_idx"]], bone_element["weight"], 'ADD')

            keyframe_dict = node.get("key")
            if keyframe_dict is not None:
                import_fcurve_data(armature, strips, object_mesh.name, keyframe_dict, node_transform)

        else:
            if result["classname"] == "brush" and node.get("mesh"):
                if data.get("brush_count") is None:
                    data["brush_count"] = 0

                mesh_data = import_mesh(data, node["mesh"], material_list)
                object_mesh = bpy.data.objects.new("brush_%s" % data["brush_count"], mesh_data)
                context.collection.objects.link(object_mesh)

                data["brush_count"] += 1

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

                light_data = bpy.data.lights.new("%s light" % data["light_count"], "POINT")
                object_mesh = bpy.data.objects.new("%s_light" % data["light_count"], light_data)
                context.collection.objects.link(object_mesh)

                light_data.energy = result["intensity"] * 50
                light_data.shadow_soft_size = result["range"] / 1000
                r, g, b = result["color"]
                light_data.color = (r / 255, g / 255, b / 255)

                data["light_count"] += 1

            elif result["classname"] == "spotlight":
                if data.get("spotlight_count") is None:
                    data["spotlight_count"] = 0

                spotlight_data = bpy.data.lights.new("%s spotlight" % data["spotlight_count"], "SPOT")
                object_mesh = bpy.data.objects.new("%s_spotlight" % data["spotlight_count"], spotlight_data)
                context.collection.objects.link(object_mesh)

                spotlight_data.energy = result["intensity"] * 50
                spotlight_data.shadow_soft_size = result["range"] / 1000
                r, g, b = result["color"]
                spotlight_data.color = (r / 255, g / 255, b / 255)

                outer_deg: float = max(1.0, min(180.0, result["outerconeangle"]))
                inner_deg: float = max(1.0, min(180.0, result["innerconeangle"]))
                ratio = inner_deg / outer_deg if outer_deg > 0.0 else 1.0

                spotlight_data.spot_size = radians(outer_deg)
                spotlight_data.spot_blend = max(0.0, min(1.0, 1.0 - ratio))

                data["spotlight_count"] += 1
            else:
                object_mesh = bpy.data.objects.new(result["classname"], None)
                object_mesh.empty_display_size = 0.00625

                context.collection.objects.link(object_mesh)

                if node.get("mesh"):
                    mesh_data = import_mesh(data, node["mesh"], material_list)
                    armature_mesh = mesh_ob = bpy.data.objects.new("mesh_%s" % node["name"], mesh_data)
                    context.collection.objects.link(mesh_ob)

                    mesh_ob.parent = object_mesh

                    armature_modifier = mesh_ob.modifiers.new("Armature", type='ARMATURE')
                    armature_modifier.object = armature

            node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            if parent_ob is not None:
                node_transform = parent_ob.matrix_world @ node_transform
                object_mesh.parent = parent_ob
                
            object_mesh.matrix_world = node_transform

        armature = import_node_recursive(context, data, node["nodes"], material_list, object_mesh, armature, armature_mesh, strips)

    return armature

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
    texture_count = 0
    
    texture_dict = data.get("textures")
    material_dict = data.get("materials")
    if texture_dict is not None:
        texture_count = len(texture_dict)

    if material_dict is not None:
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
                    print()
                    texture_asset = get_file(os.path.basename(texture['name']), True, True, directory_path=local_asset_path)


                    material.use_nodes = True
                    bsdf = material.node_tree.nodes["Principled BSDF"]
                    texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
                    texImage.image = texture_asset
                    if not "_lm" in texture['name']:
                        material.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])

            material_list.append(material)

    import_node_recursive(context, data, data["nodes"], material_list)
    if context.view_layer.objects.active is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
