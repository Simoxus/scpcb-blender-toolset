import os
import bpy
import bmesh

from pathlib import Path
from .process_b3d import B3DTree
from mathutils import Matrix, Vector
from bpy_extras.io_utils import unpack_list
from bpy_extras.image_utils import load_image

def flip(v):
    return ((v[0],v[2],v[1]) if len(v)<4 else (v[0], v[1],v[3],v[2]))

def flip_all(v):
    return [y for y in [flip(x) for x in v]]

def import_mesh(node, material_mapping, bm):
    mesh = bpy.data.meshes.new("temp_mesh")

    # join face arrays
    faces = []
    for face in node.faces:
        faces.extend(face.indices)

    vertices = [Matrix.Scale(-0.00625, 4) @ Vector(vertex) for vertex in node.vertices]

    # create mesh from data
    mesh.from_pydata(vertices, [], flip_all(faces))
    for poly in mesh.polygons:
        poly.use_smooth = True

    # assign normals
    mesh.vertices.foreach_set('normal', unpack_list(node.normals))

    # assign uv coordinates
    uvs = [(0,0) if len(uv)==0 else (uv[0], 1-uv[1]) for uv in node.uvs]
    uvlist = [i for poly in mesh.polygons for vidx in poly.vertices for i in uvs[vidx]]
    mesh.uv_layers.new().data.foreach_set('uv', uvlist)

    # adding object materials (insert-ordered)
    for key, value in material_mapping.items():
        mesh.materials.append(bpy.data.materials[value])

    # assign material_indexes
    poly = 0
    for face in node.faces:
        for _ in face.indices:
            mesh.polygons[poly].material_index = face.brush_id
            poly += 1

    bm.from_mesh(mesh)
    bpy.data.meshes.remove(mesh)

def import_node_recursive(node, material_mapping, bm):
    if 'vertices' in node and 'faces' in node:
        import_mesh(node, material_mapping, bm)

    for x in node.nodes:
        import_node_recursive(x, material_mapping, bm)

def export_scene(context, filepath, report):
    print()

def import_scene(context, filepath, report):
    images = {}
    material_mapping = {}
    IMAGE_SEARCH=True

    ob_data = bpy.data.meshes.new("model")
    data = B3DTree().parse(Path(filepath))
    for i, texture in enumerate(data['textures'] if 'textures' in data else []):
        texture_name = os.path.basename(texture['name'])
        for mat in data.materials:
            if mat.tids[0]==i:
                images[i] = (texture_name, load_image(texture_name, bpy.context.preferences.addons["io_scene_rmesh"].preferences.game_path, check_existing=True,
                    place_holder=False, recursive=IMAGE_SEARCH))


    for i, mat in enumerate(data.materials if 'materials' in data else []):
        material = bpy.data.materials.new(mat.name)
        #material.diffuse_color = random_color_gen.next()
        material_mapping[i] = material.name
        #material.diffuse_color = mat.rgba #B3D models have a material color but we're not exporting these so who cares.
        material.blend_method = 'BLEND' if mat.rgba[3] < 1.0 else 'OPAQUE'

        tid = mat.tids[0] if len(mat.tids) else -1

        if tid in images:
            name, image = images[tid]
            texture = bpy.data.textures.new(name=name, type='IMAGE')
            material.use_nodes = True
            bsdf = material.node_tree.nodes["Principled BSDF"]
            texImage = material.node_tree.nodes.new('ShaderNodeTexImage')
            texImage.image = image
            material.node_tree.links.new(bsdf.inputs['Base Color'], texImage.outputs['Color'])

    for key, value in material_mapping.items():
        ob_data.materials.append(bpy.data.materials[value])

    bm = bmesh.new()
    import_node_recursive(data, material_mapping, bm)
    bm.to_mesh(ob_data)
    bm.free()

    object_mesh = bpy.data.objects.new("model", ob_data)
    bpy.context.collection.objects.link(object_mesh)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
