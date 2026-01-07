import os
import json
import struct

from enum import Enum, auto

class FileType(Enum):
    rmesh_auto = 0
    rmesh = auto()
    rmesh_tb = auto()
    rmesh_uer = auto()
    rmesh_uer2 = auto()

class TextureType(Enum):
    none = 0
    opaque = auto()
    lightmap = auto()
    transparent = auto()

def read_string(rmesh_stream):
    return rmesh_stream.read(read_unsigned_int(rmesh_stream)).decode('utf-8')

def write_string(rmesh_stream, value):
    string_length = len(value)
    write_unsigned_int(rmesh_stream, string_length)
    rmesh_stream.write(struct.pack('<%ss' % string_length, bytes(value, 'utf-8')))

def read_unsigned_int(rmesh_stream):
    return struct.unpack('<I', rmesh_stream.read(4))[0]

def write_unsigned_int(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<I', value))

def read_byte(rmesh_stream):
    return struct.unpack('<B', rmesh_stream.read(1))[0]

def write_byte(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<B', value))

def read_float(rmesh_stream):
    return struct.unpack('<f', rmesh_stream.read(4))[0]

def write_float(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<f', value))

def read_vector(rmesh_stream):
    return struct.unpack('<3f', rmesh_stream.read(12))

def write_vector(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<3f', *value))

def read_2d_vector(rmesh_stream):
    return struct.unpack('<2f', rmesh_stream.read(8))

def write_2d_vector(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<2f', *value))

def read_uv(rmesh_stream):
    return struct.unpack('<2f', rmesh_stream.read(8))

def write_uv(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<2f', *value))

def read_color(rmesh_stream):
    return struct.unpack('<3B', rmesh_stream.read(3))

def write_color(rmesh_stream, value):
    rmesh_stream.write(struct.pack('<3B', *value))

def read_rmesh(file_path, file_type):
    rmesh_dict = {
        "rmesh_file_type": "",
        "meshes": [],
        "collision_meshes": [],
        "trigger_boxes": [],
        "entities": []
    }
    with open(file_path, "rb") as rmesh_stream:
        rmesh_dict["rmesh_file_type"] = read_string(rmesh_stream)
        if rmesh_dict["rmesh_file_type"] != "RoomMesh" and rmesh_dict["rmesh_file_type"] != "RoomMesh.HasTriggerBox" and rmesh_dict["rmesh_file_type"] != "RoomMesh2":
            raise ValueError('Input file was "%s" instead of "RoomMesh", "RoomMesh.HasTriggerBox", or "RoomMesh2" and therefore is not an RMESH file' % rmesh_dict["rmesh_file_type"])

        file_type_enum = FileType(int(file_type))
        if file_type_enum == FileType.rmesh_auto:
            if rmesh_dict["rmesh_file_type"] == "RoomMesh":
                raise ValueError('Auto is not supported for "RoomMesh" since it can either apply to SCP Containment Breach or Ultimate Reborn 1.5.6.')

            elif rmesh_dict["rmesh_file_type"] == "RoomMesh.HasTriggerBox":
                file_type_enum = FileType.rmesh_tb

            elif rmesh_dict["rmesh_file_type"] == "RoomMesh2":
                file_type_enum = FileType.rmesh_uer2

        mesh_count = read_unsigned_int(rmesh_stream)
        for mesh_idx in range(mesh_count):
            mesh_dict = {
                "textures": [],
                "vertices": [],
                "triangles": []
            }

            for texture_idx in range(2):
                texture_dict = {}

                texture_dict["texture_type"] = read_byte(rmesh_stream)
                texture_dict["texture_name"] = ""
                if TextureType(texture_dict["texture_type"]) is not TextureType.none:
                    texture_dict["texture_name"] = read_string(rmesh_stream)

                mesh_dict["textures"].append(texture_dict)

            vertex_count = read_unsigned_int(rmesh_stream)
            for vertex_idx in range(vertex_count):
                vertex_dict = {}

                vertex_dict["position"] = read_vector(rmesh_stream)
                vertex_dict["uv_render"] = read_uv(rmesh_stream)
                vertex_dict["uv_lightmap"] = read_uv(rmesh_stream)
                vertex_dict["color"] = read_color(rmesh_stream)
                if file_type_enum == FileType.rmesh_uer2:
                    vertex_dict["normal"] = read_vector(rmesh_stream)

                mesh_dict["vertices"].append(vertex_dict)

            triangle_count = read_unsigned_int(rmesh_stream)
            for triangle_idx in range(triangle_count):
                triangle_dict = {}

                triangle_dict["a"] = read_unsigned_int(rmesh_stream)
                triangle_dict["b"] = read_unsigned_int(rmesh_stream)
                triangle_dict["c"] = read_unsigned_int(rmesh_stream)

                mesh_dict["triangles"].append(triangle_dict)

            rmesh_dict["meshes"].append(mesh_dict)

        collision_count = read_unsigned_int(rmesh_stream)
        for collision_idx in range(collision_count):
            mesh_dict = {
                "vertices": [],
                "triangles": []
            }

            vertex_count = read_unsigned_int(rmesh_stream)
            for vertex_idx in range(vertex_count):
                vertex_dict = {}

                vertex_dict["position"] = read_vector(rmesh_stream)

                mesh_dict["vertices"].append(vertex_dict)

            triangle_count = read_unsigned_int(rmesh_stream)
            for triangle_idx in range(triangle_count):
                triangle_dict = {}

                triangle_dict["a"] = read_unsigned_int(rmesh_stream)
                triangle_dict["b"] = read_unsigned_int(rmesh_stream)
                triangle_dict["c"] = read_unsigned_int(rmesh_stream)

                mesh_dict["triangles"].append(triangle_dict)

            rmesh_dict["collision_meshes"].append(mesh_dict)

        if file_type_enum == FileType.rmesh_tb:
            trigger_box_count = read_unsigned_int(rmesh_stream)
            for trigger_box_idx in range(trigger_box_count):
                collision_count = read_unsigned_int(rmesh_stream)
                trigger = {
                    "meshes": [],
                    "name": ""
                }
                for collision_idx in range(collision_count):
                    mesh_dict = {
                        "vertices": [],
                        "triangles": []
                    }

                    vertex_count = read_unsigned_int(rmesh_stream)
                    for vertex_idx in range(vertex_count):
                        vertex_dict = {}

                        vertex_dict["position"] = read_vector(rmesh_stream)

                        mesh_dict["vertices"].append(vertex_dict)

                    triangle_count = read_unsigned_int(rmesh_stream)
                    for triangle_idx in range(triangle_count):
                        triangle_dict = {}

                        triangle_dict["a"] = read_unsigned_int(rmesh_stream)
                        triangle_dict["b"] = read_unsigned_int(rmesh_stream)
                        triangle_dict["c"] = read_unsigned_int(rmesh_stream)

                        mesh_dict["triangles"].append(triangle_dict)

                    trigger["meshes"].append(mesh_dict)

                trigger["name"] = read_string(rmesh_stream)
                rmesh_dict["trigger_boxes"].append(trigger)

        entity_count = read_unsigned_int(rmesh_stream)
        for entity_idx in range(entity_count):
            entity_dict = {}
            entity_dict["entity_type"] = read_string(rmesh_stream)
            if entity_dict["entity_type"] == "screen":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["texture_name"] = read_string(rmesh_stream)

            elif entity_dict["entity_type"] == "save_screen":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["model_name"] = read_string(rmesh_stream)
                entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                entity_dict["scale"] = read_vector(rmesh_stream)
                entity_dict["texture_name"] = read_string(rmesh_stream)

            elif entity_dict["entity_type"] == "waypoint":
                entity_dict["position"] = read_vector(rmesh_stream)

            elif entity_dict["entity_type"] == "light":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["range"] = read_float(rmesh_stream)
                entity_dict["color"] = read_string(rmesh_stream)
                entity_dict["intensity"] = read_float(rmesh_stream)
                if file_type_enum == FileType.rmesh_uer2:
                    entity_dict["has_sprite"] = read_byte(rmesh_stream)
                    entity_dict["sprite_scale"] = read_float(rmesh_stream)
                    entity_dict["casts_shadows"] = read_byte(rmesh_stream)
                    entity_dict["scattering"] = read_float(rmesh_stream)
                    entity_dict["ff_array"] = []
                    for ff in range(31):
                        ff_element = read_unsigned_int(rmesh_stream)
                        entity_dict["ff_array"].append(ff_element)
 
            elif entity_dict["entity_type"] == "light_fix":
                if file_type_enum == FileType.rmesh_uer2:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["range"] = read_float(rmesh_stream)
                    entity_dict["color"] = read_string(rmesh_stream)
                    entity_dict["intensity"] = read_float(rmesh_stream)
                    entity_dict["has_sprite"] = read_byte(rmesh_stream)
                    entity_dict["sprite_scale"] = read_float(rmesh_stream)
                    entity_dict["casts_shadows"] = read_byte(rmesh_stream)
                    entity_dict["scattering"] = read_float(rmesh_stream)
                    entity_dict["ff_array"] = []
                    for ff in range(31):
                        ff_element = read_unsigned_int(rmesh_stream)
                        entity_dict["ff_array"].append(ff_element)
                else:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["color"] = read_string(rmesh_stream)
                    entity_dict["intensity"] = read_float(rmesh_stream)
                    entity_dict["range"] = read_float(rmesh_stream)

            elif entity_dict["entity_type"] == "spotlight":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["range"] = read_float(rmesh_stream)
                entity_dict["color"] = read_string(rmesh_stream)
                entity_dict["intensity"] = read_float(rmesh_stream)
                if file_type_enum == FileType.rmesh_uer2:
                    entity_dict["has_sprite"] = read_byte(rmesh_stream)
                    entity_dict["sprite_scale"] = read_float(rmesh_stream)
                    entity_dict["casts_shadows"] = read_byte(rmesh_stream)
                    entity_dict["direction"] = read_2d_vector(rmesh_stream)
                    entity_dict["inner_cosine"] = read_float(rmesh_stream)
                    entity_dict["scattering"] = read_float(rmesh_stream)
                    entity_dict["ff_array"] = []
                    for ff in range(31):
                        ff_element = read_unsigned_int(rmesh_stream)
                        entity_dict["ff_array"].append(ff_element)
                else:
                    entity_dict["euler_rotation"] = read_string(rmesh_stream)
                    entity_dict["inner_cone_angle"] = read_unsigned_int(rmesh_stream)
                    entity_dict["outer_cone_angle"] = read_unsigned_int(rmesh_stream)

            elif entity_dict["entity_type"] == "soundemitter":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["id"] = read_unsigned_int(rmesh_stream)
                entity_dict["range"] = read_float(rmesh_stream)

            elif entity_dict["entity_type"] == "playerstart":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["euler_rotation"] = read_string(rmesh_stream)

            elif entity_dict["entity_type"] == "model":
                entity_dict["model_name"] = read_string(rmesh_stream)
                if not file_type_enum == FileType.rmesh_uer:
                    entity_dict["position"] = read_vector(rmesh_stream)
                    entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                    entity_dict["scale"] = read_vector(rmesh_stream)

            elif entity_dict["entity_type"] == "mesh":
                entity_dict["position"] = read_vector(rmesh_stream)
                entity_dict["model_name"] = read_string(rmesh_stream)
                entity_dict["euler_rotation"] = read_vector(rmesh_stream)
                entity_dict["scale"] = read_vector(rmesh_stream)
                entity_dict["has_collision"] = read_byte(rmesh_stream)
                entity_dict["fx"] = read_unsigned_int(rmesh_stream)
                entity_dict["texture_name"] = read_string(rmesh_stream)
            else:
                print("Unknown entity type: %s" % entity_dict["entity_type"])

            rmesh_dict["entities"].append(entity_dict)

    return file_type_enum, rmesh_dict

def write_rmesh(rmesh_dict, output_path):
    with open(output_path, "wb") as rmesh_stream:
        if rmesh_dict["rmesh_file_type"] != "RoomMesh" and rmesh_dict["rmesh_file_type"] != "RoomMesh2":
            raise ValueError("Input is not an RMESH file")

        is_rmesh2 = False
        if rmesh_dict["rmesh_file_type"] == "RoomMesh2":
            is_rmesh2 = True

        write_string(rmesh_stream, rmesh_dict["rmesh_file_type"])
        write_unsigned_int(rmesh_stream, len(rmesh_dict["meshes"]))
        for mesh_dict in rmesh_dict["meshes"]:
            for texture_dict in mesh_dict["textures"]:
                write_byte(rmesh_stream, texture_dict["texture_type"])
                if TextureType(texture_dict["texture_type"]) is not TextureType.none:
                    write_string(rmesh_stream, texture_dict["texture_name"])

            write_unsigned_int(rmesh_stream, len(mesh_dict["vertices"]))
            for vertex_dict in mesh_dict["vertices"]:
                write_vector(rmesh_stream, vertex_dict["position"])
                write_uv(rmesh_stream, vertex_dict["uv_render"])
                write_uv(rmesh_stream, vertex_dict["uv_lightmap"])
                write_color(rmesh_stream, vertex_dict["color"])
                if is_rmesh2:
                    write_vector(rmesh_stream, vertex_dict["normal"])

            write_unsigned_int(rmesh_stream, len(mesh_dict["triangles"]))
            for triangle_dict in mesh_dict["triangles"]:
                write_unsigned_int(rmesh_stream, triangle_dict["a"])
                write_unsigned_int(rmesh_stream, triangle_dict["b"])
                write_unsigned_int(rmesh_stream, triangle_dict["c"])

        write_unsigned_int(rmesh_stream, len(rmesh_dict["collision_meshes"]))
        for collision_dict in rmesh_dict["collision_meshes"]:
            write_unsigned_int(rmesh_stream, len(collision_dict["vertices"]))
            for vertex_dict in collision_dict["vertices"]:
                write_vector(rmesh_stream, vertex_dict["position"])

            write_unsigned_int(rmesh_stream, len(collision_dict["triangles"]))
            for triangle_dict in collision_dict["triangles"]:
                write_unsigned_int(rmesh_stream, triangle_dict["a"])
                write_unsigned_int(rmesh_stream, triangle_dict["b"])
                write_unsigned_int(rmesh_stream, triangle_dict["c"])

        write_unsigned_int(rmesh_stream, len(rmesh_dict["entities"]))
        for entity_dict in rmesh_dict["entities"]:
            write_string(rmesh_stream, entity_dict["entity_type"])
            if entity_dict["entity_type"] == "screen":
                write_vector(rmesh_stream, entity_dict["position"])
                write_string(rmesh_stream, entity_dict["texture_name"])

            elif entity_dict["entity_type"] == "save_screen":
                write_vector(rmesh_stream, entity_dict["position"])
                write_string(rmesh_stream, entity_dict["model_name"])
                write_vector(rmesh_stream, entity_dict["euler_rotation"])
                write_vector(rmesh_stream, entity_dict["scale"])
                write_string(rmesh_stream, entity_dict["texture_name"])

            elif entity_dict["entity_type"] == "waypoint":
                write_vector(rmesh_stream, entity_dict["position"])

            elif entity_dict["entity_type"] == "light":
                if is_rmesh2:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_float(rmesh_stream, entity_dict["range"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_unsigned_int(rmesh_stream, ff_element)
                else:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_float(rmesh_stream, entity_dict["range"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])

            elif entity_dict["entity_type"] == "light_fix":
                if is_rmesh2:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_float(rmesh_stream, entity_dict["range"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_unsigned_int(rmesh_stream, ff_element)
                else:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_string(rmesh_stream, entity_dict["color"])
                    write_float(rmesh_stream, entity_dict["intensity"])
                    write_float(rmesh_stream, entity_dict["range"])

            elif entity_dict["entity_type"] == "spotlight":
                write_vector(rmesh_stream, entity_dict["position"])
                write_float(rmesh_stream, entity_dict["range"])
                write_string(rmesh_stream, entity_dict["color"])
                write_float(rmesh_stream, entity_dict["intensity"])
                if is_rmesh2:
                    write_byte(rmesh_stream, entity_dict["has_sprite"])
                    write_float(rmesh_stream, entity_dict["sprite_scale"])
                    write_byte(rmesh_stream, entity_dict["casts_shadows"])
                    write_2d_vector(rmesh_stream, entity_dict["direction"])
                    write_float(rmesh_stream, entity_dict["inner_cosine"])
                    write_float(rmesh_stream, entity_dict["scattering"])
                    for ff_element in entity_dict["ff_array"]:
                        write_unsigned_int(rmesh_stream, ff_element)
                else:
                    write_string(rmesh_stream, entity_dict["euler_rotation"])
                    write_unsigned_int(rmesh_stream, entity_dict["inner_cone_angle"])
                    write_unsigned_int(rmesh_stream, entity_dict["outer_cone_angle"])

            elif entity_dict["entity_type"] == "soundemitter":
                write_vector(rmesh_stream, entity_dict["position"])
                write_unsigned_int(rmesh_stream, entity_dict["id"])
                write_float(rmesh_stream, entity_dict["range"])

            elif entity_dict["entity_type"] == "model":
                write_string(rmesh_stream, entity_dict["model_name"])
                if is_rmesh2:
                    write_vector(rmesh_stream, entity_dict["position"])
                    write_vector(rmesh_stream, entity_dict["euler_rotation"])
                    write_vector(rmesh_stream, entity_dict["scale"])

            elif entity_dict["entity_type"] == "mesh":
                write_vector(rmesh_stream, entity_dict["position"])
                write_string(rmesh_stream, entity_dict["model_name"])
                write_vector(rmesh_stream, entity_dict["euler_rotation"])
                write_vector(rmesh_stream, entity_dict["scale"])
                write_byte(rmesh_stream, entity_dict["has_collision"])
                write_unsigned_int(rmesh_stream, entity_dict["fx"])
                write_string(rmesh_stream, entity_dict["texture_name"])

if True:
    if False:
        input_path = r"C:\Users\Steven\Downloads\SCP CB UER\scpcb-ue-my-1.5.x\GFX\Map\cont1_173.rmesh"
        json_path = r"C:\Users\Steven\Desktop\cont1_173.json"

        rmesh_dict = read_rmesh(input_path)
        with open(json_path, 'w', encoding ='utf8') as json_file:
            json.dump(rmesh_dict, json_file, ensure_ascii = True, indent=4)
            
    elif False:
        json_path = r"C:\Users\Steven\Desktop\cont1_038.json"
        output_path = r"C:\Users\Steven\Desktop\cont1_038.rmesh"

        with open(json_path, 'r', encoding ='utf8') as json_file:
            data = json.load(json_file)
            write_rmesh(data, output_path)

    elif False:
        game_path = r"C:\Program Files (x86)\Steam\steamapps\common\SCP - Containment Breach UER v2.0B"
        for root, dirs, files in os.walk(game_path):
            for file in files:
                file_path = os.path.join(root, file)
                if file_path.lower().endswith(".rmesh"):
                    print(os.path.basename(file_path))
                    rmesh_dict = read_rmesh(file_path)

    elif False:
        import math

        # ------------------------
        # Minimal 3D vector class
        # ------------------------
        class Vec3:
            def __init__(self, x,y,z):
                self.x=float(x)
                self.y=float(y)
                self.z=float(z)
            def __add__(self, other):
                return Vec3(self.x+other.x,self.y+other.y,self.z+other.z)
            def __iadd__(self, other):
                self.x+=other.x; self.y+=other.y; self.z+=other.z
                return self
            def __sub__(self, other):
                return Vec3(self.x-other.x,self.y-other.y,self.z-other.z)
            def cross(self, other):
                return Vec3(
                    self.y*other.z - self.z*other.y,
                    self.z*other.x - self.x*other.z,
                    self.x*other.y - self.y*other.x
                )
            def length_squared(self):
                return self.x**2 + self.y**2 + self.z**2
            def normalize(self):
                l = math.sqrt(self.length_squared())
                if l==0: return Vec3(0,0,1)
                self.x/=l; self.y/=l; self.z/=l
                return self
            def __neg__(self):
                return Vec3(-self.x,-self.y,-self.z)
            def __repr__(self):
                return f"({self.x:.3f}, {self.y:.3f}, {self.z:.3f})"
            def dot(self, other):
                return self.x*other.x + self.y*other.y + self.z*other.z

        # Media3D-style vertex normal generator
        def generate_media3d_vertex_normals(vertices, triangles, fix_winding=True):
            """
            vertices  : list of dicts with 'position': (x,y,z)
            triangles : list of dicts with 'a','b','c' indices into vertices
            fix_winding : bool, optionally flips normals outward
            returns   : list[Vec3] per vertex normal
            """
            normals = [None]*len(vertices)  # store normal per vertex

            # Optional: compute mesh center for outward check
            if fix_winding:
                center = Vec3(0,0,0)
                for v in vertices:
                    pos = v["position"]
                    center += Vec3(*pos)
                center = Vec3(center.x/len(vertices),
                            center.y/len(vertices),
                            center.z/len(vertices))

            # Assign face normals directly to triangle vertices
            for tri in triangles:
                i0,i1,i2 = tri["a"], tri["b"], tri["c"]
                v0 = Vec3(*vertices[i0]["position"])
                v1 = Vec3(*vertices[i1]["position"])
                v2 = Vec3(*vertices[i2]["position"])

                # Compute face normal
                n = (v1 - v0).cross(v2 - v0)
                if n.length_squared()==0:
                    n = Vec3(0,0,1)
                else:
                    n = n.normalize()

                # Optional: fix outward direction
                if fix_winding and n.dot(v0 - center) < 0:
                    n = -n

                # Assign to vertices of this triangle
                normals[i0] = n
                normals[i1] = n
                normals[i2] = n

            # Safety: normalize all normals
            for i,n in enumerate(normals):
                if n is None or n.length_squared()==0:
                    normals[i] = Vec3(0,0,1)
                else:
                    normals[i] = n.normalize()

            return normals
        input_path = r"C:\Users\Steven\Desktop\test.rmesh"
        rmesh_dict = read_rmesh(input_path)
        for mesh in rmesh_dict["meshes"]:
            normals = generate_media3d_vertex_normals(mesh["vertices"], mesh["triangles"], fix_winding=False)
        for normal in normals:
            print(normal)
