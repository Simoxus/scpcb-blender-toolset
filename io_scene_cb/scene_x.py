import os
import bpy

from pathlib import Path
from math import sqrt, radians
from mathutils import Matrix, Vector, Quaternion
from .process_x import write_x, read_x
from .common_functions import (RandomColorGenerator, 
                               get_file, 
                               is_string_empty, 
                               flip, 
                               get_output_material_node, 
                               get_shader_node,
                               connect_inputs,
                               PM_EXPORT,
                               PM_IMPORT,
                               SHADER_RESOURCES)

def create_object(arm_ob, parent_bone, x_dict, mesh_dict, ob_data=None, is_simple=False, world_transform=None, material_list=[], local_asset_path="", error_log=set(), random_color_gen=None):
    loop_normals = []
    mesh_name = mesh_dict["name"]
    if mesh_name == None:
        if parent_bone is not None:
            mesh_name = parent_bone.name
        else:
            mesh_name = "mesh"

    vertices = [PM_IMPORT @ Vector(vertex) for vertex in mesh_dict["vertices"]]
    triangles = [triangle[::-1] for triangle in mesh_dict["faces"]]
    mesh = bpy.data.meshes.new(mesh_name)
    mesh.from_pydata(vertices, [], triangles)
    if not is_simple:
        object_mesh = bpy.data.objects.new(mesh_name, mesh)
        bpy.context.collection.objects.link(object_mesh)
        object_mesh.parent = arm_ob
    else:
        if world_transform is not None:
            mesh.transform(world_transform)

    uv_render = mesh.uv_layers.new(name="uvmap_render")
    for poly_idx, poly in enumerate(mesh.polygons):
        poly.use_smooth = True

    if not x_dict["xof_header"] == "xof 0302txt 0064":
        for material_dict in mesh_dict["materials"]:
            material = bpy.data.materials.new(name=material_dict["name"])
            material.diffuse_color = random_color_gen.next()

            mesh.materials.append(material)
            if is_simple:
                ob_data.materials.append(material)

            material.use_nodes = True
            for node in material.node_tree.nodes:
                material.node_tree.nodes.remove(node)

            output_material_node = get_output_material_node(material)
            output_material_node.location = Vector((0.0, 0.0))

            x_node = get_shader_node(material.node_tree, SHADER_RESOURCES, "x_material")
            x_node.name = "X Material"
            x_node.location = (-440.0, 0.0)

            connect_inputs(material.node_tree, x_node, "Shader", output_material_node, "Surface")

            sr, sg, sb = material_dict["specular"]
            er, eg, eb = material_dict["emissive"]
            x_node.inputs["Diffuse Overlay"].default_value = material_dict["diffuse"]
            x_node.inputs["Power"].default_value = material_dict["power"]
            x_node.inputs["Specular"].default_value = (sr, sg, sb, 1)
            x_node.inputs["Emission"].default_value = (er, eg, eb, 1)

            texture_node = get_file(material_dict["texture"], True, True, directory_path=local_asset_path)
            if texture_node:
                texture = material.node_tree.nodes.new("ShaderNodeTexImage")
                texture.location = (-720.0, 0)
                texture.image = texture_node
                connect_inputs(material.node_tree, texture, "Color", x_node, "Diffuse Map")
                connect_inputs(material.node_tree, texture, "Alpha", x_node, "Diffuse Map Alpha")

                texture_bump_data = get_file("%sbump" % os.path.basename(material_dict["texture"]).rsplit(".", 1)[0], directory_path=local_asset_path)
                if texture_bump_data:
                    texture_bump = material.node_tree.nodes.new("ShaderNodeTexImage")
                    texture_bump.image = texture_bump_data
                    texture_bump.image.alpha_mode = 'CHANNEL_PACKED'
                    texture_bump.interpolation = 'Cubic'
                    texture_bump.image.colorspace_settings.name = 'Non-Color'
                    texture_bump.location = (-720.0, -380)
                    connect_inputs(material.node_tree, texture_bump, "Color", x_node, "Normal Map")
                    connect_inputs(material.node_tree, texture_bump, "Alpha", x_node, "Normal Map Alpha")

            else:
                if material_dict["texture"] is not None:
                    error_log.add('Failed to retrive "%s"' % material_dict["texture"])

    else:
        for mat in material_list:
            mesh.materials.append(mat)
            if is_simple:
                ob_data.materials.append(mat)

    if x_dict["xof_header"] == "xof 0302txt 0064":
        for mat_data_idx, material_face in enumerate(mesh_dict["material_indices"]):
            material_index = 0
            material_data = mesh_dict["materials"][mat_data_idx]
            for mat_idx, material in enumerate(x_dict["materials"]):
                if material["name"] == material_data["name"]:
                    material_index = mat_idx

            mesh.polygons[material_face].material_index = material_index

    for poly_idx, poly in enumerate(mesh.polygons):
        if not x_dict["xof_header"] == "xof 0302txt 0064":
            poly.material_index = mesh_dict["material_indices"][poly_idx]

        for loop_index in poly.loop_indices:
            vert_index = mesh.loops[loop_index].vertex_index
            if not x_dict["xof_header"] == "xof 0302txt 0064":
                i, j, k = mesh_dict["normals"][vert_index]
                loop_normals.append(PM_IMPORT @ Vector((i, j, k)))

            u, v = mesh_dict["texcoords"][vert_index]
            uv_render.data[loop_index].uv = (u, 1 - v)

    if not is_simple:
        for skin_weight in mesh_dict["skin_weights"]:
            group_name = skin_weight["bone"]
            if not group_name in object_mesh.vertex_groups.keys():
                object_mesh.vertex_groups.new(name = group_name)

            for skin_idx, skin_element in enumerate(skin_weight["indices"]):
                group_index = object_mesh.vertex_groups.keys().index(group_name)
                object_mesh.vertex_groups[group_index].add([skin_element], skin_weight["weights"][skin_idx], 'ADD')

    if not x_dict["xof_header"] == "xof 0302txt 0064":
        mesh.normals_split_custom_set(loop_normals)

    entity_mesh = mesh
    if not is_simple:
        entity_mesh = object_mesh

    return entity_mesh

def x_matrix_to_blender(mat):
    loc, rot, scl = Matrix((mat[0:4], mat[4:8], mat[8:12], mat[12:16])).transposed().decompose()
    return Matrix.LocRotScale(PM_IMPORT @ Vector(loc), Quaternion(rot), Vector((1, 1, 1)))

def blender_matrix_to_x(mat):
    loc, rot, scl = mat.decompose()
    b_matrix = Matrix.LocRotScale(Matrix.Scale(160, 4) @ Vector(flip(loc)), Quaternion(flip(rot)), Vector(flip(scl))).transposed()
    matrix_array = []
    for row in b_matrix:
        for element in row:
            matrix_array.append(element)

    return matrix_array

def create_bone(filepath, rigid_obs, arm_ob, x_dict, frame, parent_bone=None, bm=None, ob_data=None, is_simple=False, material_list=[], local_asset_path="", error_log=set(), random_color_gen=None):
    name = frame["name"]
    world_transform = x_matrix_to_blender(frame["transform"])

    bone = None
    bone_name = None
    if not is_simple:
        bone = arm_ob.data.edit_bones.new(name)
        bone_name = bone.name
        if parent_bone:
            bone.head = parent_bone.tail
        else:
            bone.head = (0, 0, 0)

        bone.tail = bone.head + Vector((0, 0.1, 0))
        if parent_bone:
            bone.parent = parent_bone

        bone.matrix = world_transform

    for mesh_dict in frame["meshes"]:
        object_mesh = create_object(arm_ob, bone, x_dict, mesh_dict, ob_data, is_simple, world_transform, material_list, local_asset_path, error_log, random_color_gen)
        if is_simple:
            bm.from_mesh(object_mesh)
            bpy.data.meshes.remove(object_mesh)

        rigid_obs.append([object_mesh, bone_name, world_transform])

    for child in frame.get("children", []):
        create_bone(filepath, rigid_obs, arm_ob, x_dict, child, bone, bm, ob_data, is_simple, material_list, local_asset_path, error_log, random_color_gen)

def get_linked_node(node, input_name, search_type):
    linked_node = None
    node_input = node.inputs[input_name]
    if node_input.is_linked:
        for node_link in node_input.links:
            if node_link.from_node.type == search_type:
                linked_node = node_link.from_node
                break

    return linked_node

def get_skeleton_tree(active_ob, frame_dict, bone_transforms, rigid_ob_dict, depsgraph, parent_bone=None):
    for bone in active_ob.pose.bones:
        if bone.parent == parent_bone:
            bone_dict = {
                "name": bone.name,
                "transform": [],
                "meshes": [],
                "children": []
            }

            rigid_obs = rigid_ob_dict.get(bone.name)
            if rigid_obs is not None:
                for rigid_ob in rigid_obs:
                    process_mesh(bone_dict["meshes"], bone_transforms, active_ob, rigid_ob, depsgraph)

            bone_dict["transform"] = blender_matrix_to_x(bone_transforms.get(bone.name))
            get_skeleton_tree(active_ob, bone_dict["children"], bone_transforms, rigid_ob_dict, depsgraph, bone)

            frame_dict.append(bone_dict)

def process_mesh(ob_dict, bone_transforms, armature, ob, depsgraph):
    ob_eval = ob.evaluated_get(depsgraph)
    mesh = ob_eval.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.calc_loop_triangles()
    pivot_matrix = Matrix.Rotation(radians(-90), 4, 'X') @  Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Scale(160.0, 4)

    uv_layer = None
    uv_count = len(mesh.uv_layers)
    if mesh.uv_layers.active:
        uv_layer = mesh.uv_layers.active
    if uv_count > 0:
        uv_layer = mesh.uv_layers[0]

    mesh_dict = {
        "name": ob.name,
        "vertices": [],
        "faces": [],
        "normals": [],
        "normal_indices": [],
        "texcoords": [],
        "dup_preexport_count": 0,
        "dup_indices": [],
        "material_indices": [],
        "materials": [],
        "max_weights_per_vertex": 1,
        "max_weights_per_face": 1,
        "group_count": 0,
        "skin_weights": []
    }

    mesh_dict["dup_preexport_count"] = len(mesh.vertices)

    original_vertex_map = {}
    original_vertices = []
    vertex_map = {}
    for tri in mesh.loop_triangles:
        tri_indices = []
        mat_idx = tri.material_index
        mesh_dict["material_indices"].append(mat_idx)
        for loop_index in tri.loops:
            loop = mesh.loops[loop_index]
            v = mesh.vertices[loop.vertex_index]
            i, j, k  = Matrix.Rotation(radians(-90), 4, 'X') @  Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ loop.normal
            loop_normal = (i, j, k)

            pos = pivot_matrix @ v.co

            uv = (0.0, 0.0)
            if uv_layer:
                u0, v0 = uv_layer.data[loop_index].uv
                uv = (u0, 1 - v0)

            pos_key = (round(pos.x, 6), round(pos.y, 6), round(pos.z, 6))

            if pos_key not in original_vertex_map:
                original_vertex_map[pos_key] = len(original_vertices)
                original_vertices.append(pos_key)

            original_index = original_vertex_map[pos_key]

            expanded_key = (pos_key, uv, loop_normal)

            if expanded_key not in vertex_map:
                vertex_map[expanded_key] = len(mesh_dict["vertices"])
                mesh_dict["vertices"].append(pos)
                mesh_dict["texcoords"].append(uv)
                mesh_dict["normals"].append(loop_normal)
                mesh_dict["dup_indices"].append(original_index)

            tri_indices.append(vertex_map[expanded_key])

        mesh_dict["faces"].append(tri_indices[::-1])
        mesh_dict["normal_indices"].append(tri_indices[::-1])

    if ob.parent_type == 'BONE':
        bone_dict = {
            "bone": None,
            "indices": [],
            "weights": [],
            "transform": []
            }

        valid_length = len(ob.parent_bone) > 0
        bone_exists = False
        for bone in armature.data.bones:
            if bone.name == ob.parent_bone:
                bone_exists = True

        if valid_length and bone_exists:
            bone_name = ob.parent_bone
        else:
            bone_name = armature.data.bones[0]

        vert_count = len(mesh_dict["vertices"])
        bone_dict["bone"] = bone_name
        bone_dict["indices"] = [idx for idx in range(vert_count)]
        bone_dict["weights"] = [1.0 for idx in range(vert_count)]
        bone_dict["transform"] = blender_matrix_to_x(bone_transforms.get(bone_name))
        mesh_dict["skin_weights"].append(bone_dict)

    mesh_dict["group_count"] = len(mesh_dict["skin_weights"])

    for slot in ob.material_slots:
        material_dict = {"name": None,
                        "diffuse": (0.0, 0.0, 0.0, 0.0),
                        "power": 0.0,
                        "specular": (0.0, 0.0, 0.0),
                        "emissive": (0.0, 0.0, 0.0),
                        "texture": None
                        }

        mat = slot.material
        if mat is not None:
            output_material_node = get_output_material_node(mat)
            bdsf_principled = get_linked_node(output_material_node, "Surface", "BSDF_PRINCIPLED")
            node_group = get_linked_node(output_material_node, "Surface", "GROUP")
            if node_group and node_group.node_tree.name == "x_material":
                image_node = get_linked_node(node_group, "Light Map", "TEX_IMAGE")
                dr, dg, db, da = node_group.inputs["Diffuse Overlay"].default_value
                sr, sg, sb, sa = node_group.inputs["Specular"].default_value
                er, eg, eb, ea = node_group.inputs["Emission"].default_value


                material_dict["name"] = mat.name
                material_dict["diffuse"] = (dr, dg, db, da)
                material_dict["power"] = node_group.inputs["Power"].default_value
                material_dict["specular"] = (sr, sg, sb)
                material_dict["emissive"] = (er, eg, eb)
                if image_node and image_node.image:
                    material_dict["texture"] = os.path.basename(bpy.path.abspath(image_node.image.filepath))

            elif bdsf_principled:
                dr, dg, db, da = bdsf_principled.inputs["Base Color"].default_value
                da = bdsf_principled.inputs["Alpha"].default_value
                sr = sg = sb = bdsf_principled.inputs["Specular IOR Level"].default_value
                er, eg, eb, ea = bdsf_principled.inputs["Emission Color"].default_value
                image_node = get_linked_node(bdsf_principled, "Base Color", "TEX_IMAGE")

                material_dict["name"] = mat.name
                material_dict["diffuse"] = (dr, dg, db, da)
                material_dict["power"] = (2 / (bdsf_principled.inputs["Roughness"].default_value * bdsf_principled.inputs["Roughness"].default_value)) - 2
                material_dict["specular"] = (sr, sg, sb)
                material_dict["emissive"] = (er, eg, eb)
                if image_node and image_node.image:
                    material_dict["texture"] = os.path.basename(bpy.path.abspath(image_node.image.filepath))

        mesh_dict["materials"].append(material_dict)

    ob_dict.append(mesh_dict)

def export_scene(context, output_path, file_version, report):
    if context.view_layer.objects.active is not None:
        bpy.ops.object.mode_set(mode='OBJECT')

    active_ob = context.object
    if active_ob and active_ob.type == 'ARMATURE' and len(active_ob.data.bones) > 0:
        x_dict = {
            "xof_header": None,
            "templates": [],
            "anim_ticks_per_second": None,
            "materials": [],
            "frames": [],
            "meshes": [],
            "animation_set": []
        }

        x_dict["xof_header"] = "xof 0303txt 0032"

        skinned_ob_list = []
        rigid_ob_dict = {}
        depsgraph = context.evaluated_depsgraph_get()
        for ob in bpy.data.objects:
            if ob.type == "MESH":
                if ob.parent_type == 'OBJECT' and ob.parent == active_ob:
                    skinned_ob_list.append(ob)
                elif ob.parent_type == 'BONE' and ob.parent == active_ob and len(ob.parent_bone) > 0:
                    rigid_ob_list = rigid_ob_dict.get(ob.parent_bone)
                    if rigid_ob_list is None:
                        rigid_ob_list = rigid_ob_dict[ob.parent_bone] = []
                    rigid_ob_list.append(ob)
        bone_transforms = {}
        for bone in active_ob.data.bones:
            bone_transforms[bone.name] = active_ob.matrix_world @ bone.matrix_local

        bpy.ops.object.mode_set(mode = 'POSE')
        get_skeleton_tree(active_ob, x_dict["frames"], bone_transforms, rigid_ob_dict, depsgraph, None)
        bpy.ops.object.mode_set(mode = 'OBJECT')
        for skinned_ob in skinned_ob_list:
            process_mesh(x_dict["meshes"], bone_transforms, active_ob, skinned_ob, depsgraph)

        write_x(x_dict, output_path)

    else:
        report({'ERROR'}, "No armature selected. Export will now be aborted")
        return {'CANCELLED'}

    report({'INFO'}, "Export completed successfully")
    return {'FINISHED'}

def import_scene(context, filepath, report, bm=None, ob_data=None, is_simple=False, error_log=None, random_color_gen=None):
    material_list = []
    x_dict = read_x(filepath)
    if x_dict:
        if error_log is None:
            error_log = set()
        if random_color_gen is None:
            random_color_gen = RandomColorGenerator() # generates a random sequence of colors

        game_path = Path(bpy.context.preferences.addons["io_scene_cb"].preferences.game_path)

        local_asset_path = ""
        if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
            local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

        arm_ob = None
        if not is_simple:
            arm_data = bpy.data.armatures.new("Armature")
            arm_ob = bpy.data.objects.new("Armature", arm_data)
            context.collection.objects.link(arm_ob)

            context.view_layer.objects.active = arm_ob
            bpy.ops.object.mode_set(mode='EDIT')

        if x_dict["xof_header"] == "xof 0302txt 0064":
            for material_dict in x_dict["materials"]:
                material = bpy.data.materials.new(name=material_dict["name"])
                material.diffuse_color = random_color_gen.next()

                material.use_nodes = True
                for node in material.node_tree.nodes:
                    material.node_tree.nodes.remove(node)

                output_material_node = get_output_material_node(material)
                output_material_node.location = Vector((0.0, 0.0))

                x_node = get_shader_node(material.node_tree, SHADER_RESOURCES, "x_material")
                x_node.name = "X Material"
                x_node.location = (-440.0, 0.0)

                connect_inputs(material.node_tree, x_node, "Shader", output_material_node, "Surface")

                sr, sg, sb = material_dict["specular"]
                er, eg, eb = material_dict["emissive"]
                x_node.inputs["Diffuse Overlay"].default_value = material_dict["diffuse"]
                x_node.inputs["Power"].default_value = material_dict["power"]
                x_node.inputs["Specular"].default_value = (sr, sg, sb, 1)
                x_node.inputs["Emission"].default_value = (er, eg, eb, 1)

                texture_node = get_file(material_dict["texture"], True, True, directory_path=local_asset_path)
                if texture_node:
                    texture = material.node_tree.nodes.new("ShaderNodeTexImage")
                    texture.location = (-720.0, 0)
                    texture.image = texture_node
                    connect_inputs(material.node_tree, texture, "Color", x_node, "Diffuse Map")
                    connect_inputs(material.node_tree, texture, "Alpha", x_node, "Diffuse Map Alpha")

                    texture_bump_data = get_file("%sbump" % os.path.basename(material_dict["texture"]).rsplit(".", 1)[0], directory_path=local_asset_path)
                    if texture_bump_data:
                        texture_bump = material.node_tree.nodes.new("ShaderNodeTexImage")
                        texture_bump.image = texture_bump_data
                        texture_bump.image.alpha_mode = 'CHANNEL_PACKED'
                        texture_bump.interpolation = 'Cubic'
                        texture_bump.image.colorspace_settings.name = 'Non-Color'
                        texture_bump.location = (-720.0, -380)
                        connect_inputs(material.node_tree, texture_bump, "Color", x_node, "Normal Map")
                        connect_inputs(material.node_tree, texture_bump, "Alpha", x_node, "Normal Map Alpha")

                else:
                    if material_dict["texture"] is not None:
                        error_log.add('Failed to retrive "%s"' % material_dict["texture"])

                material_list.append(material)

        rigid_obs = []
        for bone in x_dict["frames"]:
            create_bone(filepath, rigid_obs, arm_ob, x_dict, bone, None, bm, ob_data, is_simple, material_list, local_asset_path, error_log, random_color_gen)

        if not is_simple:
            bpy.ops.object.mode_set(mode='OBJECT')
            context.view_layer.update()
            for rigid_ob in rigid_obs:
                object_mesh, parent_bone_name, transform = rigid_ob
                object_mesh.parent_type = 'BONE'
                object_mesh.parent_bone = parent_bone_name
                object_mesh.matrix_world = transform

        if not x_dict["xof_header"] == "xof 0302txt 0064":
            for mesh_dict in x_dict["meshes"]:
                object_mesh = create_object(arm_ob, None, x_dict, mesh_dict, ob_data, is_simple, None, material_list, local_asset_path, error_log, random_color_gen)
                if is_simple:
                    bm.from_mesh(object_mesh)
                    bpy.data.meshes.remove(object_mesh)

        if not is_simple:
            for error in error_log:
                report({'WARNING'}, error)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
