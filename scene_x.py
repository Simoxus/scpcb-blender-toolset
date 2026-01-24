import os
import bpy

from math import sqrt, radians
from pathlib import Path
from mathutils import Matrix, Vector
from .process_x import write_x, read_x
from .common_functions import RandomColorGenerator, get_file, is_string_empty

def create_object(arm_ob, parent_bone, x_dict, mesh_dict, ob_data=None, is_simple=False, world_transform=None, material_list=[], local_asset_path="", error_log=set(), random_color_gen=None):
    mesh_name = mesh_dict["name"]
    if mesh_name == None:
        if parent_bone is not None:
            mesh_name = parent_bone.name
        else:
            mesh_name = "mesh"

    pivot_matrix = Matrix.Rotation(radians(90), 4, 'X') @ Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Scale(0.00625, 4)
    mesh = bpy.data.meshes.new(mesh_name)

    vertices = [Vector(vertex) for vertex in mesh_dict["vertices"]]
    triangles = [triangle[::-1] for triangle in mesh_dict["faces"]]
    mesh.from_pydata(vertices, [], triangles)
    mesh.transform(pivot_matrix)
    if not is_simple:
        object_mesh = bpy.data.objects.new(mesh_name, mesh)
        bpy.context.collection.objects.link(object_mesh)
        object_mesh.parent = arm_ob
    else:
        if world_transform is not None:
            mesh.transform(world_transform)

    uv_render = mesh.uv_layers.new(name="UVMap_Render")
    for poly_idx, poly in enumerate(mesh.polygons):
        poly.use_smooth = True

    if not x_dict["xof_header"] == "xof 0302txt 0064":
        for material_dict in mesh_dict["materials"]:
            mat = bpy.data.materials.new(name=material_dict["name"])
            mat.diffuse_color = random_color_gen.next()

            mesh.materials.append(mat)
            if is_simple:
                ob_data.materials.append(mat)

            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')

            r, g, b, a = material_dict["diffuse"]
            #mat.diffuse_color = (r, g, b, a) # Need to find another place to store this if base color doesn't do. I rather have different colors for materials in the viewport. - Gen
            bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
            bsdf.inputs["Alpha"].default_value = a
            if a < 1.0:
                mat.blend_method = 'BLEND'
            else:
                mat.blend_method = 'CLIP'

            roughness = sqrt(2 / (material_dict["power"] + 2))
            #bsdf.inputs["Roughness"].default_value = roughness # This doesn't look like what I see ingame - Gen

            sr, sg, sb = material_dict["specular"]
            spec_strength = max(sr, sg, sb)
            #bsdf.inputs["Specular IOR Level"].default_value = spec_strength # This doesn't look like what I see ingame - Gen

            er, eg, eb = material_dict["emissive"]
            #bsdf.inputs["Emission Color"].default_value = (er, eg, eb, 1.0) # This doesn't look like what I see ingame - Gen
            
            texture_node = get_file(material_dict["texture"], True, True, directory_path=local_asset_path)
            if texture_node:
                texture = mat.node_tree.nodes.new("ShaderNodeTexImage")
                texture.location = (-300, 150)
                texture.image = texture_node
                mat.node_tree.links.new(bsdf.inputs['Base Color'], texture.outputs['Color'])
            else:
                if material_dict["texture"] is not None:
                    error_log.add('Failed to retrive "%s"' % material_dict["texture"])

    else:
        for mat in material_list:
            mesh.materials.append(mat)
            if is_simple:
                ob_data.materials.append(mat)

    loop_normals = [Vector((0.0, 0.0, 1.0))] * len(mesh.loops)
    if x_dict["xof_header"] == "xof 0302txt 0064":
        for mat_data_idx, material_face in enumerate(mesh_dict["material_indices"]):
            material_index = 0
            material_data = mesh_dict["materials"][mat_data_idx]
            for mat_idx, material in enumerate(material_list):
                if material.name == material_data["name"]:
                    material_index = mat_idx

            mesh.polygons[material_face].material_index = material_index

    for poly_idx, poly in enumerate(mesh.polygons):
        if not x_dict["xof_header"] == "xof 0302txt 0064":
            poly.material_index = mesh_dict["material_indices"][poly_idx]

        for loop_index in poly.loop_indices:
            vert_index = mesh.loops[loop_index].vertex_index
            if not x_dict["xof_header"] == "xof 0302txt 0064":
                loop_normals[loop_index] = -Vector(mesh_dict["normals"][vert_index])

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

    #if not x_dict["xof_header"] == "xof 0302txt 0064":
        # I need to look at this more. I don't think I'm applying these right. - Gen
        #mesh.normals_split_custom_set(loop_normals)

    entity_mesh = mesh
    if not is_simple:
        entity_mesh = object_mesh

    return entity_mesh

def x_matrix_to_blender(mat):
    r0 = mat[0]
    r1 = mat[1]
    r2 = mat[2]
    o0 = mat[3]
    r3 = mat[4]
    r4 = mat[5]
    r5 = mat[6]
    o1 = mat[7]
    r6 = mat[8]
    r7 = mat[9]
    r8 = mat[10]
    o2 = mat[11]
    t0 = mat[12]
    t1 = mat[13]
    t2 = mat[14]
    o3 = mat[15]

    matrix = [
        [r0, r1, r2, t0],
        [r3, r4, r5, t1],
        [r6, r7, r8, t2],
        [o0, o1, o2, o3]
    ]

    return Matrix(matrix)

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

        pivot_matrix = Matrix.Rotation(radians(90), 4, 'X') @ Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Scale(0.00625, 4)
        bone.matrix = pivot_matrix @ world_transform

    for mesh_dict in frame["meshes"]:
        object_mesh = create_object(arm_ob, bone, x_dict, mesh_dict, ob_data, is_simple, world_transform, material_list, local_asset_path, error_log, random_color_gen)
        if is_simple:
            bm.from_mesh(object_mesh)
            bpy.data.meshes.remove(object_mesh)

        rigid_obs.append([object_mesh, bone_name, world_transform])

    for child in frame.get("children", []):
        create_bone(filepath, rigid_obs, arm_ob, x_dict, child, bone, bm, ob_data, is_simple, material_list, local_asset_path, error_log, random_color_gen)

def export_scene(context, output_path, report):
    is_binary = False
    is_compressed = False
    with output_path.open("wb") as x_stream:
        if is_binary:
            print("NOT SUPPORTED")
        else:
            x_stream.write("xof 0303txt 0032\n")

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

        game_path = Path(bpy.context.preferences.addons["io_scene_rmesh"].preferences.game_path)

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
                mat = bpy.data.materials.new(name=material_dict["name"])
                mat.diffuse_color = random_color_gen.next()

                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                bsdf = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')

                r, g, b, a = material_dict["diffuse"]
                #mat.diffuse_color = (r, g, b, a) # Need to find another place to store this if base color doesn't do. I rather have different colors for materials in the viewport. - Gen
                bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
                bsdf.inputs["Alpha"].default_value = a
                if a < 1.0:
                    mat.blend_method = 'BLEND'
                else:
                    mat.blend_method = 'CLIP'

                roughness = sqrt(2 / (material_dict["power"] + 2))
                #bsdf.inputs["Roughness"].default_value = roughness # This doesn't look like what I see ingame - Gen

                sr, sg, sb = material_dict["specular"]
                spec_strength = max(sr, sg, sb)
                #bsdf.inputs["Specular IOR Level"].default_value = spec_strength # This doesn't look like what I see ingame - Gen

                er, eg, eb = material_dict["emissive"]
                #bsdf.inputs["Emission Color"].default_value = (er, eg, eb, 1.0) # This doesn't look like what I see ingame - Gen
                
                texture_node = get_file(material_dict["texture"], True, True, directory_path=local_asset_path)
                if texture_node:
                    texture = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    texture.location = (-300, 150)
                    texture.image = texture_node
                    mat.node_tree.links.new(bsdf.inputs['Base Color'], texture.outputs['Color'])

                else:
                    if material_dict["texture"] is not None:
                        error_log.add('Failed to retrive "%s"' % material_dict["texture"])

                material_list.append(mat)

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
