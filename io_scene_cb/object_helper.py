import os
import bpy
import bmesh

from math import radians
from pathlib import Path
from enum import Enum, auto
from mathutils import Matrix, Vector, Euler
from .scene_x import import_scene as import_x
from .scene_b3d import import_scene as import_b3d

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

def CreateObject(ob_bm, ob_data, ob_transform, model_path):
    if str(model_path).lower().endswith(".x"):
        material_count = len(ob_data.materials)

        temp_data = bpy.data.meshes.new("door_entity")
        bm = bmesh.new()
        is_simple=True
        import_x(bpy.context, model_path, print, bm, ob_data, is_simple)
        for f in bm.faces:
            f.material_index = material_count + f.material_index

        bm.to_mesh(temp_data)
        temp_data.transform(ob_transform)
        ob_bm.from_mesh(temp_data)
        bm.free()
        bpy.data.meshes.remove(temp_data)

    if str(model_path).lower().endswith(".b3d"):
        material_count = len(ob_data.materials)

        temp_data = bpy.data.meshes.new("door_entity")
        bm = bmesh.new()
        is_simple=True
        import_b3d(bpy.context, model_path, print, bm, ob_data, is_simple)
        for f in bm.faces:
            f.material_index = material_count + f.material_index

        bm.to_mesh(temp_data)
        temp_data.transform(ob_transform)
        ob_bm.from_mesh(temp_data)
        bm.free()
        bpy.data.meshes.remove(temp_data)

def create_door(door_type=DoorType.normal, button_type=ButtonType.normal, door_state=DoorState.closed):
    ob_data = bpy.data.meshes.new("door_entity")
    ob_bm = bmesh.new()

    game_path = bpy.context.preferences.addons[__package__].preferences.game_path
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
        x = 1.1528

    if door_type == DoorType.big:
        x = 0
        if not door_state == DoorState.closed:
            x = 1.2732

        ob_matrix = Matrix.LocRotScale(Vector((-x, 0.0002, -0.03263)), Euler((0, 0, 0)), Vector((55, 55, 55)) * RoomScale)
        CreateObject(ob_bm, ob_data, ob_matrix, BigDoorLeftPath)
        ob_matrix = Matrix.LocRotScale(Vector((x, 0.0002, -0.03263)), Euler((0, 0, 0)), Vector((55, 55, 55)) * RoomScale)
        CreateObject(ob_bm, ob_data, ob_matrix, BigDoorRightPath)

    elif door_type == DoorType.heavy:
        ob_matrix = Matrix.LocRotScale(Vector((-x, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        CreateObject(ob_bm, ob_data, ob_matrix, HeavyDoorLeftPath)
        ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((0, 0, radians(180))), Vector((1, 1, 1)))
        CreateObject(ob_bm, ob_data, ob_matrix, HeavyDoorRightPath)
        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        CreateObject(ob_bm, ob_data, ob_matrix, DoorFramePath)

    elif door_type == DoorType.elevator:
        ob_matrix = Matrix.LocRotScale(Vector((-x, 0, 0)), Euler((radians(0), 0, radians(180))), Vector((1, 1, 1)))
        CreateObject(ob_bm, ob_data, ob_matrix, ElevatorDoorsPath)
        ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((radians(0), 0, radians(0))), Vector((1, 1, 1)))
        CreateObject(ob_bm, ob_data, ob_matrix, ElevatorDoorsPath)
        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        CreateObject(ob_bm, ob_data, ob_matrix, DoorFramePath)

    else:
        sx = (204.0 * 0.00625) * RoomScale / 0.0693
        sy = (16.0 * 0.00625) * RoomScale / 0.0066
        sz = (312.0 * 0.00625) * RoomScale / 0.1518
        ob_matrix = Matrix.LocRotScale(Vector((-x, -0.05, 0)), Euler((0, 0, 0)), Vector((sx, sy, sz)))
        CreateObject(ob_bm, ob_data, ob_matrix, DoorPath)
        ob_matrix = Matrix.LocRotScale(Vector((x, 0.05, 0)), Euler((0, 0, radians(180))), Vector((sx, sy, sz)))
        CreateObject(ob_bm, ob_data, ob_matrix, DoorPath)
        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        CreateObject(ob_bm, ob_data, ob_matrix, DoorFramePath)

    if door_type == DoorType.big:
        ob_matrix = Matrix.LocRotScale(Vector((-2.70001, 1.2, 1.12)), Euler((0, 0, radians(-90))), Vector((7.7, 7.7, 7.7)))
        CreateObject(ob_bm, ob_data, ob_matrix, ButtonPath)
        ob_matrix = Matrix.LocRotScale(Vector((3.1, -0.6, 1.12)), Euler((0, 0, radians(180))), Vector((7.7, 7.7, 7.7)))
        CreateObject(ob_bm, ob_data, ob_matrix, ButtonPath)

    else:
        ob_matrix = Matrix.LocRotScale(Vector((-0.959999, 0.16, 1.12)), Euler((0, 0, 0)), Vector((7.7, 7.7, 7.7)))
        CreateObject(ob_bm, ob_data, ob_matrix, ButtonPath)
        ob_matrix = Matrix.LocRotScale(Vector((0.959999, -0.16, 1.12)), Euler((0, 0, radians(180))), Vector((7.7, 7.7, 7.7)))
        CreateObject(ob_bm, ob_data, ob_matrix, ButtonPath)

    ob_bm.to_mesh(ob_data)
    ob_bm.free()

    return ob_data
