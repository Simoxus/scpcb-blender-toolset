from .common_functions import (read_null_string,
                               write_null_string,
                               read_integer,
                               write_integer,
                               read_short,
                               write_short,
                               read_byte,
                               write_byte,
                               read_vector,
                               write_vector,
                               read_2d_vector,
                               write_2d_vector)

def read_node(smf_stream, node_dict):
    child_count = read_integer(smf_stream)
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
        child_node_dict["position"] = read_vector(smf_stream)
        child_node_dict["rotation"] = read_vector(smf_stream)
        child_node_dict["scale"] = read_vector(smf_stream)

        child_node_dict["texture_group"] = read_null_string(smf_stream)
        child_node_dict["texture_name"] = read_null_string(smf_stream)

        vertex_count = read_short(smf_stream)
        for vertex_idx in range(vertex_count):
            child_node_dict["vertices"].append(read_vector(smf_stream))

        for vertex_idx in range(vertex_count):
            child_node_dict["normals"].append(read_vector(smf_stream))

        for vertex_idx in range(vertex_count):
            child_node_dict["uvs"].append(read_2d_vector(smf_stream))

        triangle_count = read_short(smf_stream)
        for face_idx in range(triangle_count):
            p0 = read_short(smf_stream)
            p1 = read_short(smf_stream)
            p2 = read_short(smf_stream)
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
        smf_dict["file_version"] = read_short(smf_stream)
        smf_dict["file_flags"] = read_byte(smf_stream)
        read_node(smf_stream, smf_dict["nodes"])

    return smf_dict
