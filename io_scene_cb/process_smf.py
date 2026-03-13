import struct

def read_vector3d(f):
    return struct.unpack("fff", f.read(12))

def read_vector2d(f):
    return struct.unpack("ff", f.read(8))

def read_null_string(f):
    chars = []
    while True:
        c = f.read(1)
        if c == b'\x00' or c == b'':
            break
        chars.append(c.decode('utf8'))
    return ''.join(chars)

def read_node(smf_stream, node_dict):
    child_count = struct.unpack("i", smf_stream.read(4))[0]
    for child_idx in range(child_count):
        child_node_dict = {
            "position": (0, 0, 0),
            "rotation": (0, 0, 0),
            "scale": (1, 1, 1),
            "texture_group": "",
            "texture_name": "",
            "vertices": [],
            "normals": [],
            "uvs": [],
            "faces": [],
            "nodes": []
        }
        child_node_dict["position"] = read_vector3d(smf_stream)
        child_node_dict["rotation"] = read_vector3d(smf_stream)
        child_node_dict["scale"] = read_vector3d(smf_stream)

        child_node_dict["texture_group"] = read_null_string(smf_stream)
        child_node_dict["texture_name"] = read_null_string(smf_stream)

        vertex_count = struct.unpack("H", smf_stream.read(2))[0]
        for vertex_idx in range(vertex_count):
            child_node_dict["vertices"].append(read_vector3d(smf_stream))

        for vertex_idx in range(vertex_count):
            child_node_dict["normals"].append(read_vector3d(smf_stream))

        for vertex_idx in range(vertex_count):
            child_node_dict["uvs"].append(read_vector2d(smf_stream))

        triangle_count = struct.unpack("H", smf_stream.read(2))[0]
        for face_idx in range(triangle_count):
            p0, p1, p2 = struct.unpack("HHH", smf_stream.read(6))
            child_node_dict["faces"].append((p0, p1, p2))

        node_dict.append(child_node_dict)
        read_node(smf_stream, child_node_dict["nodes"])

def read_smf(file_path):
    smf_dict = {
        "file_version": 0,
        "file_flags": 0,
        "nodes": []
    }
    with file_path.open("rb") as smf_stream:
        smf_dict["file_version"] = struct.unpack("H", smf_stream.read(2))[0]
        smf_dict["file_flags"] = struct.unpack("B", smf_stream.read(1))[0]
        read_node(smf_stream, smf_dict["nodes"])

    return smf_dict
