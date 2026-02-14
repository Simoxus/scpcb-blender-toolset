import os
import bpy

from . import ObjectType
from pathlib import Path
from math import radians, degrees
from bpy_extras import anim_utils
from enum import Enum, auto, Flag
from collections import defaultdict
from .process_b3d import B3DTree, write_b3d
from mathutils import Matrix, Vector, Quaternion, Euler
from .common_functions import (RandomColorGenerator, 
                               get_file, 
                               is_string_empty, 
                               get_material_name, 
                               get_linked_node, 
                               get_output_material_node, 
                               flip, 
                               get_shader_node, 
                               connect_inputs, 
                               generate_texture_mapping,
                               SHADER_RESOURCES)

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
    unk5 = auto()

class MaterialBlendEnum(Enum):
    alpha = 0
    multiply = auto()
    add = auto()

class TextureTypeEnum(Enum):
    lightmap = 0
    diffuse = auto()
    specular = auto()

def import_mesh(node, material_list, is_simple=False, ob_data=None):
    loop_normals = []

    m_scl = Matrix.Scale(0.00625, 4)

    vertices = [m_scl @ Vector(flip(vertex)) for vertex in node["vertices"]]
    faces = [face[::-1] for brush in node["faces"] for face in brush["indices"]]
    mesh = bpy.data.meshes.new("mesh")
    mesh.from_pydata(vertices, [], faces)

    # This is for some reason fixing a crash I get when I set custom normals. - Gen
    mesh.validate(clean_customdata=True)

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
                    if is_simple:
                        ob_data.materials.append(brush_mat)

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
                loop_normals.append(flip(node["normals"][vert_index]))

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

        section_found = False
        for keyframe_section in keyframe_dict:
            for frame_data in keyframe_section:
                frame_number = frame_data["frame"]
                if action.frame_start <= frame_number <= action.frame_end:
                    section_found = True
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

        if not section_found:
            frame_number = action.frame_start
            if is_bone:
                transform_matrix = Matrix.LocRotScale(last_position, last_rotation, last_scale)
            else:
                transform_matrix = node_transform

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

def import_node_recursive(context, data, node, material_list, armature=None, strips=None, has_skeleton=False, parent_ob=None, last_mesh=None, is_simple=False, bm=None, ob_data=None, bm_transform=None):
    has_skin = bool(node.get("bones"))
    has_key = node.get("key") is not None
    has_mesh = node.get("mesh") is not None
    generated_mesh = False
                        
    result = parse_kv_string(node["name"])
    if is_simple:
        if has_mesh:
            node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            if bm_transform is not None:
                bm_transform = bm_transform @ node_transform
            else:
                bm_transform = node_transform

            mesh_data = import_mesh(node["mesh"], material_list, is_simple, ob_data)
            mesh_data.transform(bm_transform)
            bm.from_mesh(mesh_data)
            bpy.data.meshes.remove(mesh_data)

        for child_node in node["nodes"]:
            import_node_recursive(context, data, child_node, material_list, is_simple=is_simple, bm=bm, ob_data=ob_data, bm_transform=bm_transform)

    else:
        if has_skin or has_key or armature:
            if armature is None:
                armature_data = bpy.data.armatures.new(result["classname"])
                armature = object_mesh =  bpy.data.objects.new(result["classname"], armature_data)
                context.collection.objects.link(armature)

                context.view_layer.objects.active = armature

                armature.cb.object_type = str(ObjectType.node_object.value)

                node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
                if parent_ob is not None:
                    armature.parent = parent_ob
            
                armature.matrix_local = node_transform

                if last_mesh:
                    bpy.context.view_layer.update()
                    armature_modifier = last_mesh.modifiers.new("Armature", type='ARMATURE')
                    armature_modifier.object = armature
                    last_mesh.parent = armature
                    last_mesh.matrix_parent_inverse = armature.matrix_world.inverted()

                for child_node in data["nodes"]:
                    child_has_anim = child_node.get("anim") is not None
                    child_has_sequence = child_node.get("sequences") is not None
                    if child_has_sequence:
                        anim_dict = child_node["anim"]
                        context.scene.frame_end = anim_dict["frames"]

                        anim_data = armature.animation_data_create()
                        anim_data.action = None 
                        track = anim_data.nla_tracks.new()
                        track.name = armature.name

                        sequences_dict = child_node["sequences"]
                        for sequence_element in sequences_dict:
                            action = bpy.data.actions.new(name="%s_%s" % (armature.name, sequence_element["name"]))
                            action.use_frame_range = True
                            action.frame_start = sequence_element["start"]
                            action.frame_end = sequence_element["end"]

                            strip = track.strips.new(name=action.name, start=int(action.frame_start), action=action)
                            strips.append(strip)

                    elif child_has_anim:
                        anim_dict = child_node["anim"]
                        context.scene.frame_end = anim_dict["frames"]

                        anim_data = armature.animation_data_create()
                        anim_data.action = None 
                        track = anim_data.nla_tracks.new()
                        track.name = armature.name

                        action = bpy.data.actions.new(name="%s_animation" % armature.name)
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
                        object_mesh.matrix = node_transform

                object_mesh.length = get_bone_distance(node, parent_ob)

        else:
            if result["classname"].lower().startswith("brush"):
                generated_mesh = True
                
                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.node_brush.value)

            elif result["classname"].lower().startswith("terrainsector"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.node_terrainsector.value)

            elif result["classname"].lower().startswith("terrain"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.node_terrain.value)

            elif result["classname"].lower().startswith("mesh"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.node_mesh.value)

            elif result["classname"].lower().startswith("field_hit"):
                generated_mesh = True

                mesh_data = None
                if node.get("mesh"):
                    mesh_data = import_mesh(node["mesh"], material_list)

                object_mesh = bpy.data.objects.new(result["classname"], mesh_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.node_field_hit.value)

            elif result["classname"] == "light":
                light_data = bpy.data.lights.new(result["classname"], "POINT")
                object_mesh = bpy.data.objects.new(result["classname"], light_data)
                context.collection.objects.link(object_mesh)

                light_data.energy = result["intensity"] * 50
                light_data.shadow_soft_size = result["range"] / 1000
                r, g, b = result["color"]
                light_data.color = (r / 255, g / 255, b / 255)
                object_mesh.cb.linear_falloff = result["linearfalloff"]

                object_mesh.cb.object_type = str(ObjectType.node_light.value)

            elif result["classname"] == "spotlight":
                spotlight_data = bpy.data.lights.new(result["classname"], "SPOT")
                object_mesh = bpy.data.objects.new(result["classname"], spotlight_data)
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

                object_mesh.cb.linear_falloff = result["linearfalloff"]

                object_mesh.cb.object_type = str(ObjectType.node_spotlight.value)

            elif result["classname"] == "sunlight":
                sunlight_data = bpy.data.lights.new(result["classname"], "SUN")
                object_mesh = bpy.data.objects.new(result["classname"], sunlight_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.node_sunlight.value)

            elif result["classname"].startswith("soundemitter"):
                speaker_data = bpy.data.speakers.new(result["classname"])
                object_mesh = bpy.data.objects.new(result["classname"], speaker_data)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.sound_emitter_id = result["sound"]
                object_mesh.data.distance_max = result["range"]

                object_mesh.cb.object_type = str(ObjectType.node_soundemitter.value)

            elif result["classname"].startswith("waypoint"):
                object_mesh = bpy.data.objects.new(result["classname"], None)
                context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.node_waypoint.value)

            else:
                if not generated_mesh and has_mesh and not has_skeleton:
                    generated_mesh = True
                    mesh_data = import_mesh(node["mesh"], material_list)
                    object_mesh = bpy.data.objects.new(node["name"], mesh_data)
                    context.collection.objects.link(object_mesh)
                else:
                    object_mesh = bpy.data.objects.new(result["classname"], None)
                    object_mesh.empty_display_size = 0.00625

                    context.collection.objects.link(object_mesh)

                object_mesh.cb.object_type = str(ObjectType.node_object.value)

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
            
            last_mesh.cb.object_type = str(ObjectType.node_object.value)

            node_transform = Matrix.LocRotScale(Matrix.Scale(0.00625, 4) @ Vector(flip(node["position"])), Quaternion(flip(node["rotation"])), Vector(flip(node["scale"])))
            last_mesh.matrix_local = node_transform

        if has_skin and len(node["bones"]) > 0:
            group_name = object_mesh.name
            if not group_name in last_mesh.vertex_groups.keys():
                last_mesh.vertex_groups.new(name = group_name)

            group_index = last_mesh.vertex_groups.keys().index(group_name)
            for bone_element in node["bones"]:
                last_mesh.vertex_groups[group_index].add([bone_element["vertex_idx"]], bone_element["weight"], 'ADD')

        if has_key:
            import_fcurve_data(armature, strips, object_mesh.name, node["key"], node_transform, isinstance(object_mesh, bpy.types.EditBone))

        for child_node in node["nodes"]:
            import_node_recursive(context, data, child_node, material_list, armature, strips, has_skeleton, object_mesh, last_mesh)

def get_mesh(b3d_data, ob, depsgraph, armature_ob=None):
    ob_eval = ob.evaluated_get(depsgraph)
    mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.calc_loop_triangles()

    uv_layer_count = len(mesh.uv_layers)
    color_layer_count = len(mesh.color_attributes)
    layer_uv_0 = mesh.uv_layers.get("uvmap_render")
    layer_uv_1 = mesh.uv_layers.get("uvmap_lightmap")
    layer_color = mesh.color_attributes.get("color")
    if uv_layer_count > 0 and not layer_uv_0:
        layer_uv_0 = mesh.uv_layers[0]
    if uv_layer_count > 1 and not layer_uv_1:
        layer_uv_1 = mesh.uv_layers[1]
    if color_layer_count > 0 and not layer_color:
        layer_color = mesh.color_attributes[0]

    mesh_dict = {
        "brush_id": -1,
        "vertices": [],
        "normals": [],
        "rgba": [],
        "uvs": [],
        "faces": []
    }

    vertex_group_count = len(ob.vertex_groups)
    skin_info = {}
    material_map = {}
    vertex_map = {}
    for tri in mesh.loop_triangles:
        mat_name = get_material_name(ob, tri)
        material_dict_idx = -1
        for mat_idx, b3d_material_dict in enumerate(b3d_data["materials"]):
            if mat_name == b3d_material_dict["name"]:
                material_dict_idx = mat_idx
                break

        if material_dict_idx == -1:
            texture_id_list = []
            r = g = b = a = 1.0

            scene_mat = bpy.data.materials[mat_name]
            output_material_node = get_output_material_node(scene_mat)
            bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
            node_group = get_linked_node(output_material_node, "Surface", "GROUP")
            if node_group and node_group.node_tree.name == "b3d_material":
                lightmap_node = get_linked_node(node_group, "Light Map", "TEX_IMAGE")
                diffuse_node = get_linked_node(node_group, "Diffuse Map", "TEX_IMAGE")
                specular_node = get_linked_node(node_group, "Specular Map", "TEX_IMAGE")
                texture_entries = [lightmap_node, diffuse_node, specular_node]
                for texture_entry_idx, texture_entry in enumerate(texture_entries):
                    texture_dict_idx = -1 
                    if not texture_entry:
                        # Limiting it to 2 because honestly I think the max inputs on this game is 2. Everything else is derived from the diffuse name
                        # Check goes away during rigged exports to allow SCP 1048a to export with its third texture id that I'm pretty sure does nothing - Gen
                        if armature_ob is None and texture_entry_idx < 2:
                            texture_id_list.append(texture_dict_idx)
                        continue

                    texture_type_val = 0
                    if texture_entry_idx == 0:
                        texture_type_val = 1

                    mapping_node = get_linked_node(texture_entry, "Vector", "MAPPING")
                    tx = ty = tz = 0.0
                    sx = sy = sz = 1.0
                    rx = ry = rz = 0.0
                    if mapping_node is not None:
                        tx, ty, tz = mapping_node.inputs["Location"].default_value
                        sx, sy, sz = mapping_node.inputs["Scale"].default_value
                        rx, ry, rz = mapping_node.inputs["Rotation"].default_value

                    img = texture_entry.image
                    if img and img.source == 'FILE' and img.filepath:
                        image_name = img.name
                        for tex_idx, texture_dict in enumerate(b3d_data["textures"]):
                            txd, tyd = texture_dict["position"]
                            sxd, syd = texture_dict["scale"]
                            rxd = texture_dict["rotation"]

                            if image_name != texture_dict["name"]:
                                continue
                            if (tx, ty) != (txd, tyd):
                                continue
                            if (sx, sy) != (sxd, syd):
                                continue
                            if degrees(rx) != rxd:
                                continue

                            texture_dict_idx = tex_idx

                    if texture_dict_idx == -1:
                        fx = 0
                        if img.cb.color:
                            fx += TextureFXFlags.color.value
                        if img.cb.alpha:
                            fx += TextureFXFlags.alpha.value
                        if img.cb.masked:
                            fx += TextureFXFlags.masked.value
                        if img.cb.mipmapped:
                            fx += TextureFXFlags.mipmapped.value
                        if img.cb.clamp_u:
                            fx += TextureFXFlags.clamp_u.value
                        if img.cb.clamp_v:
                            fx += TextureFXFlags.clamp_v.value
                        if img.cb.spherical_environment_map:
                            fx += TextureFXFlags.spherical_environment_map.value
                        if img.cb.cubic_environment_map:
                            fx += TextureFXFlags.cubic_environment_map.value
                        if img.cb.store_texture_in_vram:
                            fx += TextureFXFlags.store_texture_in_vram.value
                        if img.cb.force_high_color_textures:
                            fx += TextureFXFlags.force_high_color_textures.value

                        texture_dict = {
                            "name": img.name,
                            "flags": fx,
                            "texture_type": texture_type_val,
                            "blend": img.cb.blend_type,
                            "position": [tx, ty],
                            "scale": [sx, sy],
                            "rotation": degrees(rx)
                        }

                        get_image_properties(img, texture_dict)
                        b3d_data["textures"].append(texture_dict)
                        texture_id = len(b3d_data["textures"]) - 1
                        texture_dict_idx = texture_id

                    r, g, b, a = node_group.inputs["Diffuse Overlay"].default_value
                    material_shine = node_group.inputs["Shine"].default_value
                    blend_type = node_group.inputs["Blend Type"].default_value
                    fx = 0
                    if node_group.inputs["Full Bright"].default_value:
                        fx += MaterialFXFlags.full_bright.value
                    if node_group.inputs["Use Vertex Colors Instead Of Brush Color"].default_value:
                        fx += MaterialFXFlags.use_vertex_colors_instead_of_brush_color.value
                    if node_group.inputs["Flat Shaded"].default_value:
                        fx += MaterialFXFlags.flatshaded.value
                    if node_group.inputs["Disable Fog"].default_value:
                        fx += MaterialFXFlags.disable_fog.value
                    if node_group.inputs["Disable Backface Culling"].default_value:
                        fx += MaterialFXFlags.disable_backface_culling.value
                    if node_group.inputs["Unknown 5"].default_value:
                        fx += MaterialFXFlags.unk5.value
                    
                    texture_id_list.append(texture_dict_idx)

            elif bdsf_principled:
                diffuse_node = get_linked_node(bdsf_principled, "Base Color", "TEX_IMAGE")

                texture_dict_idx = -1 
                if diffuse_node is not None:
                    img = diffuse_node.image
                    if img and img.source == 'FILE' and img.filepath:
                        image_name = img.name
                        for tex_idx, texture_dict in enumerate(b3d_data["textures"]):
                            if image_name == texture_dict["name"]:
                                texture_dict_idx = tex_idx

                        if texture_dict_idx == -1:
                            fx = 0
                            if img.cb.color:
                                fx += TextureFXFlags.color.value
                            if img.cb.alpha:
                                fx += TextureFXFlags.alpha.value
                            if img.cb.masked:
                                fx += TextureFXFlags.masked.value
                            if img.cb.mipmapped:
                                fx += TextureFXFlags.mipmapped.value
                            if img.cb.clamp_u:
                                fx += TextureFXFlags.clamp_u.value
                            if img.cb.clamp_v:
                                fx += TextureFXFlags.clamp_v.value
                            if img.cb.spherical_environment_map:
                                fx += TextureFXFlags.spherical_environment_map.value
                            if img.cb.cubic_environment_map:
                                fx += TextureFXFlags.cubic_environment_map.value
                            if img.cb.store_texture_in_vram:
                                fx += TextureFXFlags.store_texture_in_vram.value
                            if img.cb.force_high_color_textures:
                                fx += TextureFXFlags.force_high_color_textures.value

                            texture_dict = {
                                "name": img.name,
                                "flags": fx,
                                "blend": img.cb.blend_type,
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

                    r, g, b, a = bdsf_principled.inputs["Base Color"].default_value
                    a = bdsf_principled.inputs["Alpha"].default_value
                    material_shine = 0.0
                    blend_type = 0
                    fx = 0

                texture_id_list.append(texture_dict_idx)

            material_dict = {
                "name": mat_name,
                "rgba": [
                    r,
                    g,
                    b,
                    a
                ],
                "shine": material_shine,
                "blend": blend_type,
                "fx": fx,
                "tids": []
            }

            material_dict["tids"] = texture_id_list
            b3d_data["materials"].append(material_dict)
            material_dict_idx = len(b3d_data["materials"]) - 1

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

            v_skins = set()
            for vertex_group in v.groups:
                group_index = vertex_group.group
                weight = vertex_group.weight
                v_skins.add((group_index, weight))

            key = (round(pos[0], 6), round(pos[1], 6), round(pos[2], 6), uv_render, uv_lightmap, color, loop_normal)
            if key not in vertex_map:
                vertex_map_index = len(mesh_dict["vertices"])
                vertex_map[key] = vertex_map_index
                mesh_dict["vertices"].append(pos)
                mesh_dict["uvs"].append((*uv_render, *uv_lightmap))
                mesh_dict["normals"].append(loop_normal)
                mesh_dict["rgba"].append(color)
                for vertex_group in v.groups:
                    group_index = vertex_group.group
                    weight = vertex_group.weight
                    if vertex_group_count > group_index:
                            group_name = ob.vertex_groups[group_index].name
                            skin_group = skin_info.get(group_name)
                            if skin_group is None:
                                skin_group = skin_info[group_name] = []

                            skin_group.append({"vertex_idx": vertex_map_index, "weight": weight})

            tri_indices.append(vertex_map[key])

        material_section = material_map.get(mat_name)
        if material_section is None:
            material_section = material_map[mat_name] = {"brush_id": material_dict_idx, "indices": []}

        material_section["indices"].append(tri_indices[::-1])

    for mat_key in material_map.keys():
        mesh_dict["faces"].append(material_map[mat_key])

    ob_eval.to_mesh_clear()

    return skin_info, mesh_dict

def get_scene_bones(b3d_data, node_dict, depsgraph, skin_info=None, key_info=None, armature=None, parent_ob=None):
    for bone in armature.data.bones:
        if bone.parent == parent_ob:
            node_transform = bone.matrix_local
            if parent_ob is not None:
                node_transform = parent_ob.matrix_local.inverted() @ bone.matrix_local
            loc, rot_quat, scl = node_transform.decompose()

            tx, ty, tz = Matrix.Scale(160, 4) @ loc
            sx, sy, sz = scl
            rw, ri, rj, rk = rot_quat
            ob_node_dict = {
                "name": bone.name,
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

            ob_node_dict["bones"] = []
            if skin_info is not None:
                skin_keys = skin_info.keys()
                for skin_key in skin_keys:
                    if bone.name == skin_key:
                        ob_node_dict["bones"] = skin_info[skin_key]

            key_data = key_info.get(bone.name)
            if key_data is not None:
                ob_node_dict["key"] = []
                for action_group in key_data:
                    action_entry = []
                    for frame_data in action_group:
                        frame_index, frame_transform = frame_data

                        node_transform = bone.matrix_local @ frame_transform
                        if parent_ob is not None:
                            node_transform = parent_ob.matrix_local.inverted() @ (bone.matrix_local @ frame_transform)

                        f_loc, f_rot_quat, f_scl = node_transform.decompose()

                        f_tx, f_ty, f_tz = Matrix.Scale(160, 4) @ f_loc
                        f_sx, f_sy, f_sz = f_scl
                        f_rw, f_ri, f_rj, f_rk = f_rot_quat

                        key_dict = {
                            "frame": frame_index,
                            "position": [
                                f_tx,
                                f_tz,
                                f_ty
                            ],
                            "scale": [
                                f_sx,
                                f_sz,
                                f_sy
                            ],
                            "rotation": [
                                f_rw,
                                f_ri,
                                f_rk,
                                f_rj
                            ],
                        }
                        action_entry.append(key_dict)

                    ob_node_dict["key"].append(action_entry)


            get_scene_bones(b3d_data, ob_node_dict["nodes"], depsgraph, skin_info, key_info, armature, bone)

            node_dict.append(ob_node_dict)

def get_node_name(ob):
    node_name = ob.name
    object_type_enum = ObjectType(int(ob.cb.object_type))
    if object_type_enum == ObjectType.node_brush:
        node_name = "classname=brush"
    elif object_type_enum == ObjectType.node_terrainsector:
        node_name = "classname=terrainsector"
    elif object_type_enum == ObjectType.node_terrain:
        node_name = "classname=terrain"
    elif object_type_enum == ObjectType.node_mesh:
        node_name = "classname=mesh"
    elif object_type_enum == ObjectType.node_field_hit:
        node_name = "classname=field_hit"
    elif object_type_enum == ObjectType.node_light:
        r, g, b = ob.data.color

        light_color = "color=%s %s %s" % (int(r * 255), int(g * 255), int(b * 255))
        light_intensity = "intensity=%s" % (ob.data.energy / 50)
        light_range = "range=%s" % int(ob.data.shadow_soft_size * 1000)
        light_linear_falloff = "linearfalloff=%s" % int(ob.cb.linear_falloff)
        node_name = "classname=light\r\n%s\r\n%s\r\n%s\r\n%s" % (light_color, light_intensity, light_range, light_linear_falloff)
    elif object_type_enum == ObjectType.node_spotlight:
        r, g, b = ob.data.color
        outer_deg = degrees(ob.data.spot_size)

        light_angles = "angles=%s %s %s" % (0, 0, 0)
        light_color = "color=%s %s %s" % (int(r * 255), int(g * 255), int(b * 255))
        light_intensity = "intensity=%s" % (ob.data.energy / 50)
        light_range = "range=%s" % int(ob.data.shadow_soft_size * 1000)
        light_inner_cone_angle = "innerconeangle=%s" % int(ob.data.spot_blend * outer_deg)
        light_outer_cone_angle = "outerconeangle=%s" % int(outer_deg)
        light_linear_falloff = "linearfalloff=%s" % int(ob.cb.linear_falloff)

        node_name = "classname=spotlight\r\n%s\r\n%s\r\n%s\r\n%s\r\n%s\r\n%s\r\n%s" % (light_angles, light_color, light_intensity, light_range, light_inner_cone_angle, light_outer_cone_angle, light_linear_falloff)
    elif object_type_enum == ObjectType.node_sunlight:
        r, g, b = ob.data.color

        light_angles = "angles=%s %s %s" % (0, 0, 0)
        light_color = "color=%s %s %s" % (int(r * 255), int(g * 255), int(b * 255))
        light_intensity = "intensity=%s" % (ob.data.energy / 50)

        node_name = "classname=sunlight\r\n%s\r\n%s\r\n%s" % (light_angles, light_color, light_intensity)
    elif object_type_enum == ObjectType.node_soundemitter:
        sound_id_str = "sound=%s" % ob.cb.sound_emitter_id
        range_str = "range=%s" % ob.data.distance_max
        node_name = "classname=soundemitter\r\n%s\r\n%s" % (sound_id_str, range_str)
    elif object_type_enum == ObjectType.node_waypoint:
        node_name = "classname=waypoint"

    return node_name

def get_scene_objects(context, b3d_data, node_dict, depsgraph, skin_info, key_info, armature_ob, parent_ob=None):
    for ob in bpy.data.objects:
        if ob.parent == parent_ob:
            transform_matrix = ob.matrix_local
            loc, rot_quat, scl = transform_matrix.decompose()

            node_name = get_node_name(ob)

            tx, ty, tz = Matrix.Scale(160, 4) @ loc
            sx, sy, sz = scl
            rw, ri, rj, rk = rot_quat
            ob_node_dict = {
                "name": node_name,
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

            if armature_ob:
                if ob.type == "ARMATURE":
                    ob_node_dict["bones"] = []
                    get_scene_bones(b3d_data, ob_node_dict["nodes"], depsgraph, skin_info, key_info, ob)

                key_data = key_info.get(ob.name)
                if key_data is not None:
                    ob_node_dict["key"] = []
                    for action_group in key_data:
                        action_entry = []
                        for frame_data in action_group:
                            frame_index, frame_transform = frame_data

                            f_loc, f_rot_quat, f_scl = frame_transform.decompose()

                            f_tx, f_ty, f_tz = Matrix.Scale(160, 4) @ f_loc
                            f_sx, f_sy, f_sz = f_scl
                            f_rw, f_ri, f_rj, f_rk = f_rot_quat
                            key_dict = {
                                "frame": frame_index,
                                "position": [
                                    f_tx,
                                    f_tz,
                                    f_ty
                                ],
                                "scale": [
                                    f_sx,
                                    f_sz,
                                    f_sy
                                ],
                                "rotation": [
                                    f_rw,
                                    f_ri,
                                    f_rk,
                                    f_rj
                                ],
                            }

                            action_entry.append(key_dict)

                        ob_node_dict["key"].append(action_entry)

            else:
                if ob.type == "MESH":
                    skin_info, mesh_dict = get_mesh(b3d_data, ob, depsgraph)
                    ob_node_dict["mesh"] = mesh_dict

            get_scene_objects(context, b3d_data, ob_node_dict["nodes"], depsgraph, skin_info, key_info, armature_ob, ob)

            node_dict.append(ob_node_dict)

def set_image_properties(img, texture_dict):
    if img:
        img_b3d = img.cb

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

def set_material_properties(b3d_node, material_dict):
    if b3d_node:
        mat_flags = MaterialFXFlags(material_dict["fx"])

        if MaterialFXFlags.full_bright in mat_flags:
            b3d_node.inputs["Full Bright"].default_value = True
        if MaterialFXFlags.use_vertex_colors_instead_of_brush_color in mat_flags:
            b3d_node.inputs["Use Vertex Colors Instead Of Brush Color"].default_value = True
        if MaterialFXFlags.flatshaded in mat_flags:
            b3d_node.inputs["Flat Shaded"].default_value = True
        if MaterialFXFlags.disable_fog in mat_flags:
            b3d_node.inputs["Disable Fog"].default_value = True
        if MaterialFXFlags.disable_backface_culling in mat_flags:
            b3d_node.inputs["Disable Backface Culling"].default_value = True
        if MaterialFXFlags.unk5 in mat_flags:
            b3d_node.inputs["Unknown 5"].default_value = True

        b3d_node.inputs["Blend Type"].default_value = material_dict["blend"]
        b3d_node.inputs["Shine"].default_value = material_dict["shine"]
        b3d_node.inputs["Diffuse Overlay"].default_value = material_dict["rgba"]

def get_image_properties(img, texture_dict):
    img_b3d = img.cb

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

def gather_keyframe_data(armature, node_data, bake_action=False):
    if not armature.animation_data:
        return

    tracks = armature.animation_data.nla_tracks
    if not tracks:
        return

    original_action = armature.animation_data.action
    temp_action = None

    nla_strips = []
    for track in tracks:
        if track.mute:
            continue

        nla_strips.extend([s for s in track.strips if s.action])

    for strip in nla_strips:
        action = strip.action
        if bake_action:
            temp_action = action.copy()
            temp_action.name = action.name + "_TEMP"
            armature.animation_data.action = temp_action
            bpy.ops.nla.bake(
                frame_start=int(strip.frame_start),
                frame_end=int(strip.frame_end),
                only_selected=False,
                visual_keying=True,
                clear_constraints=False,
                clear_parents=False,
                use_current_action=True,
                bake_types={'POSE'}
            )
            action = temp_action

        if (5, 0, 0) <= bpy.app.version:
            if action.slots:
                slot = action.slots[0]
            else:
                slot = action.slots.new(id_type='OBJECT', name=armature.name)
            channelbag = anim_utils.action_ensure_channelbag_for_slot(action, slot)
            fcurves = channelbag.fcurves
        else:
            fcurves = action.fcurves

        node_fcurves = defaultdict(list)
        for fc in fcurves:
            dp = fc.data_path
            if dp.startswith('pose.bones["'):
                node_name = dp.split('"', 2)[1]

            else:
                node_name = armature.name

            node_fcurves[node_name].append(fc)
            node_data.setdefault(node_name, [])

        for node_name, node_fcs in node_fcurves.items():
            frames = sorted({int(kp.co.x) for fc in node_fcs for kp in fc.keyframe_points})

            is_bone = node_name != armature.name
            if is_bone and armature.pose and node_name in armature.pose.bones:
                rot_mode = armature.pose.bones[node_name].rotation_mode

            else:
                rot_mode = armature.rotation_mode

            strip_keyframes = []
            for frame in frames:
                loc = [0.0, 0.0, 0.0]
                scale = [1.0, 1.0, 1.0]
                if rot_mode == 'QUATERNION':
                    rot = [1.0, 0.0, 0.0, 0.0]

                else:
                    rot = [0.0, 0.0, 0.0]

                for fc in node_fcs:
                    val = fc.evaluate(frame)
                    idx = fc.array_index

                    if fc.data_path.endswith("location"):
                        loc[idx] = val

                    elif fc.data_path.endswith("scale"):
                        scale[idx] = val

                    elif fc.data_path.endswith("rotation_quaternion") and rot_mode == 'QUATERNION':
                        rot[idx] = val

                    elif fc.data_path.endswith("rotation_euler") and rot_mode != 'QUATERNION':
                        rot[idx] = val

                if rot_mode == 'QUATERNION':
                    mat = Matrix.LocRotScale(Vector(loc), Quaternion(rot), Vector(scale))
                else:
                    mat = Matrix.LocRotScale(Vector(loc), Euler(rot, rot_mode).to_quaternion(), Vector(scale))

                strip_keyframes.append((frame, mat))

            node_data[node_name].append(strip_keyframes)

        nodes_without_fc = set(node_data.keys()) - set(node_fcurves.keys())
        for node_name in nodes_without_fc:
            node_data[node_name].append([])

        if bake_action and temp_action:
            armature.animation_data.action = None
            bpy.data.actions.remove(temp_action)
            temp_action = None

    armature.animation_data.action = original_action

def export_scene(context, filepath, report):
    active_ob = context.view_layer.objects.active
    if active_ob is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    depsgraph = context.evaluated_depsgraph_get()

    b3d_data = {"nodes": [], "textures": [], "materials": []}

    armature_ob = None
    skin_info = None
    mesh_dict = None
    key_dict = defaultdict(list)
    if active_ob is not None and active_ob.type == "ARMATURE" and active_ob.animation_data is not None and active_ob.animation_data.nla_tracks is not None:
        armature_ob = active_ob

    if armature_ob is None:
        for ob in bpy.data.objects:
            if ob.type == "ARMATURE" and ob.animation_data is not None and ob.animation_data.nla_tracks is not None:
                armature_ob = ob
                break

    if armature_ob:
        armature_ob.data.pose_position = 'REST'
        depsgraph.update()
        for node_ob in bpy.data.objects:
            if node_ob.type == "MESH" and node_ob.parent == armature_ob:
                skin_info, mesh_dict = get_mesh(b3d_data, node_ob, depsgraph, armature_ob)
            elif node_ob.type == "ARMATURE":
                gather_keyframe_data(node_ob, key_dict)

    get_scene_objects(context, b3d_data, b3d_data["nodes"], depsgraph, skin_info, key_dict, armature_ob)

    if armature_ob and len(b3d_data["nodes"]) > 0:
        root_node = b3d_data["nodes"][0]
        if mesh_dict is not None:
            root_node["mesh"] = mesh_dict

        for nla_track in armature_ob.animation_data.nla_tracks:
            if nla_track.name == armature_ob.name:
                flags = 0
                frame_end = int(context.scene.frame_end)
                fps = int(context.scene.render.fps)

                root_node["anim"] = {"flags": flags, "frames": frame_end, "fps": fps}
                root_node["sequences"] = []
                for strip in nla_track.strips:
                    strip_name = strip.action.name.replace("%s_" % armature_ob.name, "")
                    start_frame = int(strip.action_frame_start)
                    end_frame = int(strip.action_frame_end)
                    flags = 0
                    strip_dict = {"name": strip_name, "start": start_frame, "end": end_frame, "flags": flags}
                    root_node["sequences"].append(strip_dict)

    write_b3d(filepath, b3d_data)

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

def find_bones(node, bone_check_list, uv_counts):
    mesh_dict = node.get("mesh")
    bone_check_list.append(bool(node.get("bones")))
    if mesh_dict is not None:
        for uv_channel in mesh_dict["uvs"]:
            uv_counts.append(len(uv_channel))

    for child_node in node["nodes"]:
        find_bones(child_node, bone_check_list, uv_counts)
    
def import_scene(context, filepath, report, bm=None, ob_data=None, is_simple=False, error_log=None, random_color_gen=None):
    game_path = Path(bpy.context.preferences.addons[__package__].preferences.game_path)

    local_asset_path = ""
    if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
        local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

    data = B3DTree().parse(filepath)

    if error_log is None:
        error_log = set()
    if random_color_gen is None:
        random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    material_list = []
    texture_count = 0
    
    has_skeleton = False
    bone_check_list = []
    uv_counts = []
    for child_node in data["nodes"]:
        find_bones(child_node, bone_check_list, uv_counts)

    texture_dict = data.get("textures")
    material_dict = data.get("materials")
    if texture_dict is not None:
        texture_count = len(texture_dict)

    has_lightmap_data = False
    for uv_count in uv_counts:
        if uv_count > 2:
            has_lightmap_data = True

    if material_dict is not None:
        for material_dict in data["materials"]:
            material = bpy.data.materials.new(material_dict["name"])
            material.diffuse_color = random_color_gen.next()

            material.use_nodes = True
            for node in material.node_tree.nodes:
                material.node_tree.nodes.remove(node)

            output_material_node = get_output_material_node(material)
            output_material_node.location = Vector((0.0, 0.0))

            b3d_node = get_shader_node(material.node_tree, SHADER_RESOURCES, "b3d_material")
            b3d_node.name = "B3D Material"
            b3d_node.location = (-440.0, 0.0)
            set_material_properties(b3d_node, material_dict)

            connect_inputs(material.node_tree, b3d_node, "Shader", output_material_node, "Surface")

            valid_texture_id_count = 0
            for tid_element in material_dict["tids"]:
                if tid_element != -1 and texture_count > tid_element:
                    valid_texture_id_count += 1

            for tex_idx, tid_element in enumerate(material_dict["tids"]):
                if valid_texture_id_count == 1:
                    texture_type = TextureTypeEnum.diffuse
                else:
                    if tex_idx == 0:
                        texture_type = TextureTypeEnum.lightmap
                    elif tex_idx == 1:
                        texture_type = TextureTypeEnum.diffuse
                    elif tex_idx == 2:
                        texture_type = TextureTypeEnum.specular

                if texture_type == TextureTypeEnum.lightmap and not has_lightmap_data:
                    continue

                if tid_element != -1 and texture_count > tid_element:
                    texture = data["textures"][tid_element]
                    texture_asset = get_file(os.path.basename(texture['name']), True, True, directory_path=local_asset_path)
                    if texture_asset:
                        set_image_properties(texture_asset, texture)

                        texture_node = material.node_tree.nodes.new('ShaderNodeTexImage')
                        texture_node.image = texture_asset

                        if texture_type == TextureTypeEnum.lightmap:
                            texture_node.location = (-720.0, 0)
                            connect_inputs(material.node_tree, texture_node, "Color", b3d_node, "Light Map")
                            connect_inputs(material.node_tree, texture_node, "Alpha", b3d_node, "Light Map Alpha")
                            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_node)
                            uv_node.uv_map = "uvmap_lightmap"
                            mapping_node.vector_type = 'TEXTURE'
                            tx, ty = texture["position"]
                            sx, sy = texture["scale"]
                            rx = texture["rotation"]
                            mapping_node.inputs["Location"].default_value = (tx, ty, 0)
                            mapping_node.inputs["Scale"].default_value = (sx, sy, 1)
                            mapping_node.inputs["Rotation"].default_value = (radians(rx), 0, 0)


                        elif texture_type == TextureTypeEnum.diffuse:
                            texture_node.location = (-720.0, -380)
                            connect_inputs(material.node_tree, texture_node, "Color", b3d_node, "Diffuse Map")
                            connect_inputs(material.node_tree, texture_node, "Alpha", b3d_node, "Diffuse Map Alpha")
                            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_node)
                            uv_node.uv_map = "uvmap_render"
                            mapping_node.vector_type = 'TEXTURE'
                            tx, ty = texture["position"]
                            sx, sy = texture["scale"]
                            rx = texture["rotation"]
                            mapping_node.inputs["Location"].default_value = (tx, ty, 0)
                            mapping_node.inputs["Scale"].default_value = (sx, sy, 1)
                            mapping_node.inputs["Rotation"].default_value = (radians(rx), 0, 0)

                        elif texture_type == TextureTypeEnum.specular:
                            texture_node.location = (-720.0, -760)
                            connect_inputs(material.node_tree, texture_node, "Color", b3d_node, "Specular Map")
                            connect_inputs(material.node_tree, texture_node, "Alpha", b3d_node, "Specular Map Alpha")
                            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_node)
                            uv_node.uv_map = "uvmap_render"
                            mapping_node.vector_type = 'TEXTURE'
                            tx, ty = texture["position"]
                            sx, sy = texture["scale"]
                            rx = texture["rotation"]
                            mapping_node.inputs["Location"].default_value = (tx, ty, 0)
                            mapping_node.inputs["Scale"].default_value = (sx, sy, 1)
                            mapping_node.inputs["Rotation"].default_value = (radians(rx), 0, 0)

                    if not texture_asset and texture_type == TextureTypeEnum.diffuse:
                        texture_bump_data = get_file("%sbump" % os.path.basename(texture['name']).rsplit(".", 1)[0], directory_path=local_asset_path)
                        if texture_bump_data:
                            texture_bump = material.node_tree.nodes.new("ShaderNodeTexImage")
                            texture_bump.image = texture_bump_data
                            texture_bump.image.alpha_mode = 'CHANNEL_PACKED'
                            texture_bump.interpolation = 'Cubic'
                            texture_bump.image.colorspace_settings.name = 'Non-Color'
                            texture_bump.location = (-720.0, -1140)
                            connect_inputs(material.node_tree, texture_bump, "Color", b3d_node, "Normal Map")
                            connect_inputs(material.node_tree, texture_bump, "Alpha", b3d_node, "Normal Map Alpha")
                            mapping_node, uv_node = generate_texture_mapping(material.node_tree, texture_node)
                            uv_node.uv_map = "uvmap_render"
                            mapping_node.vector_type = 'TEXTURE'
                            tx, ty = texture["position"]
                            sx, sy = texture["scale"]
                            rx = texture["rotation"]
                            mapping_node.inputs["Location"].default_value = (tx, ty, 0)
                            mapping_node.inputs["Scale"].default_value = (sx, sy, 1)
                            mapping_node.inputs["Rotation"].default_value = (radians(rx), 0, 0)

            material_list.append(material)

    strips = []
    armature_ob = None
    for has_bone in bone_check_list:
        if has_bone:
            has_skeleton = True
            break

    for child_node in data["nodes"]:
        import_node_recursive(context, data, child_node, material_list, armature_ob, strips, has_skeleton, is_simple=is_simple, bm=bm, ob_data=ob_data)

    if not is_simple:
        if context.view_layer.objects.active is not None:
            bpy.ops.object.mode_set(mode='OBJECT')

        for error in error_log:
            report({'WARNING'}, error)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
