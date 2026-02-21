import os
import bpy
import colorsys

from math import pi, radians
from mathutils import Matrix, Quaternion, Vector, Euler

SHADER_RESOURCES = os.path.join(os.path.dirname(os.path.realpath(__file__)), "shader_resources.blend")

DTOR = pi / 180.0
RTOD = 180.0 / pi

PM_IMPORT = Matrix.Rotation(radians(90), 4, 'X') @ Matrix.Diagonal((-1.0, 1.0, 1.0, 1.0)) @ Matrix.Scale(0.00625, 4)

def pitch_quat(p):
    return Quaternion((1.0, 0.0, 0.0), p)

def yaw_quat(y):
    return Quaternion((0.0, 1.0, 0.0), y)

def roll_quat(r):
    return Quaternion((0.0, 0.0, 1.0), r)

def rotation_quat(p, y, r):
    return yaw_quat(y) @ pitch_quat(p) @ roll_quat(r)

def get_blender_rot(entity_position, entity_rotation, is_spotlight=False):
    p, y, r = entity_rotation
    y = -y
    quat = rotation_quat(p * DTOR, y * DTOR, r * DTOR)
    quat.normalized()

    loc, rot, scl = (PM_IMPORT @ Matrix.LocRotScale(entity_position, quat, Vector((1,1,1)))).decompose()
    if not is_spotlight:
        rx, ry, rz = (rot @ Matrix.Rotation(radians(90), 4, 'X').to_quaternion()).to_euler()
    else:
        rx, ry, rz = rot.to_euler()

    return Euler((-rx, -ry, rz))

def lim32(n):
    """Simulate a 32 bit unsigned interger overflow"""
    return n & 0xFFFFFFFF

# Ported from https://github.com/preshing/RandomSequence
class PreshingSequenceGenerator32:
    """Peusdo-random sequence generator that repeats every 2**32 elements"""
    @staticmethod
    def __permuteQPR(x):
        prime = 4294967291
        if x >= prime: # The 5 integers out of range are mapped to themselves.
            return x

        residue = lim32(x**2 % prime)
        if x <= (prime // 2):
            return residue

        else:
            return lim32(prime - residue)

    def __init__(self, seed_base = None, seed_offset = None):
        import time
        if seed_base == None:
            seed_base = lim32(int(time.time() * 100000000)) ^ 0xac1fd838

        if seed_offset == None:
            seed_offset = lim32(int(time.time() * 100000000)) ^ 0x0b8dedd3

        self.__index = PreshingSequenceGenerator32.__permuteQPR(lim32(PreshingSequenceGenerator32.__permuteQPR(seed_base) + 0x682f0161))
        self.__intermediate_offset = PreshingSequenceGenerator32.__permuteQPR(lim32(PreshingSequenceGenerator32.__permuteQPR(seed_offset) + 0x46790905))

    def next(self):
        self.__index = lim32(self.__index + 1)
        index_permut = PreshingSequenceGenerator32.__permuteQPR(self.__index)
        return PreshingSequenceGenerator32.__permuteQPR(lim32(index_permut + self.__intermediate_offset) ^ 0x5bf03635)

class RandomColorGenerator(PreshingSequenceGenerator32):
    def next(self):
        rng = super().next()
        h = (rng >> 16) / 0xFFF # [0, 1]
        saturation_raw = (rng & 0xFF) / 0xFF
        brightness_raw = (rng >> 8 & 0xFF) / 0xFF
        v = brightness_raw * 0.3 + 0.5 # [0.5, 0.8]
        s = saturation_raw * 0.4 + 0.6 # [0.3, 1]
        rgb = colorsys.hsv_to_rgb(h, s, v)
        colors = (rgb[0], rgb[1] , rgb[2], 1)
        return colors

def is_string_empty(string):
    is_empty = False
    if not string == None and (len(string) == 0 or string.isspace()):
        is_empty = True

    return is_empty

def get_file(file_name, use_image_set=True, generate_image_node=True, directory_path=""):
    extension_set = ("bmp", "jpg", "jpeg", "png")
    if not use_image_set:
        extension_set = ("b3d", "x")

    file_asset = None
    file_path = None
    game_path = bpy.context.preferences.addons[__package__].preferences.game_path
    asset_directory = os.path.join(game_path, directory_path)
    if not is_string_empty(asset_directory) and file_name is not None:
        if not is_string_empty(directory_path):
            for file in os.listdir(asset_directory):
                absolute_file_path = os.path.join(asset_directory, file)
                if os.path.isfile(absolute_file_path):
                    for extension in extension_set:
                        file_name_w_ext = os.path.basename(file_name).lower()
                        file_name_wo_ext = file_name_w_ext.rsplit(".", 1)[0]
                        if file_name_wo_ext == "scp-012_diffuse": # The SCP 12 model references a texture that doesn't exist so putting this hack here - Gen
                            file_name_wo_ext = "scp-012_0"
                        if file.lower() == "%s.%s" % (file_name_wo_ext, extension):
                            file_path = os.path.join(asset_directory, file)
                            break

        if file_path is None:
            for root, dirs, files in os.walk(game_path):
                for file in files:
                    for extension in extension_set:
                        file_name_w_ext = os.path.basename(file_name).lower()
                        file_name_wo_ext = file_name_w_ext.rsplit(".", 1)[0]
                        if file.lower() == "%s.%s" % (file_name_wo_ext, extension):
                            file_path = os.path.join(root, file)
                            break

        # Not sure why I do this - Gen
        #if file_path is None:
            #file_path = ""

    if use_image_set and generate_image_node:
        if file_path is not None and os.path.isfile(file_path):
            file_asset = bpy.data.images.load(file_path, check_existing=True)
    else:
        file_asset = file_path

    return file_asset

def get_material_name(ob, tri):
    mat_name = "UNASSIGNED"
    mat_count = len(ob.material_slots)
    ob_mat_idx = tri.material_index
    if 0 <= ob_mat_idx < mat_count:
        mat_slot = ob.material_slots[ob_mat_idx]
        if mat_slot.link == 'OBJECT':
            if mat_slot is not None:
                mat_name = mat_slot.material.name
        else:
            if ob.data.materials[ob_mat_idx] is not None:
                mat_name = ob.data.materials[ob_mat_idx].name

    return mat_name

def get_linked_node(node, input_name, search_type):
    linked_node = None
    node_input = node.inputs[input_name]
    if node_input.is_linked:
        for node_link in node_input.links:
            if node_link.from_node.type == search_type:
                linked_node = node_link.from_node
                break

    return linked_node

def connect_inputs(tree, output_node, output_name, input_node, input_name):
    tree.links.new(output_node.outputs[output_name], input_node.inputs[input_name])

def get_output_material_node(mat):
    output_material_node = None
    if not mat == None and mat.use_nodes and not mat.node_tree == None:
        for node in mat.node_tree.nodes:
            if node.type == "OUTPUT_MATERIAL" and node.is_active_output:
                output_material_node = node
                break

    if output_material_node is None:
        output_material_node = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")

    return output_material_node

def get_shader_node(tree, shader_resource, shader_name):
    if not bpy.data.node_groups.get(shader_name):
        with bpy.data.libraries.load(shader_resource) as (data_from, data_to):
            data_to.node_groups.append(data_from.node_groups[data_from.node_groups.index(shader_name)])

    shader_node = tree.nodes.new('ShaderNodeGroup')
    shader_node.node_tree = bpy.data.node_groups.get(shader_name)

    return shader_node

def generate_texture_mapping(node_tree, input_node, input_key="Vector"):
    mapping_node = node_tree.nodes.new("ShaderNodeMapping")
    uv_node = node_tree.nodes.new("ShaderNodeUVMap")

    mapping_node.location = Vector((-180.0, 0.0)) + input_node.location
    uv_node.location = Vector((-360.0, 0.0)) + input_node.location

    connect_inputs(node_tree, uv_node, "UV", mapping_node, "Vector")
    connect_inputs(node_tree, mapping_node, "Vector", input_node, input_key)

    return mapping_node, uv_node

def flip(v):
    return ((v[0],v[2],v[1]) if len(v)<4 else (v[0], v[1],v[3],v[2]))
