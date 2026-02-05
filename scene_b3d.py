import os
import bpy
import json

from math import radians
from pathlib import Path
from .process_b3d import B3DTree, write_b3d
from bpy_extras import anim_utils
from enum import Enum, auto, Flag
from collections import defaultdict
from mathutils import Matrix, Vector, Quaternion
from .common_functions import RandomColorGenerator, get_file, is_string_empty, get_material_name, get_linked_node, connect_inputs, get_output_material_node

class TextureFXFlags(Flag):
    color = auto()
    alpha = auto()
    masked = auto()
    mipmapped = auto()
    clamp_u = auto()
    clamp_v = auto()
    spherical_environment_map = auto()
    cubic_environment_map = auto()
    store_texture_in_vram = auto()
    force_high_color_textures = auto()

class TextureBlendEnum(Enum):
    do_not_blend = 0
    no_blend_or_alpha = auto()
    multiply = auto()
    add = auto()
    dot3 = auto()
    multiply2 = auto()
    
class MaterialFXFlags(Flag):
    full_bright = auto()
    use_vertex_colors_instead_of_brush_color = auto()
    flatshaded = auto()
    disable_fog = auto()
    disable_backface_culling = auto()

class MaterialBlendEnum(Enum):
    alpha = 0
    multiply = auto()
    add = auto()

def flip(v):
    return ((v[0],v[2],v[1]) if len(v)<4 else (v[0], v[1],v[3],v[2]))

def import_mesh(node, material_list):
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
    last_scale = Vector((1, 1, 1))
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
                    fcurve_data_path = path
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

def get_bone_distance(node, parent_ob):
    child_nodes = node["nodes"]
    child_node_count = len(child_nodes)
    bone_distance = 0
    if child_node_count == 0 and parent_ob:
        if isinstance(parent_ob, bpy.types.EditBone):
            bone_distance = parent_ob.length
        else:
            bone_distance = parent_ob.location.length

    elif child_node_count == 1:
        child_position = Vector(child_nodes[0]["position"])
        position = Vector(node["position"])

        bone_distance = (Matrix.Scale(0.00625, 4) @ (position - child_position)).length

    elif child_node_count > 1:
        positions = []
        for child_node in child_nodes:
            positions.append(Vector(child_node["position"]))

        average_position = (sum(positions, Vector()) / len(positions))
        position = Vector(node["position"])
        bone_distance = (Matrix.Scale(0.00625, 4) @ (position - average_position)).length

    if bone_distance < 0.000001:
        bone_distance = 0.00625

    return bone_distance

def import_node_recursive(context, data, nodes, material_list, armature, parent_ob=None, last_mesh=None, strips=None):
    for node in nodes:
        has_skin = node.get("bones") is not None
        has_key = node.get("key") is not None
        has_mesh = node.get("mesh") is not None
        generated_mesh = False
                           
        result = parse_kv_string(node["name"])
        if has_skin or has_key or armature:
            if armature is None:
                armature_data = bpy.data.armatures.new(node["name"])
                armature = object_mesh =  bpy.data.objects.new(node["name"], armature_data)
                context.collection.objects.link(armature)

                context.view_layer.objects.active = armature

                node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
                if parent_ob is not None:
                    armature.parent = parent_ob
            
                armature.matrix_local = node_transform

                if last_mesh:
                    armature_modifier = last_mesh.modifiers.new("Armature", type='ARMATURE')
                    armature_modifier.object = armature
                    last_mesh.parent = armature
                    last_mesh.matrix_parent_inverse = node_transform.inverted()

                for child_node in data["nodes"]:
                    child_has_anim = child_node.get("anim") is not None
                    child_has_sequence = child_node.get("sequences") is not None
                    if child_has_sequence:
                        anim_data = armature.animation_data_create()
                        anim_data.action = None 
                        track = anim_data.nla_tracks.new()
                        track.name = "anim"

                        sequences_dict = child_node["sequences"]
                        for sequence_element in sequences_dict:
                            action = bpy.data.actions.new(name=sequence_element["name"])
                            action.use_frame_range = True
                            action.frame_start = sequence_element["start"]
                            action.frame_end = sequence_element["end"]

                            strip = track.strips.new(name=action.name, start=int(action.frame_start), action=action)
                            strips.append(strip)

                    elif child_has_anim:
                        anim_dict = node["anim"]
                        context.scene.frame_end = anim_dict["frames"]

                        anim_data = armature.animation_data_create()
                        anim_data.action = None 
                        track = anim_data.nla_tracks.new()
                        track.name = "anim"

                        action = bpy.data.actions.new(name="Animation")
                        action.use_frame_range = True
                        action.frame_start = 1
                        action.frame_end = child_node["anim"]["frames"]

                        strip = track.strips.new(name=action.name, start=int(action.frame_start), action=action)
                        strips.append(strip)
                    break

                bpy.ops.object.mode_set(mode='EDIT')

            else:
                object_mesh = armature.data.edit_bones.new(node["name"])
                object_mesh.length = 0.00625

                node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
                if parent_ob is not None:
                    if isinstance(parent_ob, bpy.types.EditBone):
                        object_mesh.parent = parent_ob
                        object_mesh.matrix = parent_ob.matrix @ node_transform
                    else:
                        loc, rot, scl = armature.matrix_world.inverted().decompose()
                        object_mesh.matrix = Matrix.Translation(loc) @ node_transform

                object_mesh.length = get_bone_distance(node, parent_ob)

        else:
            if result["classname"] == "brush" and node.get("mesh"):
                generated_mesh = True
                if data.get("brush_count") is None:
                    data["brush_count"] = 0

                mesh_data = import_mesh(node["mesh"], material_list)
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
                if not generated_mesh and has_mesh:
                    generated_mesh = True
                    mesh_data = import_mesh(node["mesh"], material_list)
                    last_mesh = object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                    context.collection.objects.link(last_mesh)

                else:
                    object_mesh = bpy.data.objects.new(result["classname"], None)
                    object_mesh.empty_display_size = 0.00625

                    context.collection.objects.link(object_mesh)

            node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            if parent_ob is not None:
                object_mesh.parent = parent_ob
        
            object_mesh.matrix_local = node_transform

        if not generated_mesh and has_mesh:
            generated_mesh = True
            mesh_data = import_mesh(node["mesh"], material_list)
            last_mesh = bpy.data.objects.new(node["name"], mesh_data)
            context.collection.objects.link(last_mesh)

            if armature:
                last_mesh.parent = armature
                armature_modifier = last_mesh.modifiers.new("Armature", type='ARMATURE')
                armature_modifier.object = armature
            elif parent_ob:
                last_mesh.parent = parent_ob

        if has_skin:
            group_name = object_mesh.name
            if not group_name in last_mesh.vertex_groups.keys():
                last_mesh.vertex_groups.new(name = group_name)

            group_index = last_mesh.vertex_groups.keys().index(group_name)
            for bone_element in node["bones"]:
                last_mesh.vertex_groups[group_index].add([bone_element["vertex_idx"]], bone_element["weight"], 'ADD')

        if has_key and has_skin:
            import_fcurve_data(armature, strips, object_mesh.name, node["key"], node_transform, has_skin)

        import_node_recursive(context, data, node["nodes"], material_list, armature, object_mesh, last_mesh, strips)

def get_scene_objects(b3d_data, node_dict, parent_ob, depsgraph):
    for ob in bpy.data.objects:
        if ob.parent == parent_ob:
            transform_matrix = ob.matrix_world
            if parent_ob is not None:
                transform_matrix = parent_ob.matrix_world.inverted() @ ob.matrix_world
            loc, rot_quat, scl = transform_matrix.decompose()

            tx, ty, tz = Matrix.Scale(160, 4) @ loc
            sx, sy, sz = scl
            rw, ri, rj, rk = rot_quat
            ob_node_dict = {
                "name": ob.name,
                "position": [
                    tx,
                    tz,
                    ty
                ],
                "scale": [
                    sx,
                    sz,
                    sy
                ],
                "rotation": [
                    rw,
                    ri,
                    rk,
                    rj
                ],
                "nodes": []
            }

            if ob.type == "MESH":
                ob_eval = ob.evaluated_get(depsgraph)
                mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
                mesh.calc_loop_triangles()

                layer_uv_0 = mesh.uv_layers.get("uvmap_render")
                layer_uv_1 = mesh.uv_layers.get("uvmap_lightmap")
                layer_color = mesh.color_attributes.get("color")

                ob_node_dict["mesh"] = {
                    "brush_id": -1,
                    "vertices": [],
                    "normals": [],
                    "rgba": [],
                    "uvs": [],
                    "faces": []
                }

                material_map = {}
                vertex_map = {}
                for tri in mesh.loop_triangles:
                    mat_name = get_material_name(ob, tri)
                    material_dict_idx = -1
                    for mat_idx, material_dict in enumerate(b3d_data["materials"]):
                        if mat_name == material_dict["name"]:
                            material_dict_idx = mat_idx
                            break

                    if material_dict_idx == -1:
                        r = g = b = a = 1.0

                        scene_mat = bpy.data.materials[mat_name]
                        output_material_node = get_output_material_node(scene_mat)
                        bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
                        image_node_a = get_linked_node(bdsf_principled, "Base Color", "TEX_IMAGE")

                        texture_dict_idx = -1 
                        img = image_node_a.image
                        if img and img.source == 'FILE' and img.filepath:
                            image_name = img.name
                            for tex_idx, texture_dict in enumerate(b3d_data["textures"]):
                                if image_name == texture_dict["name"]:
                                    texture_dict_idx = tex_idx

                            if texture_dict_idx == -1:
                                texture_dict = {
                                    "name": img.name,
                                    "flags": 0,
                                    "blend": 0,
                                    "position": [
                                        0.0,
                                        0.0
                                    ],
                                    "scale": [
                                        1.0,
                                        1.0
                                    ],
                                    "rotation": 0.0
                                }

                                get_image_properties(img, texture_dict)
                                b3d_data["textures"].append(texture_dict)
                                texture_dict_idx = len(b3d_data["textures"]) - 1


                        if bdsf_principled:
                            r, g, b, a = bdsf_principled.inputs["Base Color"].default_value
                            a = bdsf_principled.inputs["Alpha"].default_value

                        material_dict = {
                            "name": mat_name,
                            "rgba": [
                                r,
                                g,
                                b,
                                a
                            ],
                            "shine": 0.0,
                            "blend": MaterialBlendEnum.multiply.value,
                            "fx": MaterialFXFlags.full_bright.value + MaterialFXFlags.use_vertex_colors_instead_of_brush_color.value,
                            "tids": []
                        }

                        material_dict["tids"].append(texture_dict_idx)
                        
                        get_material_properties(scene_mat, material_dict)
                        b3d_data["materials"].append(material_dict)
                        material_dict_idx = len(b3d_data["materials"]) - 1

                        material_map[mat_name] = {"brush_id": material_dict_idx, "indices": []}

                    tri_indices = []
                    for loop_index in tri.loops:
                        loop = mesh.loops[loop_index]
                        v = mesh.vertices[loop.vertex_index]
                        x, y, z = Matrix.Scale(160.0, 4) @ v.co
                        i, j, k = loop.normal
                        pos = (x, z, y)
                        loop_normal = (i, k, j)

                        uv_render = (0.0, 0.0)
                        uv_lightmap = (0.0, 0.0)
                        if layer_uv_0:
                            u0, v0 = layer_uv_0.data[loop_index].uv
                            uv_render = (u0, 1 - v0)

                        if layer_uv_1:
                            u1, v1 = layer_uv_1.data[loop_index].uv
                            uv_lightmap = (u1, 1 - v1)

                        color = (0, 0, 0, 0)
                        if layer_color:
                            r, g, b, a = layer_color.data[loop_index].color
                            color = (r, g, b, a)

                        key = (round(pos[0], 6), round(pos[1], 6), round(pos[2], 6), uv_render, uv_lightmap, color, loop_normal)
                        if key not in vertex_map:
                            vertex_map[key] = len(ob_node_dict["mesh"]["vertices"])
                            ob_node_dict["mesh"]["vertices"].append(pos)
                            ob_node_dict["mesh"]["uvs"].append((*uv_render, *uv_lightmap))
                            ob_node_dict["mesh"]["normals"].append(loop_normal)
                            ob_node_dict["mesh"]["rgba"].append(color)
    
                        tri_indices.append(vertex_map[key])

                    material_map[mat_name]["indices"].append(tri_indices[::-1])

                for mat_key in material_map.keys():
                    ob_node_dict["mesh"]["faces"].append(material_map[mat_key])

            get_scene_objects(b3d_data, ob_node_dict["nodes"], ob, depsgraph)

            node_dict.append(ob_node_dict)

def set_image_properties(img, texture_dict):
    img_b3d = img.b3d

    tex_flags = TextureFXFlags(texture_dict["flags"])

    if TextureFXFlags.color in tex_flags:
        img_b3d.color = True
    if TextureFXFlags.alpha in tex_flags:
        img_b3d.alpha = True
    if TextureFXFlags.masked in tex_flags:
        img_b3d.masked = True
    if TextureFXFlags.mipmapped in tex_flags:
        img_b3d.mipmapped = True
    if TextureFXFlags.clamp_u in tex_flags:
        img_b3d.clamp_u = True
    if TextureFXFlags.clamp_v in tex_flags:
        img_b3d.clamp_v = True
    if TextureFXFlags.spherical_environment_map in tex_flags:
        img_b3d.spherical_environment_map = True
    if TextureFXFlags.cubic_environment_map in tex_flags:
        img_b3d.cubic_environment_map = True
    if TextureFXFlags.store_texture_in_vram in tex_flags:
        img_b3d.store_texture_in_vram = True
    if TextureFXFlags.force_high_color_textures in tex_flags:
        img_b3d.force_high_color_textures = True

    img_b3d.blend_type = str(texture_dict["blend"])

def set_material_properties(mat, material_dict):
    mat_b3d = mat.b3d

    mat_flags = MaterialFXFlags(material_dict["fx"])

    if MaterialFXFlags.full_bright in mat_flags:
        mat_b3d.full_bright = True
    if MaterialFXFlags.use_vertex_colors_instead_of_brush_color in mat_flags:
        mat_b3d.use_vertex_colors_instead_of_brush_color = True
    if MaterialFXFlags.flatshaded in mat_flags:
        mat_b3d.flatshaded = True
    if MaterialFXFlags.disable_fog in mat_flags:
        mat_b3d.disable_fog = True
    if MaterialFXFlags.disable_backface_culling in mat_flags:
        mat_b3d.disable_backface_culling = True

    mat_b3d.blend_type = str(material_dict["blend"])

def get_image_properties(img, texture_dict):
    img_b3d = img.b3d

    tex_flags = 0
    if img_b3d.color:
        tex_flags += TextureFXFlags.color.value
    if img_b3d.alpha:
        tex_flags += TextureFXFlags.alpha.value
    if img_b3d.masked:
        tex_flags += TextureFXFlags.masked.value
    if img_b3d.mipmapped:
        tex_flags += TextureFXFlags.mipmapped.value
    if img_b3d.clamp_u:
        tex_flags += TextureFXFlags.clamp_u.value
    if img_b3d.clamp_v:
        tex_flags += TextureFXFlags.clamp_v.value
    if img_b3d.spherical_environment_map:
        tex_flags += TextureFXFlags.spherical_environment_map.value
    if img_b3d.cubic_environment_map:
        tex_flags += TextureFXFlags.cubic_environment_map.value
    if img_b3d.store_texture_in_vram:
        tex_flags += TextureFXFlags.store_texture_in_vram.value
    if img_b3d.force_high_color_textures:
        tex_flags += TextureFXFlags.force_high_color_textures.value

    texture_dict["flags"] = tex_flags
    texture_dict["blend"] = int(img_b3d.blend_type)

def get_material_properties(mat, material_dict):
    mat_b3d = mat.b3d

    mat_flags = 0
    if mat_b3d.full_bright:
        mat_flags += MaterialFXFlags.full_bright.value
    if mat_b3d.use_vertex_colors_instead_of_brush_color:
        mat_flags += MaterialFXFlags.use_vertex_colors_instead_of_brush_color.value
    if mat_b3d.flatshaded:
        mat_flags += MaterialFXFlags.flatshaded.value
    if mat_b3d.disable_fog:
        mat_flags += MaterialFXFlags.disable_fog.value
    if mat_b3d.disable_backface_culling:
        mat_flags += MaterialFXFlags.disable_backface_culling.value

    material_dict["fx"] = mat_flags
    material_dict["blend"] = int(mat_b3d.blend_type)

def export_scene(context, filepath, report):
    if context.view_layer.objects.active is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    depsgraph = context.evaluated_depsgraph_get()

    b3d_data = {"nodes": [], "textures": [], "materials": []}

    get_scene_objects(b3d_data, b3d_data["nodes"], None, depsgraph)

    write_b3d(filepath, b3d_data)

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

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

            set_material_properties(material, material_dict)

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
                    set_image_properties(texture_asset, texture)

                    material.use_nodes = True
                    bsdf = material.node_tree.nodes["Principled BSDF"]
                    texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
                    texImage.image = texture_asset
                    if not "_lm" in texture['name']:
                        material.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])

            material_list.append(material)

    strips = []
    armature_ob = None

    import_node_recursive(context, data, data["nodes"], material_list, armature_ob, strips=strips)
    if context.view_layer.objects.active is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
