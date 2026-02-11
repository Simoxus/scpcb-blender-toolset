import re
import os
import bpy
import bmesh
import configparser

from . import ObjectType
from pathlib import Path
from mathutils import Matrix, Vector, Euler, Quaternion
from .scene_x import import_scene as import_x
from .scene_b3d import import_scene as import_b3d
from math import radians, pi, degrees, asin, atan2
from .process_rmesh import TextureType, write_rmesh, read_rmesh, ImportFileType, ExportFileType
from .object_helper import create_door, DoorType, ButtonType, DoorState
from .common_functions import (RandomColorGenerator, 
                               get_file, 
                               is_string_empty, 
                               get_blender_rot, 
                               get_material_name, 
                               get_linked_node, 
                               connect_inputs, 
                               get_output_material_node, 
                               flip, 
                               RTOD)

def natural_key(s):
    return [int(t) if t.isdigit() else t.lower()
            for t in re.split(r'(\d+)', s)]

def get_referenced_collection(collection_name, parent_collection, hide_render=False, hide_viewport=False):
    asset_collection = bpy.data.collections.get(collection_name)
    if asset_collection == None:
        asset_collection = bpy.data.collections.new(collection_name)
        parent_collection.children.link(asset_collection)
        if not parent_collection.name == "Scene Collection":
            asset_collection.tag_collection.parent = parent_collection

    asset_collection.hide_render = hide_render
    asset_collection.hide_viewport = hide_viewport

    return asset_collection

def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))

def get_blitz_rot(rot):
    q = rot.normalized()
    m = q.to_matrix()

    v = -m[1][2]
    v = clamp(v)

    if abs(v) < 0.999999:
        pitch = asin(v)
        yaw   = atan2(m[0][2], m[2][2])
        roll  = atan2(m[1][0], m[1][1])
    else:
        pitch = asin(v)
        yaw   = atan2(-m[2][0], m[0][0])
        roll  = 0.0

    yaw = -yaw

    return (pitch * RTOD, yaw * RTOD, roll * RTOD)

def collect_objects():
    mesh_list = []
    collision_list = []
    trigger_box_list = []
    entity_list = []

    for ob in bpy.data.objects:
        ob_type = ObjectType(int(ob.cb.object_type))
        if ob_type == ObjectType.mesh:
            if ob.type == 'MESH':
                mesh_list.append(ob)
        elif ob_type == ObjectType.collision:
            if ob.type == 'MESH':
                collision_list.append(ob)
        elif ob_type == ObjectType.trigger_box:
            if ob.type == 'MESH':
                trigger_box_list.append(ob)
        elif ob_type == ObjectType.entity_screen:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_save_screen:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_waypoint:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_light:
            if ob.type == 'LIGHT' and ob.data.type == 'POINT':
                entity_list.append(ob)
        elif ob_type == ObjectType.entity_light_fix:
            if ob.type == 'LIGHT' and ob.data.type == 'POINT':
                entity_list.append(ob)
        elif ob_type == ObjectType.entity_spotlight:
            if ob.type == 'LIGHT' and ob.data.type == 'SPOT':
                entity_list.append(ob)
        elif ob_type == ObjectType.entity_sound_emitter:
            if ob.type == 'SPEAKER':
                entity_list.append(ob)
        elif ob_type == ObjectType.entity_player_start:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_model:
            entity_list.append(ob)
        elif ob_type == ObjectType.entity_mesh:
            entity_list.append(ob)

    entity_list.sort(key=lambda obj: natural_key(obj.name)) # Doing this cause no idea if the game cares about order for entities. Probably not but better be safe. - Gen

    return mesh_list, collision_list, trigger_box_list, entity_list

def export_scene(context, filepath, file_type, report):
    if context.view_layer.objects.active is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    file_type = ExportFileType(int(file_type))
    if file_type == ExportFileType.rmesh or file_type == ExportFileType.rmesh_uer:
        rmesh_file_type = "RoomMesh"
    elif file_type == ExportFileType.rmesh_tb:
        rmesh_file_type = "RoomMesh.HasTriggerBox"
    elif file_type == ExportFileType.rmesh_uer2:
        rmesh_file_type = "RoomMesh2"

    rmesh_dict = {
        "rmesh_file_type": rmesh_file_type,
        "meshes": [],
        "collision_meshes": [],
        "trigger_boxes": [],
        "entities": []
    }

    mesh_list, collision_list, trigger_box_list, entity_list = collect_objects()

    pivot_matrix = Matrix.Rotation(radians(-90), 4, 'X') @  Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Scale(160.0, 4)
    depsgraph = context.evaluated_depsgraph_get()

    section_data = {}
    for ob in mesh_list:
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

        for tri in mesh.loop_triangles:
            mat_name = get_material_name(ob, tri)
            if mat_name not in section_data:
                section_data[mat_name] = {"textures": [], "vertices": [], "triangles": [], "vertex_map": {}}
                lightmap_texture_dict = {"texture_type": 0, "texture_name": ""}
                diffuse_texture_dict = {"texture_type": 0, "texture_name": ""}

                mat = bpy.data.materials.get(mat_name)
                if mat.use_nodes:
                    for node in mat.node_tree.nodes:
                        if node.type == 'TEX_IMAGE':
                            image = node.image
                            if not image:
                                continue

                            if image.filepath:
                                filename = os.path.basename(bpy.path.abspath(image.filepath))
                                name_no_ext = os.path.splitext(filename)[0]
                                if "_lm" in name_no_ext.lower():
                                    lightmap_texture_dict["texture_type"] = TextureType.lightmap.value
                                    lightmap_texture_dict["texture_name"] = filename
                                    break

                    output_material_node = get_output_material_node(mat)
                    bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
                    image_node_a = get_linked_node(bdsf_principled, "Base Color", "TEX_IMAGE")
                    image_node_b = get_linked_node(bdsf_principled, "Alpha", "TEX_IMAGE")

                    if image_node_a is not None:
                        diffuse_texture_dict["texture_type"] = TextureType.opaque.value
                        if image_node_a.image.filepath:
                            diffuse_texture_dict["texture_name"] = os.path.basename(bpy.path.abspath(image_node_a.image.filepath))

                        if image_node_a == image_node_b:
                            diffuse_texture_dict["texture_type"] = TextureType.transparent.value

                section_data[mat_name]["textures"].append(lightmap_texture_dict)
                section_data[mat_name]["textures"].append(diffuse_texture_dict)

            mesh_section = section_data[mat_name]
            vertex_map = mesh_section["vertex_map"]
            tri_indices = []
            for loop_index in tri.loops:
                loop = mesh.loops[loop_index]
                v = mesh.vertices[loop.vertex_index]
                i, j, k = loop.normal
                loop_normal = (i, j, k)

                pos = pivot_matrix @ (ob_eval.matrix_world @ v.co)

                uv_render = (0.0, 0.0)
                uv_lightmap = (0.0, 0.0)
                if layer_uv_0:
                    u0, v0 = layer_uv_0.data[loop_index].uv
                    uv_render = (u0, 1 - v0)

                if layer_uv_1:
                    u1, v1 = layer_uv_1.data[loop_index].uv
                    uv_lightmap = (u1, 1 - v1)

                color = (0, 0, 0)
                if layer_color:
                    r, g, b, a = layer_color.data[loop_index].color
                    color = (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))

                if file_type == ExportFileType.rmesh_uer2:
                    key = (round(pos.x, 6), round(pos.y, 6), round(pos.z, 6), uv_render, uv_lightmap, color, loop_normal)
                else:
                    key = (round(pos.x, 6), round(pos.y, 6), round(pos.z, 6), uv_render, uv_lightmap, color)
                if key not in vertex_map:
                    vertex_map[key] = len(mesh_section["vertices"])
                    vert_dict = {"position": pos, "uv_render": uv_render, "uv_lightmap": uv_lightmap, "color": color}
                    if file_type == ExportFileType.rmesh_uer2:
                        vert_dict["normal"] = loop_normal

                    mesh_section["vertices"].append(vert_dict)

                tri_indices.append(vertex_map[key])

            mesh_section["triangles"].append({"a": tri_indices[2], "b": tri_indices[1], "c": tri_indices[0]})

        ob_eval.to_mesh_clear()

    for mesh_dict in section_data.values():
        rmesh_dict["meshes"].append(mesh_dict)

    for ob in collision_list:
        if ob.type == 'MESH':
            ob_eval = ob.evaluated_get(depsgraph)
            mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
            mesh.calc_loop_triangles()

            mesh_dict = {
                "vertices": [],
                "triangles": []
            }
            for v in mesh.vertices:
                pos = pivot_matrix @ (ob_eval.matrix_world @ v.co)
                mesh_dict["vertices"].append({"position": pos})

            for tri in mesh.loop_triangles:
                tri_indices = [mesh.loops[loop_index].vertex_index for loop_index in tri.loops]
                mesh_dict["triangles"].append({"a": tri_indices[2], "b": tri_indices[1], "c": tri_indices[0]})

            ob_eval.to_mesh_clear()
            rmesh_dict["collision_meshes"].append(mesh_dict)

    if file_type == ExportFileType.rmesh_tb:
        for ob in trigger_box_list:
            if ob.type == 'MESH':
                trigger_group = ob.cb.trigger_group
                if is_string_empty(trigger_group):
                    trigger_group = "unnamed"

                trigger_entry = None
                for trigger_dict in rmesh_dict["trigger_boxes"]:
                    if trigger_dict["name"] == trigger_group:
                        trigger_entry = trigger_dict
                        break

                if trigger_entry is None:
                    trigger_entry = {"meshes": [], "name": trigger_group}
                    rmesh_dict["trigger_boxes"].append(trigger_entry)

                ob_eval = ob.evaluated_get(depsgraph)
                mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
                mesh.calc_loop_triangles()

                mesh_dict = {
                    "vertices": [],
                    "triangles": []
                }
                for v in mesh.vertices:
                    pos = pivot_matrix @ (ob_eval.matrix_world @ v.co)
                    mesh_dict["vertices"].append({"position": pos})

                for tri in mesh.loop_triangles:
                    tri_indices = [mesh.loops[loop_index].vertex_index for loop_index in tri.loops]
                    mesh_dict["triangles"].append({"a": tri_indices[2], "b": tri_indices[1], "c": tri_indices[0]})

                trigger_entry["meshes"].append(mesh_dict)
                ob_eval.to_mesh_clear()

    for ob in entity_list:
        object_type = ObjectType(int(ob.cb.object_type))
        if object_type == ObjectType.entity_screen:
            loc, rot, scale = (pivot_matrix @ ob.matrix_world).decompose()
            entity_dict = {}

            entity_dict["entity_type"] = "screen"
            entity_dict["position"] = loc
            entity_dict["texture_name"] = os.path.basename(bpy.path.abspath(ob.cb.texture_path))
            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_save_screen:
            loc, rot, inverted_scale = (pivot_matrix @ ob.matrix_world).decompose()
            inverted_loc, inverted_rot, scale = ob.matrix_world.decompose()

            entity_dict = {}

            entity_dict["entity_type"] = "save_screen"
            entity_dict["position"] = loc
            entity_dict["model_name"] = os.path.basename(bpy.path.abspath(ob.cb.model_path))
            entity_dict["euler_rotation"] = get_blitz_rot(rot)
            entity_dict["scale"] = scale
            entity_dict["texture_name"] = os.path.basename(bpy.path.abspath(ob.cb.texture_path))
            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_waypoint:
            loc, rot, scale = (pivot_matrix @ ob.matrix_world).decompose()
            entity_dict = {}

            entity_dict["entity_type"] = "waypoint"
            entity_dict["position"] = loc
            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_light:
            loc, rot, scale = (pivot_matrix @ ob.matrix_world).decompose()
            r, g, b = ob.data.color
            entity_dict = {}

            entity_dict["entity_type"] = "light"
            entity_dict["position"] = loc
            entity_dict["range"] = ob.data.shadow_soft_size * 1000
            entity_dict["color"] = "%s %s %s" % (round(r * 255), round(g * 255), round(b * 255))
            entity_dict["intensity"] = ob.data.energy / 50
            if file_type == ExportFileType.rmesh_uer2:
                entity_dict["has_sprite"] = ob.cb.has_sprite
                entity_dict["sprite_scale"] = ob.cb.sprite_scale
                entity_dict["casts_shadows"] = ob.data.use_shadow
                entity_dict["scattering"] = ob.cb.scattering
                entity_dict["ff_array"] = []
                for ff in range(31):
                    entity_dict["ff_array"].append(0)

            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_light_fix:
            loc, rot, scale = (pivot_matrix @ ob.matrix_world).decompose()
            r, g, b = ob.data.color
            entity_dict = {}

            entity_dict["entity_type"] = "light_fix"
            entity_dict["position"] = loc
            entity_dict["color"] = "%s %s %s" % (round(r * 255), round(g * 255), round(b * 255))
            entity_dict["intensity"] = ob.data.energy / 50
            entity_dict["range"] = ob.data.shadow_soft_size * 1000
            if file_type == ExportFileType.rmesh_uer2:
                entity_dict["has_sprite"] = ob.cb.has_sprite
                entity_dict["sprite_scale"] = ob.cb.sprite_scale
                entity_dict["casts_shadows"] = ob.data.use_shadow
                entity_dict["scattering"] = ob.cb.scattering
                entity_dict["ff_array"] = []
                for ff in range(31):
                    entity_dict["ff_array"].append(0)

            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_spotlight:
            loc, rot, scale = (pivot_matrix @ ob.matrix_world).decompose()
            r, g, b = ob.data.color
            entity_dict = {}

            entity_dict["entity_type"] = "spotlight"
            entity_dict["position"] = loc
            entity_dict["range"] = ob.data.shadow_soft_size * 1000
            entity_dict["color"] = "%s %s %s" % (round(r * 255), round(g * 255), round(b * 255))
            entity_dict["intensity"] = ob.data.energy / 50
            if file_type == ExportFileType.rmesh_uer2:
                p, y, r = get_blitz_rot(rot)
                entity_dict["has_sprite"] = ob.cb.has_sprite
                entity_dict["sprite_scale"] = ob.cb.sprite_scale
                entity_dict["casts_shadows"] = ob.data.use_shadow
                entity_dict["direction"] = [p, y]
                entity_dict["inner_cosine"] = degrees(ob.data.spot_size)
                entity_dict["scattering"] = ob.data.spot_blend
                entity_dict["ff_array"] = []
                for ff in range(31):
                    entity_dict["ff_array"].append(0)

            else:
                outer_deg = degrees(ob.data.spot_size)
                p, y, r = get_blitz_rot(rot)
                entity_dict["euler_rotation"] = "%s %s %s" % (p, y, r)
                entity_dict["inner_cone_angle"] = int(ob.data.spot_blend * outer_deg)
                entity_dict["outer_cone_angle"] = int(outer_deg)

            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_sound_emitter:
            loc, rot, scale = (pivot_matrix @ ob.matrix_world).decompose()
            entity_dict = {}

            entity_dict["entity_type"] = "soundemitter"
            entity_dict["position"] = loc
            entity_dict["id"] = ob.cb.sound_emitter_id
            entity_dict["range"] = ob.data.distance_max
            rmesh_dict["entities"].append(entity_dict)

        elif object_type == ObjectType.entity_model:
            loc, rot, inverted_scale = (pivot_matrix @ (ob.matrix_world @ Matrix.Rotation(radians(-90), 4, 'X'))).decompose()
            inverted_loc, inverted_rot, scale = ob.matrix_world.decompose()
            entity_dict = {}

            entity_dict["entity_type"] = "model"
            entity_dict["model_name"] = os.path.basename(bpy.path.abspath(ob.cb.model_path))
            rmesh_dict["entities"].append(entity_dict)
            if not file_type == ExportFileType.rmesh_uer:
                entity_dict["position"] = loc
                entity_dict["euler_rotation"] = get_blitz_rot(rot)
                entity_dict["scale"] = scale

        elif object_type == ObjectType.entity_mesh:
            loc, rot, inverted_scale = (pivot_matrix @ ob.matrix_world).decompose()
            inverted_loc, inverted_rot, scale = ob.matrix_world.decompose()

            entity_dict = {}

            entity_dict["entity_type"] = "mesh"
            entity_dict["position"] = loc
            entity_dict["model_name"] = os.path.basename(bpy.path.abspath(ob.cb.model_path))
            entity_dict["euler_rotation"] = get_blitz_rot(rot)
            entity_dict["scale"] = scale
            entity_dict["has_collision"] = int(ob.cb.has_collision)
            entity_dict["fx"] = ob.cb.fx
            entity_dict["texture_name"] = os.path.basename(bpy.path.abspath(ob.cb.texture_path))
            rmesh_dict["entities"].append(entity_dict)

    write_rmesh(rmesh_dict, filepath, file_type)

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

def import_scene(context, filepath, file_type, report):
    file_type, rmesh_dict = read_rmesh(filepath, ImportFileType(int(file_type)))

    game_path = Path(bpy.context.preferences.addons[__package__].preferences.game_path)

    pivot_matrix = Matrix.Rotation(radians(90), 4, 'X') @ Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Scale(0.00625, 4)

    mesh_collection = get_referenced_collection("meshes", context.scene.collection, False)
    collision_collection = get_referenced_collection("collisions", context.scene.collection, True)
    entity_collection = get_referenced_collection("entities", context.scene.collection, False)

    random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    full_mesh = bpy.data.meshes.new("room_mesh")
    object_mesh = bpy.data.objects.new("room_mesh", full_mesh)
    object_mesh.cb.object_type = str(ObjectType.mesh.value)
    mesh_collection.objects.link(object_mesh)

    error_log = set()

    local_asset_path = ""
    local_prop_path = r"GFX\map\Props"
    local_screen_path = r"GFX\screens"
    if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
        local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

    bm = bmesh.new()
    for mesh_idx, mesh_dict in enumerate(rmesh_dict["meshes"]):
        mesh = bpy.data.meshes.new("temp_mesh_%s" % mesh_idx)

        vertices = [pivot_matrix @ Vector(vertex["position"]) for vertex in mesh_dict["vertices"]]
        triangles = [list(triangle.values())[::-1] for triangle in mesh_dict["triangles"]]
        mesh.from_pydata(vertices, [], triangles)

        mat = bpy.data.materials.new(name="texture_%s" % mesh_idx)
        mat.diffuse_color = random_color_gen.next()
        mesh.materials.append(mat)
        full_mesh.materials.append(mat)

        mat.use_nodes = True
        for node in mat.node_tree.nodes:
            mat.node_tree.nodes.remove(node)

        output_material_node = get_output_material_node(mat)
        output_material_node.location = Vector((0.0, 0.0))

        bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
        if bdsf_principled is None:
            bdsf_principled = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
            connect_inputs(mat.node_tree, bdsf_principled, "BSDF", output_material_node, "Surface")

        bdsf_principled.location = (-440.0, 0.0)

        texture_lightmap = None
        diffuse_type = TextureType.none
        texture_diffuse = None
        for texture_idx, texture_dict in enumerate(mesh_dict["textures"]):
            if texture_idx == 0:
                lightmap_type = TextureType(texture_dict["texture_type"])
                texture_lightmap_data = get_file(texture_dict["texture_name"], directory_path=local_asset_path)
                if texture_lightmap_data:
                    texture_lightmap = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    texture_lightmap.image = texture_lightmap_data
                    texture_lightmap.image.alpha_mode = 'CHANNEL_PACKED'
                    texture_lightmap.location = (-720.0, -320.0)
                elif len(texture_dict["texture_name"]) > 0:
                    error_log.add('Failed to retrive "%s"' % texture_dict["texture_name"])

            elif texture_idx == 1:
                diffuse_type = TextureType(texture_dict["texture_type"])
                texture_diffuse_data = get_file(texture_dict["texture_name"], directory_path=local_asset_path)
                if texture_diffuse_data:
                    texture_diffuse = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    texture_diffuse.image = texture_diffuse_data
                    texture_diffuse.image.alpha_mode = 'CHANNEL_PACKED'
                    texture_diffuse.location = (-720.0, 0.0)
                    connect_inputs(mat.node_tree, texture_diffuse, "Color", bdsf_principled, "Base Color")
                    if diffuse_type == TextureType.transparent:
                        connect_inputs(mat.node_tree, texture_diffuse, "Alpha", bdsf_principled, "Alpha")

                    texture_name = os.path.basename(texture_dict["texture_name"]).rsplit(".", 1)[0]
                    texture_bump_data = get_file("%sbump" % texture_name, directory_path=local_asset_path)
                    if texture_bump_data:
                        normal_map = mat.node_tree.nodes.new("ShaderNodeNormalMap")
                        texture_bump = mat.node_tree.nodes.new("ShaderNodeTexImage")
                        texture_bump.image = texture_bump_data
                        texture_bump.image.alpha_mode = 'CHANNEL_PACKED'
                        texture_bump.interpolation = 'Cubic'
                        texture_bump.image.colorspace_settings.name = 'Non-Color'
                        normal_map.location = (-720.0, -640.0)
                        texture_bump.location = (-720.0, -640.0)
                        connect_inputs(mat.node_tree, texture_bump, "Color", normal_map, "Color")
                        connect_inputs(mat.node_tree, normal_map, "Normal", bdsf_principled, "Normal")

                elif len(texture_dict["texture_name"]) > 0:
                    error_log.add('Failed to retrive "%s"' % texture_dict["texture_name"])
                    report({'WARNING'}, 'Failed to retrive "%s"' % texture_dict["texture_name"])
            else:
                report({'WARNING'}, 'Texture index out of range: %s' % texture_idx)

        loop_normals = []
        layer_color = mesh.color_attributes.new("color", "BYTE_COLOR", "CORNER")
        layer_uv_0 = mesh.uv_layers.new(name="uvmap_render")
        layer_uv_1 = mesh.uv_layers.new(name="uvmap_lightmap")
        for poly in mesh.polygons:
            poly.use_smooth = True
            poly.material_index = mesh_idx
            for loop_index in poly.loop_indices:
                vert_index = mesh.loops[loop_index].vertex_index
                vertex = mesh_dict["vertices"][vert_index]
                layer_uv_0.data[loop_index].uv = (vertex["uv_render"][0], 1 - vertex["uv_render"][1])
                layer_uv_1.data[loop_index].uv = (vertex["uv_lightmap"][0], 1 - vertex["uv_lightmap"][1])
                layer_color.data[loop_index].color = (vertex["color"][0] / 255, vertex["color"][1] / 255, vertex["color"][2] / 255, 1.0)
                if file_type == ImportFileType.rmesh_uer2:
                    loop_normals.append(Vector(flip(vertex["normal"])))

        if file_type == ImportFileType.rmesh_uer2:
            mesh.normals_split_custom_set(loop_normals)

        bm.from_mesh(mesh)
        bpy.data.meshes.remove(mesh)

    bm.to_mesh(full_mesh)
    bm.free()

    for coll_mesh_idx, coll_mesh_dict in enumerate(rmesh_dict["collision_meshes"]):
        collision_name = "coll_mesh_%s" % coll_mesh_idx
        coll_mesh = bpy.data.meshes.new(collision_name)
        coll_object_mesh = bpy.data.objects.new(collision_name, coll_mesh)
        coll_object_mesh.cb.object_type = str(ObjectType.collision.value)
        collision_collection.objects.link(coll_object_mesh)

        coll_vertices = [pivot_matrix @ Vector(coll_vertex["position"]) for coll_vertex in coll_mesh_dict["vertices"]]
        coll_triangles = [[coll_triangle["c"], coll_triangle["b"], coll_triangle["a"]] for coll_triangle in coll_mesh_dict["triangles"]]
        coll_mesh.from_pydata(coll_vertices, [], coll_triangles)
        for poly in coll_mesh.polygons:
            poly.use_smooth = True

    if file_type == ImportFileType.rmesh_tb:
        trigger_box_collection = get_referenced_collection("trigger_boxes", context.scene.collection, True)
        for trigger_box_idx, trigger_box_dict in enumerate(rmesh_dict["trigger_boxes"]):
            for trigger_idx, trigger_dict in enumerate(trigger_box_dict["meshes"]):
                trigger_name = "trigger_g%st%s" % (trigger_box_idx, trigger_idx)
                trigger_mesh = bpy.data.meshes.new(trigger_name)
                trigger_mesh_object_mesh = bpy.data.objects.new(trigger_name, trigger_mesh)
                trigger_mesh_object_mesh.cb.object_type = str(ObjectType.trigger_box.value)
                trigger_mesh_object_mesh.cb.trigger_group = trigger_box_dict["name"]
                trigger_box_collection.objects.link(trigger_mesh_object_mesh)

                trigger_vertices = [pivot_matrix @ Vector(trigger_vertex["position"]) for trigger_vertex in trigger_dict["vertices"]]
                trigger_triangles = [[trigger_triangle["c"], trigger_triangle["b"], trigger_triangle["a"]] for trigger_triangle in trigger_dict["triangles"]]
                trigger_mesh.from_pydata(trigger_vertices, [], trigger_triangles)
                for poly in trigger_mesh.polygons:
                    poly.use_smooth = True


    items_ini = None
    items_ini_path = os.path.join(game_path, r"Data\items.ini")
    if os.path.isfile(items_ini_path):
        items_ini = configparser.ConfigParser()
        items_ini.read(items_ini_path)

    entity_meshes = {}
    for entity_idx, entity_dict in enumerate(rmesh_dict["entities"]):
        if entity_dict["entity_type"] == "screen":
            object_mesh = bpy.data.objects.new("%s screen" % entity_idx, None)
            object_mesh.cb.object_type = str(ObjectType.entity_screen.value)
            object_mesh.empty_display_type = 'IMAGE'

            file_path = get_file(entity_dict["texture_name"], True, False, local_screen_path)
            object_mesh.cb.texture_path = file_path
            if os.path.isfile(file_path):
                file_asset = bpy.data.images.load(file_path, check_existing=True)
                object_mesh.data = file_asset

            entity_collection.objects.link(object_mesh)
            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])
            object_mesh.rotation_euler = Euler((radians(90), 0, radians(90)))

        elif entity_dict["entity_type"] == "save_screen":
            object_mesh = bpy.data.objects.new("%s save_screen" % entity_idx, None)
            object_mesh.cb.object_type = str(ObjectType.entity_save_screen.value)
            entity_collection.objects.link(object_mesh)

            loc, rot, sca = (pivot_matrix @ Matrix.LocRotScale(Vector(entity_dict["position"]), get_blender_rot(entity_dict["euler_rotation"]), Vector((1,1,1)))).decompose()
            global_transform = Matrix.LocRotScale(loc, rot, Vector(entity_dict["scale"]))

            object_mesh.matrix_world =  global_transform

            model_path = get_file(entity_dict["model_name"], False)
            texture_path = get_file(entity_dict["texture_name"], True, False)
            object_mesh.cb.model_path = model_path
            object_mesh.cb.texture_path = texture_path

        elif entity_dict["entity_type"] == "waypoint":
            object_mesh = bpy.data.objects.new("%s waypoint" % entity_idx, None)
            object_mesh.cb.object_type = str(ObjectType.entity_waypoint.value)
            entity_collection.objects.link(object_mesh)
            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])

        elif entity_dict["entity_type"] == "light":
            object_data = bpy.data.lights.new("%s light" % entity_idx, "POINT")
            object_mesh = bpy.data.objects.new("%s light" % entity_idx, object_data)
            object_mesh.cb.object_type = str(ObjectType.entity_light.value)
            entity_collection.objects.link(object_mesh)

            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])
            object_data.energy = entity_dict["intensity"] * 50
            object_data.shadow_soft_size = entity_dict["range"] / 1000
            r, g, b = entity_dict["color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)
            if file_type == ImportFileType.rmesh_uer2:
                object_mesh.cb.has_sprite = bool(entity_dict["has_sprite"])
                object_mesh.cb.sprite_scale = entity_dict["sprite_scale"]
                object_data.use_shadow = bool(entity_dict["casts_shadows"])
                object_mesh.cb.scattering = entity_dict["scattering"]

        elif entity_dict["entity_type"] == "light_fix":
            object_data = bpy.data.lights.new("%s light_fix" % entity_idx, "POINT")
            object_mesh = bpy.data.objects.new("%s light_fix" % entity_idx, object_data)
            object_mesh.cb.object_type = str(ObjectType.entity_light_fix.value)
            entity_collection.objects.link(object_mesh)

            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])
            object_data.energy = entity_dict["intensity"] * 50
            object_data.shadow_soft_size = entity_dict["range"] / 1000
            r, g, b = entity_dict["color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)
            if file_type == ImportFileType.rmesh_uer2:
                object_mesh.cb.has_sprite = bool(entity_dict["has_sprite"])
                object_mesh.cb.sprite_scale = entity_dict["sprite_scale"]
                object_data.use_shadow = bool(entity_dict["casts_shadows"])
                object_mesh.cb.scattering = entity_dict["scattering"]

        elif entity_dict["entity_type"] == "spotlight":
            object_data = bpy.data.lights.new("%s spotlight" % entity_idx, "SPOT")
            object_mesh = bpy.data.objects.new("%s spotlight" % entity_idx, object_data)
            object_mesh.cb.object_type = str(ObjectType.entity_spotlight.value)
            entity_collection.objects.link(object_mesh)

            object_data.energy = entity_dict["intensity"] * 50
            object_data.shadow_soft_size = entity_dict["range"] / 1000
            r, g, b = entity_dict["color"].split(" ")
            object_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

            if file_type == ImportFileType.rmesh_uer2:
                object_mesh.cb.has_sprite = bool(entity_dict["has_sprite"])
                object_mesh.cb.sprite_scale = entity_dict["sprite_scale"]
                object_data.use_shadow = bool(entity_dict["casts_shadows"])
                x, y = entity_dict["direction"]

                rotation = get_blender_rot([x, y, 0])
                object_data.spot_size = radians(entity_dict["inner_cosine"])
                object_data.spot_blend = entity_dict["scattering"]

            else:
                outer_deg: float = max(1.0, min(180.0, entity_dict["outer_cone_angle"]))
                inner_deg: float = max(1.0, min(180.0, entity_dict["inner_cone_angle"]))
                ratio = inner_deg / outer_deg if outer_deg > 0.0 else 1.0

                object_data.spot_size = radians(outer_deg)
                object_data.spot_blend = max(0.0, min(1.0, 1.0 - ratio))

                p, y, r = entity_dict["euler_rotation"].split(" ")
                rotation = get_blender_rot([float(p), float(y), float(r)])

            loc, rot, sca = (pivot_matrix @ Matrix.LocRotScale(Vector(entity_dict["position"]), rotation, Vector((1,1,1)))).decompose()
            global_transform = Matrix.LocRotScale(loc, rot, Vector((1, 1, 1)))

            object_mesh.matrix_world =  global_transform

        elif entity_dict["entity_type"] == "soundemitter":
            speaker_data = bpy.data.speakers.new("%s soundemitter" % entity_idx)
            object_mesh = bpy.data.objects.new("%s soundemitter" % entity_idx, speaker_data)
            object_mesh.cb.object_type = str(ObjectType.entity_sound_emitter.value)
            entity_collection.objects.link(object_mesh)
            object_mesh.location = pivot_matrix @ Vector(entity_dict["position"])
            object_mesh.cb.sound_emitter_id = entity_dict["id"]
            object_mesh.data.distance_max = entity_dict["range"]

        elif entity_dict["entity_type"] == "playerstart":
            object_mesh = bpy.data.objects.new("%s playerstart" % entity_idx, None)
            object_mesh.cb.object_type = str(ObjectType.entity_player_start.value)
            entity_collection.objects.link(object_mesh)

            p, y, r = entity_dict["euler_rotation"].split(" ")
            rotation = get_blender_rot([float(p), float(y), float(r)])

            loc, rot, sca = (pivot_matrix @ Matrix.LocRotScale(Vector(entity_dict["position"]), rotation, Vector((1,1,1)))).decompose()
            global_transform = Matrix.LocRotScale(loc, rot, Vector((1, 1, 1)))

            object_mesh.matrix_world =  global_transform

        elif entity_dict["entity_type"] == "model":
            model_path = get_file(entity_dict["model_name"], False, directory_path=local_prop_path)
            ob_data = entity_meshes.get(model_path)
            if ob_data is None and model_path:
                ob_data = entity_meshes[model_path] = bpy.data.meshes.new("%s model" % entity_idx)
                bm = bmesh.new()
                is_simple=True
                if model_path.lower().endswith(".b3d"):
                    import_b3d(context, Path(model_path), report, bm, ob_data, is_simple, error_log, random_color_gen)

                else:
                    import_x(context, Path(model_path), report, bm, ob_data, is_simple, error_log, random_color_gen)

                bm.to_mesh(ob_data)
                bm.free()

            object_mesh = bpy.data.objects.new("%s model" % entity_idx, ob_data)
            object_mesh.cb.object_type = str(ObjectType.entity_model.value)
            if model_path is not None:
                object_mesh.cb.model_path = model_path
            entity_collection.objects.link(object_mesh)
            if not file_type == ImportFileType.rmesh_uer:
                loc, rot, sca = (pivot_matrix @ Matrix.LocRotScale(Vector(entity_dict["position"]), get_blender_rot(entity_dict["euler_rotation"]), Vector((1,1,1)))).decompose()
                global_transform = Matrix.LocRotScale(loc, rot @ Matrix.Rotation(radians(90), 4, 'X').to_quaternion(), Vector(entity_dict["scale"]))

                object_mesh.matrix_world =  global_transform

        elif entity_dict["entity_type"] == "mesh":
            model_path = get_file(entity_dict["model_name"], False)
            texture_path = get_file(entity_dict["texture_name"], True, False)
            ob_data = entity_meshes.get(model_path)

            if ob_data is None and model_path:
                ob_data = entity_meshes[model_path] = bpy.data.meshes.new("%s mesh" % entity_idx)
                bm = bmesh.new()
                is_simple=True
                if model_path.lower().endswith(".b3d"):
                    import_b3d(context, Path(model_path), report, bm, ob_data, is_simple, error_log, random_color_gen)

                else:
                    import_x(context, Path(model_path), report, bm, ob_data, is_simple, error_log, random_color_gen)

                bm.to_mesh(ob_data)
                bm.free()

            object_mesh = bpy.data.objects.new("%s mesh" % entity_idx, ob_data)
            object_mesh.cb.object_type = str(ObjectType.entity_mesh.value)
            entity_collection.objects.link(object_mesh)

            if model_path is not None:
                object_mesh.cb.model_path = model_path
            object_mesh.cb.texture_path = texture_path

            loc, rot, sca = (pivot_matrix @ Matrix.LocRotScale(Vector(entity_dict["position"]), get_blender_rot(entity_dict["euler_rotation"]), Vector((1,1,1)))).decompose()
            global_transform = Matrix.LocRotScale(loc, rot, Vector(entity_dict["scale"]))

            object_mesh.matrix_world =  global_transform

            object_mesh.cb.has_collision = bool(entity_dict["has_collision"])
            object_mesh.cb.fx = entity_dict["fx"]

        elif entity_dict["entity_type"] == "item":
            ob_data = None
            model_path = None
            if items_ini:
                print()
                print("ITEM INI WAS TRUE")
                item_entry = items_ini.get(entity_dict["model_name"], "model", fallback=None)
                print("TEMPLATE NAME: ", entity_dict["model_name"])
                print("ITEM NAME: ", entity_dict["item_name"])
                print("ITEM ENTRY: ", item_entry)
                if item_entry:
                    print("ITEM ENTRY WAS FOUND")
                    print(item_entry)
                    model_path = get_file(item_entry, False)
                    ob_data = entity_meshes.get(model_path)

                    if ob_data is None and model_path:
                        ob_data = entity_meshes[model_path] = bpy.data.meshes.new("%s mesh" % entity_idx)
                        bm = bmesh.new()
                        is_simple=True
                        if model_path.lower().endswith(".b3d"):
                            import_b3d(context, Path(model_path), report, bm, ob_data, is_simple, error_log, random_color_gen)

                        else:
                            import_x(context, Path(model_path), report, bm, ob_data, is_simple, error_log, random_color_gen)

                        bm.to_mesh(ob_data)
                        bm.free()

            object_mesh = bpy.data.objects.new("%s item" % entity_idx, ob_data)
            object_mesh.cb.object_type = str(ObjectType.entity_item.value)
            entity_collection.objects.link(object_mesh)

            loc, rot, sca = (pivot_matrix @ Matrix.LocRotScale(Vector(entity_dict["position"]), get_blender_rot(entity_dict["euler_rotation"]), Vector((1,1,1)))).decompose()
            global_transform = Matrix.LocRotScale(loc, rot, Vector((1,1,1)))

            object_mesh.matrix_world =  global_transform
            object_mesh.cb.item_name = entity_dict["item_name"]
            if model_path is not None:
                object_mesh.cb.model_path = model_path
            object_mesh.cb.use_custom_rotation = bool(entity_dict["use_custom_rotation"])
            object_mesh.cb.state_1 = entity_dict["state_1"]
            object_mesh.cb.state_2 = entity_dict["state_2"]
            object_mesh.cb.spawn_chance = entity_dict["spawn_chance"]

        elif entity_dict["entity_type"] == "door":
            door_type = DoorType(entity_dict["door_type"])
            button_type = ButtonType.normal
            if entity_dict["key_card_level"] < 0:
                button_type = ButtonType.scanner
            elif len(entity_dict["keypad_code"]) > 0:
                button_type = ButtonType.code
            elif entity_dict["key_card_level"] > 0:
                button_type = ButtonType.keycard

            door_state = DoorState(entity_dict["start_open"])
            ob_data = create_door(door_type, button_type, door_state)
            object_mesh = bpy.data.objects.new("%s door" % entity_idx, ob_data)
            object_mesh.cb.object_type = str(ObjectType.entity_door.value)
            entity_collection.objects.link(object_mesh)

            loc, rot, sca = (pivot_matrix @ Matrix.LocRotScale(Vector(entity_dict["position"]), Quaternion(), Vector((1,1,1)))).decompose()
            global_transform = Matrix.LocRotScale(loc, Euler((0, 0, radians(entity_dict["angle"]))), Vector((1,1,1)))

            object_mesh.matrix_world =  global_transform

            object_mesh.cb.door_type = entity_dict["door_type"]
            object_mesh.cb.key_card_level = entity_dict["key_card_level"]
            object_mesh.cb.keypad_code = entity_dict["keypad_code"]
            object_mesh.cb.start_open = bool(entity_dict["start_open"])
            object_mesh.cb.allow_scp_079_remote_control = bool(entity_dict["allow_scp_079_remote_control"])



        else:
            report({'WARNING'}, "Unknown entity type: %s" % entity_dict["entity_type"])

    for error in error_log:
        report({'WARNING'}, error)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
