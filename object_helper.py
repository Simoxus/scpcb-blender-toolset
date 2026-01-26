import os
import bpy
import bmesh

from math import radians
from pathlib import Path
from mathutils import Matrix, Vector, Euler
from enum import Flag, Enum, auto
from io_scene_rmesh.scene_x import import_scene as import_x
from io_scene_rmesh.process_b3d import B3DTree
from io_scene_rmesh.scene_b3d import import_node_recursive
from bpy_extras.image_utils import load_image

RoomScale = 1

class DoorType(Enum):
    normal = 0
    big = auto()
    heavy = auto()
    elevator = auto()

class ButtonType(Enum):
    normal = 0
    code = auto()
    keycard = auto()
    scanner = auto()

class DoorState(Enum):
    closed = 0
    open = auto()
    broken = auto()

def CreateObject(model_path, model_name="mesh"):
    if str(model_path).lower().endswith(".x"):
        ob_data = bpy.data.meshes.new(model_name)
        bm = bmesh.new()
        is_simple=True
        import_x(bpy.context, model_path, print, bm, ob_data, is_simple)
        bm.to_mesh(ob_data)
        bm.free()

    if str(model_path).lower().endswith(".b3d"):
        images = {}
        material_mapping = {}
        IMAGE_SEARCH=True

        ob_data = bpy.data.meshes.new(model_name)
        data = B3DTree().parse(Path(model_path))
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

    object_mesh = bpy.data.objects.new(model_name, ob_data)
    bpy.context.collection.objects.link(object_mesh)

    return object_mesh

def CreateDoor(position=Vector(), angle=0.0, door_type=DoorType.normal, button_type=ButtonType.normal, door_state=DoorState.closed):
    pivot_matrix = Matrix.LocRotScale(position, Euler((0, 0, radians(angle))), Vector((RoomScale, RoomScale, RoomScale)))
    game_path = bpy.context.preferences.addons["io_scene_rmesh"].preferences.game_path
    BigDoorLeftPath = Path(os.path.join(game_path, r"GFX\map\ContDoorLeft.x"))
    BigDoorRightPath = Path(os.path.join(game_path, r"GFX\map\ContDoorRight.x"))
    HeavyDoorLeftPath = Path(os.path.join(game_path, r"GFX\map\heavydoor1.x"))
    HeavyDoorRightPath = Path(os.path.join(game_path, r"GFX\map\heavydoor2.x"))
    ElevatorDoorsPath = Path(os.path.join(game_path, r"GFX\map\elevatordoor.b3d"))
    DoorFramePath = Path(os.path.join(game_path, r"GFX\map\doorframe.x"))
    DoorPath = Path(os.path.join(game_path, r"GFX\map\door01.x"))
    ButtonPath = Path(os.path.join(game_path, r"GFX\map\Button.x"))
    if button_type == ButtonType.code:
        ButtonPath = Path(os.path.join(game_path, r"GFX\map\ButtonCode.x"))
    elif button_type == ButtonType.keycard:
        ButtonPath = Path(os.path.join(game_path, r"GFX\map\ButtonKeycard.x"))
    elif button_type == ButtonType.scanner:
        ButtonPath = Path(os.path.join(game_path, r"GFX\map\ButtonScanner.x"))

    x = 0
    if not door_state == DoorState.closed:
        x = 1.125

    if door_type == DoorType.big:
        x = 0
        if not door_state == DoorState.closed:
            x = 1.1525

        ob = CreateObject(BigDoorLeftPath, "BigLeftDoor")
        ob_matrix = Matrix.LocRotScale(Vector((-x, 0, -0.03263)), Euler((0, 0, 0)), Vector((55, 55, 55)) * RoomScale)
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(BigDoorRightPath, "BigRightDoor")
        ob_matrix = Matrix.LocRotScale(Vector((x, 0, -0.03263)), Euler((0, 0, 0)), Vector((55, 55, 55)) * RoomScale)
        ob.matrix_world = pivot_matrix @ ob_matrix
    
    elif door_type == DoorType.heavy:
        ob = CreateObject(HeavyDoorLeftPath, "HeavyLeftDoor")
        ob_matrix = Matrix.LocRotScale(Vector((-x, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(HeavyDoorRightPath, "HeavyRightDoor")
        ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((0, 0, radians(180))), Vector((1, 1, 1)))
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(DoorFramePath, "DoorFrame")
        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        ob.matrix_world = pivot_matrix @ ob_matrix

    elif door_type == DoorType.elevator:
        ob = CreateObject(ElevatorDoorsPath, "ElevatorLeftDoor")
        ob_matrix = Matrix.LocRotScale(Vector((-x, 0, 0)), Euler((radians(-90), 0, 0)), Vector((1, 1, 1)))
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(ElevatorDoorsPath, "ElevatorRightDoor")
        ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((radians(-90), 0, radians(180))), Vector((1, 1, 1)))
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(DoorFramePath, "DoorFrame")
        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        ob.matrix_world = pivot_matrix @ ob_matrix

    else:
        ob = CreateObject(DoorPath, "DoorLeftDoor")
        sx = (204.0 * 0.00625) * RoomScale / ob.dimensions.x
        sy = (16.0 * 0.00625) * RoomScale / ob.dimensions.y
        sz = (312.0 * 0.00625) * RoomScale / ob.dimensions.z
        ob_matrix = Matrix.LocRotScale(Vector((-x, -0.05, 0)), Euler((0, 0, 0)), Vector((sx, sy, sz)))
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(DoorPath, "DoorRightDoor")
        ob_matrix = Matrix.LocRotScale(Vector((x, 0.05, 0)), Euler((0, 0, radians(180))), Vector((sx, sy, sz)))
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(DoorFramePath, "DoorFrame")
        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        ob.matrix_world = pivot_matrix @ ob_matrix

    if door_type == DoorType.big:
        ob = CreateObject(ButtonPath, "Button")
        ob_matrix = Matrix.LocRotScale(Vector((-2.70001, 1.2, 1.12)), Euler((0, 0, radians(-90))), Vector((7.7, 7.7, 7.7)))
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(ButtonPath, "Button")
        ob_matrix = Matrix.LocRotScale(Vector((3.1, -0.6, 1.12)), Euler((0, 0, radians(180))), Vector((7.7, 7.7, 7.7)))
        ob.matrix_world = pivot_matrix @ ob_matrix

    else:
        ob = CreateObject(ButtonPath, "Button")
        ob_matrix = Matrix.LocRotScale(Vector((-0.959999, 0.16, 1.12)), Euler((0, 0, 0)), Vector((7.7, 7.7, 7.7)))
        ob.matrix_world = pivot_matrix @ ob_matrix
        ob = CreateObject(ButtonPath, "Button")
        ob_matrix = Matrix.LocRotScale(Vector((0.959999, -0.16, 1.12)), Euler((0, 0, radians(180))), Vector((7.7, 7.7, 7.7)))
        ob.matrix_world = pivot_matrix @ ob_matrix

CreateDoor(bpy.context.scene.cursor.location, 0, DoorType.normal, ButtonType.normal, DoorState.closed)
