import os
import bpy

from math import radians
from pathlib import Path
from .process_3dw import read_3dw
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
                               SHADER_RESOURCES,
                               ROOMSCALE,
                               LIGHTEXPONENT,
                               ObjectType)

def import_node_recursive(context, data, node, random_color_gen, local_asset_path, parent_ob=None):
    if node["classname"] == "classname" and node["name"] == "light":
        light_data = bpy.data.lights.new(node["classname"], "POINT")
        object_mesh = bpy.data.objects.new(node["classname"], light_data)
        context.collection.objects.link(object_mesh)

        light_data.shadow_soft_size = ROOMSCALE * float(node["properties"].get("range", 0))
        light_data.energy = float(node["properties"].get("intensity", 0)) * (light_data.shadow_soft_size ** LIGHTEXPONENT) 
        light_color = node["properties"].get("color")
        if light_color is not None:
            r, g, b = light_color.split(" ")
            light_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

        object_mesh.cb.linear_falloff = float(node["properties"].get("linearfalloff", 0))

        object_mesh.matrix_world = Matrix.LocRotScale(ROOMSCALE * Vector(node["origin"]), Quaternion(), Vector((1, 1, 1)))

        object_mesh.cb.object_type = str(ObjectType.entity_light.value)

    elif node["classname"] == "classname" and node["name"] == "spotlight":
        spotlight_data = bpy.data.lights.new(node["classname"], "SPOT")
        object_mesh = bpy.data.objects.new(node["classname"], spotlight_data)
        context.collection.objects.link(object_mesh)

        spotlight_data.shadow_soft_size = ROOMSCALE * float(node["properties"].get("range", 0))
        spotlight_data.energy = float(node["properties"].get("intensity", 0)) * (spotlight_data.shadow_soft_size ** LIGHTEXPONENT) 
        light_color = node["properties"].get("color")
        if light_color is not None:
            r, g, b = light_color.split(" ")
            spotlight_data.color = (int(r) / 255, int(g) / 255, int(b) / 255)

        outer_deg: float = max(1.0, min(180.0, float(node["properties"].get("outerconeangle", 0))))
        inner_deg: float = max(1.0, min(180.0, float(node["properties"].get("innerconeangle", 0))))
        ratio = inner_deg / outer_deg if outer_deg > 0.0 else 1.0

        spotlight_data.spot_size = radians(outer_deg)
        spotlight_data.spot_blend = max(0.0, min(1.0, 1.0 - ratio))

        object_mesh.cb.linear_falloff = float(node["properties"].get("linearfalloff", 0))

        light_rotation = Quaternion()
        light_angles = node["properties"].get("angles") 
        if light_angles is not None:
            x, y, z = light_angles.split(" ")
            light_rotation = Euler((radians(float(x)), radians(float(y)), radians(float(z))), 'XYZ').to_quaternion()
            axis = Vector((1, 0, 0))
            rot = Quaternion(axis, radians(-90))
            light_rotation = rot @ light_rotation

        object_mesh.matrix_world = Matrix.LocRotScale(ROOMSCALE * Vector(node["origin"]), light_rotation, Vector((1, 1, 1)))

        object_mesh.cb.object_type = str(ObjectType.entity_spotlight.value)


def import_scene(context, filepath, report):
    game_path = Path(bpy.context.preferences.addons[__package__].preferences.game_path)

    local_asset_path = ""
    if not is_string_empty(str(game_path)) and str(filepath).startswith(str(game_path)):
        local_asset_path = os.path.dirname(os.path.relpath(str(filepath), str(game_path)))

    data = read_3dw(filepath)

    error_log = set()
    random_color_gen = RandomColorGenerator() # generates a random sequence of colors

    for object_node in data["objects"]:
        import_node_recursive(context, data, object_node, random_color_gen, local_asset_path)

    report({'INFO'}, "Import completed successfully")
    return {'FINISHED'}
