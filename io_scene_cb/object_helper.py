import os
import bpy
import bmesh

from math import radians
from pathlib import Path
from enum import Enum, auto
from .process_rmesh import ImportFileType
from mathutils import Matrix, Vector, Euler
from .scene_x import import_scene as import_x
from .scene_b3d import import_scene as import_b3d
from .common_functions import ROOMSCALE

# Notes
# Room scale seems to be 0.00390625
# The inverse of this is 256
# In order for the scale value to work in our Blender scene it seems we need to do whatever math the BB asks for and then multiply 256 against the result
# positions seem to be good when doing whatever the bb asks for and then multipling with 1.6 probably cause of the scale stuff we do
# I'm not sure where the other plugin got 0.00625 but the value I pulled from the game might be the real scale I need to set the imported assets to to match the ingame scale.

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

def create_object(ob_bm, ob_data, ob_transform, model_path):
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
        import_b3d(bpy.context, model_path, False, print, bm, ob_data, is_simple)
        for f in bm.faces:
            f.material_index = material_count + f.material_index

        bm.to_mesh(temp_data)
        temp_data.transform(ob_transform)
        ob_bm.from_mesh(temp_data)
        bm.free()
        bpy.data.meshes.remove(temp_data)

def create_door(door_type=DoorType.normal, button_type=ButtonType.normal, door_state=DoorState.closed, door_halved=False, file_type=ImportFileType.rmesh, entity_idx=0, sd_ob=None, sba_ob=None, sbb_ob=None):
    if sd_ob:
        door_ob_data = sd_ob.data

    else:
        door_ob_data = bpy.data.meshes.new("door_entity")

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

    if door_type == DoorType.big:
        x = 0
        if not door_state == DoorState.closed:
            x = 1.2732

        if door_halved:
            ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((0, 0, radians(180))), Vector((55, 55, 55)))
            create_object(ob_bm, door_ob_data, ob_matrix, BigDoorRightPath)
        else:
            ob_matrix = Matrix.LocRotScale(Vector((-x, 0, 0)), Euler((0, 0, radians(180))), Vector((55, 55, 55)))
            create_object(ob_bm, door_ob_data, ob_matrix, BigDoorLeftPath)
            ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((0, 0, radians(180))), Vector((55, 55, 55)))
            create_object(ob_bm, door_ob_data, ob_matrix, BigDoorRightPath)

    elif door_type == DoorType.heavy:
        ax = 0
        bx = 0
        if not door_state == DoorState.closed:
            ax = 0.76
            bx = 1.074

        if door_halved:
            ob_matrix = Matrix.LocRotScale(Vector((bx, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
            create_object(ob_bm, door_ob_data, ob_matrix, HeavyDoorLeftPath)
        else:
            ob_matrix = Matrix.LocRotScale(Vector((-ax, 0, 0)), Euler((0, 0, radians(180))), Vector((1, 1, 1)))
            create_object(ob_bm, door_ob_data, ob_matrix, HeavyDoorRightPath)
            ob_matrix = Matrix.LocRotScale(Vector((bx, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
            create_object(ob_bm, door_ob_data, ob_matrix, HeavyDoorLeftPath)

        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, DoorFramePath)

    elif door_type == DoorType.elevator:
        x = 0
        if not door_state == DoorState.closed:
            x = 0.56

        ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((radians(0), 0, radians(0))), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, ElevatorDoorsPath)
        ob_matrix = Matrix.LocRotScale(Vector((-x, 0, 0)), Euler((radians(0), 0, radians(180))), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, ElevatorDoorsPath)

        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, DoorFramePath)

    else:
        x = 0
        if not door_state == DoorState.closed:
            x = 1.1528

        #Values on the right are hardcoded door01.x model dimensions at roomscale 1. Just easier than having a setup to calculate it from the model file.
        #Values on the left are from the bb game code. - Gen
        sx = (204.0 * ROOMSCALE) * (1 / (11.0814 * ROOMSCALE))
        sy = (16.0 * ROOMSCALE) * (1 /(1.05759 * ROOMSCALE))
        sz = (312.0 * ROOMSCALE) * (1 / (24.2875 * ROOMSCALE))

        if door_halved:
            ob_matrix = Matrix.LocRotScale(Vector((x, 0, 0)), Euler((0, 0, 0)), Vector((sx, sy, sz)))
            create_object(ob_bm, door_ob_data, ob_matrix, DoorPath)
        else:
            ob_matrix = Matrix.LocRotScale(Vector((-x, -0.05, 0)), Euler((0, 0, radians(180))), Vector((sx, sy, sz)))
            create_object(ob_bm, door_ob_data, ob_matrix, DoorPath)
            ob_matrix = Matrix.LocRotScale(Vector((x, 0.05, 0)), Euler((0, 0, 0)), Vector((sx, sy, sz)))
            create_object(ob_bm, door_ob_data, ob_matrix, DoorPath)

        ob_matrix = Matrix.LocRotScale(Vector((0, 0, 0)), Euler((0, 0, 0)), Vector((1, 1, 1)))
        create_object(ob_bm, door_ob_data, ob_matrix, DoorFramePath)

    ob_bm.to_mesh(door_ob_data)
    ob_bm.free()

    if sd_ob:
        door_ob = sd_ob

    else:
        door_ob = bpy.data.objects.new("%s door" % entity_idx, door_ob_data)

    if sba_ob:
        button_a_ob_data = sba_ob.data

    else:
        button_a_ob_data = bpy.data.meshes.new("button_a_entity")

    if sba_ob:
        button_b_ob_data = sbb_ob.data

    else:
        button_b_ob_data = bpy.data.meshes.new("button_b_entity")

    button_a_ob_bm = bmesh.new()
    button_b_ob_bm = bmesh.new()
    ob_bm = bmesh.new()
    button_scale = Vector((7.68, 7.68, 7.68))
    if door_type == DoorType.big:
        create_object(button_a_ob_bm, button_a_ob_data, Matrix(), ButtonPath)
        create_object(button_b_ob_bm, button_b_ob_data, Matrix(), ButtonPath)
        button_a_ob_bm.to_mesh(button_a_ob_data)
        button_a_ob_bm.free()
        button_b_ob_bm.to_mesh(button_b_ob_data)
        button_b_ob_bm.free()

        ob_a_matrix = Matrix.LocRotScale(Vector((2.7, -1.2, 1.12)), Euler((0, 0, radians(-90))), button_scale)
        ob_b_matrix = Matrix.LocRotScale(Vector((-2.7, 1.2, 1.12)), Euler((0, 0, radians(90))), button_scale)
        if sba_ob:
            button_a_ob = sba_ob

        else:
            button_a_ob = bpy.data.objects.new("%s door_button_a" % entity_idx, button_a_ob_data)
            button_a_ob.parent = door_ob
            button_a_ob.matrix_world = ob_a_matrix

        if sbb_ob:
            button_b_ob = sbb_ob

        else:
            button_b_ob = bpy.data.objects.new("%s door_button_b" % entity_idx, button_b_ob_data)
            button_b_ob.parent = door_ob
            button_b_ob.matrix_world = ob_b_matrix

    else:
        create_object(button_a_ob_bm, button_a_ob_data, Matrix(), ButtonPath)
        create_object(button_b_ob_bm, button_b_ob_data, Matrix(), ButtonPath)
        button_a_ob_bm.to_mesh(button_a_ob_data)
        button_a_ob_bm.free()
        button_b_ob_bm.to_mesh(button_b_ob_data)
        button_b_ob_bm.free()

        ob_a_matrix = Matrix.LocRotScale(Vector((0.96, -0.16, 1.12)), Euler((0, 0, 0)), button_scale)
        ob_b_matrix = Matrix.LocRotScale(Vector((-0.96, 0.16, 1.12)), Euler((0, 0, radians(180))), button_scale)

        if sba_ob:
            button_a_ob = sba_ob

        else:
            button_a_ob = bpy.data.objects.new("%s door_button_a" % entity_idx, button_a_ob_data)
            button_a_ob.parent = door_ob
            button_a_ob.matrix_world = ob_a_matrix

        if sbb_ob:
            button_b_ob = sbb_ob

        else:
            button_b_ob = bpy.data.objects.new("%s door_button_b" % entity_idx, button_b_ob_data)
            button_b_ob.parent = door_ob
            button_b_ob.matrix_world = ob_b_matrix

    return door_ob, button_a_ob, button_b_ob
