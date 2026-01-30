import os
import re
import zlib
import json
import struct

from enum import Enum, auto
from io import TextIOWrapper

class FileType(Enum):
    unk = 0
    text = auto()
    binary = auto()
    compressed_binary = auto()

class CompressionType(Enum):
    uncompressed = 0
    compressed = auto()
    unk = auto()

class FloatType(Enum):
    unk = 0
    _32 = auto()
    _64 = auto()

def test_encoding(filepath):
    UTF_8_BOM = b'\xef\xbb\xbf'
    UTF_16_BE_BOM = b'\xfe\xff'
    UTF_16_LE_BOM = b'\xff\xfe'
    data = filepath.open("rb")
    file_size = os.path.getsize(filepath)
    BOM = data.read(3)
    encoding = None
    # first check the boms
    if BOM.startswith(UTF_8_BOM):
        encoding = 'utf-8-sig'

    elif BOM.startswith(UTF_16_BE_BOM) or BOM.startswith(UTF_16_LE_BOM):
        encoding = 'utf-16'

    else:
        if file_size % 2: # can't be USC-2/UTF-16 if the number of bytes is odd
            encoding = 'utf-8'

        else:
            # get the first half a kilobyte
            data.seek(0)
            sample_bytes = data.read(0x200)

            even_zeros = 0
            odd_zeros = 0

            for idx, byte in enumerate(sample_bytes):
                if byte != 0:
                    continue

                if idx % 2:
                    odd_zeros += 1

                else:
                    even_zeros += 1

            ## if there are no null bytes we assume we are dealing with a utf-8 file
            ## if there are null bytes, assume utf-16 and guess endianness based on where the null bytes are
            if even_zeros == 0 and odd_zeros == 0:
                encoding = 'utf-8'

            elif odd_zeros > even_zeros:
                encoding = 'utf-16-le'

            else:
                encoding = 'utf-16-be'

    data.close()

    return encoding

class ParseError(Exception):
    pass

class TextAsset:
    def __init__(self, file):
        self._elements = []
        self._index = 0
        if not isinstance(file, TextIOWrapper):
            with file.open("r", encoding=test_encoding(file)) as file:
                self.__init_from_textio(file.read())

        else:
            self.__init_from_textio(file.read())

    def __init_from_textio(self, io):
        token_re = re.compile(
            r'''
            "(?:\\.|[^"])*"      |  # quoted string
            <[^>]+>              |  # angle-bracket blocks
            [{};,]               |  # punctuation
            [^\s{};,]+              # everything else (names, numbers, etc.)
            ''',
            re.VERBOSE
        )

        io = re.sub(r'//.*$', '', io, flags=re.MULTILINE)

        for token in token_re.findall(io):
            self._elements.append(token)

    def left(self):
        """Returns the number of elements left"""
        if self._index < len(self._elements):
            return len(self._elements) - self._index

        else:
            return 0

    def skip(self, count):
        """Skip forwards n elements"""
        self._index += count

    def skip_terminators(self):
        """Return the next element that is not a terminator, raises AssetParseError on error"""
        try:
            self._index += 1
            next_element = self._elements[self._index - 1]
            while next_element == ";":
                self._index += 1
                next_element = self._elements[self._index - 1]

            return next_element

        except:
            raise ParseError()

    def next(self):
        """Return the next element, raises AssetParseError on error"""
        try:
            self._index += 1
            return self._elements[self._index - 1]

        except:
            raise ParseError()

    def get_first_line(self):
        """Return the first line in the file, raises AssetParseError on error"""
        try:
            return self._elements[0]

        except:
            raise ParseError()

    def next_multiple(self, count):
        """Returns an array of the next n elements, raises AssetParseError on error"""
        try:
            list = self._elements[self._index: self._index + count]
            self._index += count
            return list

        except:
            raise ParseError()

def get_indentation(level):
    result = ""
    for idx in range(level):
        result += " "

    return result

def format_float(value, decimals):
    return f"{value:.{decimals}f}"

def parse_mesh(x_dict, tokens, frame_meshes):
    mesh_dict = {
        "name": None,
        "vertices": [],
        "faces": [],
        "normals": [],
        "normal_indices": [],
        "texcoords": [],
        "dup_preexport_count": 0, 
        "dup_indices": [],
        "material_indices": [], 
        "materials": [],
        "max_weights_per_vertex": 1.0,
        "max_weights_per_face": 1.0,
        "bone_count": 0,
        "skin_weights": []
    }

    next_token = tokens.next()
    if next_token != "{":
        mesh_dict["name"] = next_token
        tokens.next()

    vertex_count = int(tokens.next())
    tokens.next()
    for vertex_idx in range(vertex_count):
        x = float(tokens.next())
        tokens.next()
        y = float(tokens.next())
        tokens.next()
        z = float(tokens.next())
        tokens.next()
        tokens.next()
        mesh_dict["vertices"].append([x, y, z])

    face_count = int(tokens.next())
    tokens.next()
    for face_idx in range(face_count):
        face_indicies = []
        face_length = int(tokens.next())
        for face_index in range(face_length):
            tokens.next()
            face_indicies.append(int(tokens.next()))

        tokens.next()
        tokens.next()

        mesh_dict["faces"].append(face_indicies)
    
    next_token = tokens.next()
    while next_token != "}" and tokens.left() > 0:
        if next_token == "MeshNormals":
            tokens.next()
            normal_count = int(tokens.next())
            tokens.next()
            for normal_idx in range(normal_count):
                normals = []
                for normal_element in range(3):
                    normals.append(float(tokens.next()))
                    tokens.next()
                tokens.next()

                mesh_dict["normals"].append(normals)

            normal_indices_count = int(tokens.next())
            tokens.next()
            for normal_idx in range(normal_indices_count):
                normal_indicies = []
                face_length = int(tokens.next())
                tokens.next()
                for face_index in range(face_length):
                    normal_indicies.append(int(tokens.next()))
                    tokens.next()

                tokens.next()

                mesh_dict["normal_indices"].append(normal_indicies)

            tokens.next()

        elif next_token == "MeshTextureCoords":
            tokens.next()
            uv_count = int(tokens.next())
            tokens.next()  
            for uv_idx in range(uv_count):
                uv_indicies = []
                for uv_element in range(2):
                    uv_indicies.append(float(tokens.next()))
                    tokens.next()  

                tokens.next() 

                mesh_dict["texcoords"].append(uv_indicies)

            tokens.next() 

        elif next_token == "VertexDuplicationIndices":
            tokens.next()
            dup_count = int(tokens.next())
            tokens.next()
            mesh_dict["dup_preexport_count"] = int(tokens.next())
            tokens.next()
            for dup_idx in range(dup_count):
                mesh_dict["dup_indices"].append(int(tokens.next()))
                tokens.next()

            tokens.next()

        elif next_token == "MeshMaterialList":
            tokens.next()
            material_count = int(tokens.next())
            tokens.next()
            face_count = int(tokens.next())
            tokens.next()
            for face_idx in range(face_count):
                mesh_dict["material_indices"].append(int(tokens.next()))
                tokens.next()

            if x_dict["xof_header"] == "xof 0302txt 0064":
                tokens.next()
                for mat_idx in range(material_count):
                   material_dict = {"name": None}
                   tokens.next()
                   material_dict["name"] = tokens.next()
                   tokens.next()

                   mesh_dict["materials"].append(material_dict)

            else:
                for mat_idx in range(material_count):
                    next_token = tokens.next()
                    parse_material(x_dict, mesh_dict, next_token, tokens)

            tokens.next()

        elif next_token == "XSkinMeshHeader":
            tokens.next()
            mesh_dict["max_weights_per_vertex"] = int(tokens.next())
            tokens.next()
            mesh_dict["max_weights_per_face"] = int(tokens.next())
            tokens.next()
            mesh_dict["bone_count"] = int(tokens.next())
            tokens.next()
            tokens.next()


        elif next_token == "SkinWeights":
            tokens.next()
            bone_dict = {"bone": None, "indices": [], "weights": [], "transform": []}
            bone_dict["bone"] = tokens.next().strip('"')
            tokens.next()

            vertex_count = int(tokens.next())
            tokens.next()
            for vertex_idx in range(vertex_count):
                bone_dict["indices"].append(int(tokens.next()))
                tokens.next()

            for vertex_idx in range(vertex_count):
                bone_dict["weights"].append(float(tokens.next()))
                tokens.next()

            next_token = tokens.next()
            while next_token != ";" and tokens.left() > 0:
                bone_dict["transform"].append(float(next_token))
                tokens.next()
                next_token = tokens.next()

            next_token = tokens.next()

            mesh_dict["skin_weights"].append(bone_dict)

            next_token = tokens.next()   

        if tokens.left() != 0:
            next_token = tokens.next()

    frame_meshes.append(mesh_dict)

def parse_frame(x_dict, tokens, children_dict):
    frame_dict = {
        "name": "",
        "transform": [],
        "meshes": [],
        "children": []
    }

    next_token = tokens.next()
    if next_token != "{":
        frame_dict["name"] = next_token
        tokens.next()

    next_token = tokens.next()
    while next_token != "}" and tokens.left() > 0:
        if next_token == "FrameTransformMatrix":
            tokens.next()
            next_token = tokens.next()
            while next_token != ";" and tokens.left() > 0:
                frame_dict["transform"].append(float(next_token))
                tokens.next()
                next_token = tokens.next()
            tokens.next()
            
        elif next_token == "Mesh":
            parse_mesh(x_dict, tokens, frame_dict["meshes"])

        elif next_token == "Frame":
            parse_frame(x_dict, tokens, frame_dict["children"])

        if tokens.left() != 0:
            next_token = tokens.next()

    children_dict.append(frame_dict)

def parse_material(x_dict, mesh_dict, next_token, tokens):
    if next_token == "Material":
        material_dict = {"name": None, 
                        "diffuse": (0.0, 0.0, 0.0, 0.0), 
                        "power": 0.0, 
                        "specular": (0.0, 0.0, 0.0), 
                        "emissive": (0.0, 0.0, 0.0), 
                        "texture": None
                        }

        next_token = tokens.next()
        if next_token != "{":
            material_dict["name"] = next_token
            tokens.next()

        dr = float(tokens.next())
        tokens.next()
        dg = float(tokens.next())
        tokens.next()
        db = float(tokens.next())
        tokens.next()
        da = float(tokens.next())
        tokens.next()
        tokens.next()

        material_dict["diffuse"] = (dr, dg, db, da)

        material_dict["power"] = float(tokens.next())
        tokens.next()

        sr = float(tokens.next())
        tokens.next()
        sg = float(tokens.next())
        tokens.next()
        sb = float(tokens.next())
        tokens.next()
        tokens.next()

        material_dict["specular"] = (sr, sg, sb)

        er = float(tokens.next())
        tokens.next()
        eg = float(tokens.next())
        tokens.next()
        eb = float(tokens.next())
        tokens.next()
        tokens.next()

        material_dict["emissive"] = (er, eg, eb)

        next_token = tokens.next()
        if next_token == "TextureFilename":
            tokens.next()
            material_dict["texture"] = tokens.next().strip('"')
            tokens.next()
            tokens.next()
            tokens.next()

        mesh_dict["materials"].append(material_dict)

    elif next_token == "{":
        # This probably needs to be moved to the scene file so that we can kept the file as it was. - Gen
        material_name = tokens.next()
        tokens.next()

        for material_dict in x_dict["materials"]:
            if material_dict["name"] == material_name:
                mesh_dict["materials"].append(material_dict)
                break

def write_mesh(mesh_dict, x_stream, indent_level=0, final_mesh=False):
    mesh_name = mesh_dict["name"]
    if mesh_name is None:
        mesh_name = ""

    x_stream.write("%sMesh %s {\n" % (get_indentation(indent_level + 0), mesh_name))
    vertex_count = len(mesh_dict["vertices"])
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 1), vertex_count))
    for vertex_idx, vertex_list in enumerate(mesh_dict["vertices"]):
        final_seperator = ","
        if vertex_idx == vertex_count - 1:
            final_seperator = ";"

        x, y, z = vertex_list
        x_stream.write("%s%s;%s;%s;%s\n" % (get_indentation(indent_level + 1), format_float(x, 6), format_float(y, 6), format_float(z, 6), final_seperator))

    face_count = len(mesh_dict["faces"])
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 1), face_count))
    for face_idx, face_list in enumerate(mesh_dict["faces"]):
        face_final_seperator = ","
        if face_idx == face_count - 1:
            face_final_seperator = ";"

        face_indicies_length = len(face_list)
        face_string = "%s;" % face_indicies_length
        for face_point_idx, face_index in enumerate(face_list):
            point_final_seperator = ","
            if face_point_idx == face_indicies_length - 1:
                point_final_seperator = ";"

            face_string += "%s%s" % (face_index, point_final_seperator)

        face_string += "%s\n" % face_final_seperator

        x_stream.write("%s%s" % (get_indentation(indent_level + 1), face_string))
    x_stream.write("\n")
    
    x_stream.write("%sMeshNormals {\n" % get_indentation(indent_level + 1))
    normal_count = len(mesh_dict["normals"])
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), normal_count))
    for normal_idx, normal_list in enumerate(mesh_dict["normals"]):
        final_seperator = ","
        if normal_idx == normal_count - 1:
            final_seperator = ";"

        i, j, k = normal_list
        x_stream.write("%s%s;%s;%s;%s\n" % (get_indentation(indent_level + 2), format_float(i, 6), format_float(j, 6), format_float(k, 6), final_seperator))

    normal_indices_count = len(mesh_dict["normal_indices"])
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), normal_indices_count))
    for normals_idx, normal_indices_list in enumerate(mesh_dict["normal_indices"]):
        normal_final_seperator = ","
        if normals_idx == normal_indices_count - 1:
            normal_final_seperator = ";"

        normal_indicies_length = len(normal_indices_list)
        normal_indicies_string = "%s;" % normal_indicies_length
        for normal_point_idx, normal_index in enumerate(normal_indices_list):
            point_final_seperator = ","
            if normal_point_idx == normal_indicies_length - 1:
                point_final_seperator = ";"

            normal_indicies_string += "%s%s" % (normal_index, point_final_seperator)

        normal_indicies_string += "%s\n" % normal_final_seperator

        x_stream.write("%s%s" % (get_indentation(indent_level + 2), normal_indicies_string))

    x_stream.write("%s}\n" % get_indentation(indent_level + 1))
    x_stream.write("\n")

    x_stream.write("%sMeshTextureCoords {\n" % get_indentation(indent_level + 1))
    texcoords_count = len(mesh_dict["texcoords"])
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), texcoords_count))
    for texcoord_idx, texcoord_list in enumerate(mesh_dict["texcoords"]):
        final_seperator = ","
        if texcoord_idx == texcoords_count - 1:
            final_seperator = ";"

        u, v = texcoord_list
        x_stream.write("%s%s;%s;%s\n" % (get_indentation(indent_level + 2), format_float(u, 6), format_float(v, 6), final_seperator))
    x_stream.write("%s}\n" % get_indentation(indent_level + 1))
    x_stream.write("\n")

    x_stream.write("%sVertexDuplicationIndices {\n" % get_indentation(indent_level + 1))
    dup_indices_count = len(mesh_dict["dup_indices"])
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), dup_indices_count))
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), mesh_dict["dup_preexport_count"]))
    for dup_idx, dup_index in enumerate(mesh_dict["dup_indices"]):
        final_seperator = ","
        if dup_idx == dup_indices_count - 1:
            final_seperator = ";"

        x_stream.write("%s%s%s\n" % (get_indentation(indent_level + 2), dup_index, final_seperator))
    x_stream.write("%s}\n" % get_indentation(indent_level + 1))
    x_stream.write("\n")

    x_stream.write("%sMeshMaterialList {\n" % get_indentation(indent_level + 1))
    material_count = len(mesh_dict["materials"])
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), material_count))
    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), face_count))
    for material_face_idx, material_index in enumerate(mesh_dict["material_indices"]):
        final_seperator = ","
        if material_face_idx == face_count - 1:
            final_seperator = ";"

        x_stream.write("%s%s%s\n" % (get_indentation(indent_level + 2), material_index, final_seperator))

    x_stream.write("\n")
    for material_idx, material_dict in enumerate(mesh_dict["materials"]):
        final_seperator = ","
        if material_idx == face_count - 1:
            final_seperator = ";"

        material_name = material_dict["name"]
        if material_name is None:
            material_name = ""

        texture_name = material_dict["texture"]

        dr, dg, db, da = material_dict["diffuse"]
        sr, sg, sb = material_dict["specular"]
        er, eg, eb = material_dict["emissive"]

        x_stream.write("%sMaterial %s {\n" % (get_indentation(indent_level + 2), material_name))
        x_stream.write("%s%s;%s;%s;%s;;\n" % (get_indentation(indent_level + 3), format_float(dr, 6), format_float(dg, 6), format_float(db, 6), format_float(da, 6)))
        x_stream.write("%s%s;\n" % (get_indentation(indent_level + 3), format_float(material_dict["power"], 6)))
        x_stream.write("%s%s;%s;%s;;\n" % (get_indentation(indent_level + 3), format_float(sr, 6), format_float(sg, 6), format_float(sb, 6)))
        x_stream.write("%s%s;%s;%s;;\n" % (get_indentation(indent_level + 3), format_float(er, 6), format_float(eg, 6), format_float(eb, 6)))
        x_stream.write("\n")
        if texture_name is not None:
            x_stream.write("%sTextureFilename {\n" % get_indentation(indent_level + 3))
            x_stream.write('%s"%s";\n' % (get_indentation(indent_level + 4), texture_name))
            x_stream.write("%s}\n" % get_indentation(indent_level + 3))

    x_stream.write("%s}\n" % get_indentation(indent_level + 2))
    x_stream.write("%s}\n" % get_indentation(indent_level + 1))
    if mesh_dict["bone_count"] > 0:
        x_stream.write("\n")
        x_stream.write("%sXSkinMeshHeader {\n" % get_indentation(indent_level + 1))
        x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), mesh_dict["max_weights_per_vertex"]))
        x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), mesh_dict["max_weights_per_face"]))
        x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), mesh_dict["bone_count"]))
        x_stream.write("%s}\n" % get_indentation(indent_level + 1))
        x_stream.write("\n")

        x_stream.write("%sSkinWeights {\n" % get_indentation(indent_level + 1))
        for skin_weight in mesh_dict["skin_weights"]:
            x_stream.write('%s"%s";\n' % (get_indentation(indent_level + 2), skin_weight["bone"]))
            point_count = len(skin_weight["indices"])
            x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), point_count))
            for point_idx, point_element in enumerate(skin_weight["indices"]):
                final_seperator = ","
                if point_idx == point_count - 1:
                    final_seperator = ";"

                x_stream.write("%s%s%s\n" % (get_indentation(indent_level + 2), point_element, final_seperator))
            for weight_idx, weight_element in enumerate(skin_weight["weights"]):
                final_seperator = ","
                if weight_idx == point_count - 1:
                    final_seperator = ";"

                x_stream.write("%s%s%s\n" % (get_indentation(indent_level + 2), format_float(weight_element, 6), final_seperator))

            transform_count = len(skin_weight["transform"])
            skin_transform_string = ""
            for skin_transform_idx, skin_transform in enumerate(skin_weight["transform"]):
                final_seperator = ","
                if skin_transform_idx == transform_count - 1:
                    final_seperator = ";"

                skin_transform_string += "%s%s" % (format_float(skin_transform, 6), final_seperator)

            x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), skin_transform_string))
            x_stream.write("%s}\n" % (get_indentation(indent_level + 1)))

    x_stream.write("%s}" % (get_indentation(indent_level + 0)))
    if not final_mesh:
        x_stream.write("\n")

def write_frame(frame_dict, x_stream, indent_level=0):
    frame_name = frame_dict["name"]
    if frame_name is None:
        frame_name = ""

    x_stream.write("%sFrame %s {\n" % (get_indentation(indent_level + 0), frame_name))
    x_stream.write("%s\n" % get_indentation(indent_level + 1))
    x_stream.write("\n")
    x_stream.write("%sFrameTransformMatrix {\n" % get_indentation(indent_level + 1))
    transform_count = len(frame_dict["transform"])
    transform_string = ""
    for frame_transform_idx, frame_transform in enumerate(frame_dict["transform"]):
        final_seperator = ","
        if frame_transform_idx == transform_count - 1:
            final_seperator = ";"

        transform_string += "%s%s" % (format_float(frame_transform, 6), final_seperator)

    x_stream.write("%s%s;\n" % (get_indentation(indent_level + 2), transform_string))

    x_stream.write("%s}\n" % get_indentation(indent_level + 1))
    if len(frame_dict["children"]) > 0: 
        x_stream.write("%s\n" % get_indentation(indent_level))

    if len(frame_dict["meshes"]) > 0:
        x_stream.write("\n")
    mesh_indent = indent_level + 1 
    for mesh_dict in frame_dict["meshes"]:
        write_mesh(mesh_dict, x_stream, mesh_indent)

    for child_dict in frame_dict["children"]:
        write_frame(child_dict, x_stream, indent_level + 1)

    x_stream.write("%s}\n" % get_indentation(indent_level + 0))

def parse_x_a_txt(text):
    tokens = TextAsset(text)

    x_dict = {
        "xof_header": None,
        "file_type": FileType.text.value,
        "compressed": CompressionType.uncompressed.value,
        "float_size": FloatType._32.value,
        "materials": [],
        "frames": []
    }
    
    while tokens.left() != 0:
        next_token = tokens.next()
        if next_token == "xof":
            x_dict["xof_header"] = next_token
            while len(x_dict["xof_header"]) < 16 and tokens.left() > 0:
                next_token = tokens.next()
                x_dict["xof_header"] = "%s %s" % (x_dict["xof_header"], next_token)
            
            tokens.next()
            tokens.next()
            tokens.next()
            tokens.next()
            tokens.next()
            tokens.next()
            tokens.next()
            tokens.next()
            tokens.next()

        elif next_token == "Material":
            parse_material(x_dict, x_dict, next_token, tokens)

        elif next_token == "Frame":
            parse_frame(x_dict, tokens, x_dict["frames"])

    return x_dict

def parse_x_b_txt(text):
    tokens = TextAsset(text)

    x_dict = {
        "xof_header": None,
        "templates": [],
        "anim_ticks_per_second": None,
        "materials": [],
        "frames": [],
        "meshes": [],
        "animation_set": []
    }
    
    while tokens.left() != 0:
        next_token = tokens.next()
        if next_token == "xof":
            x_dict["xof_header"] = next_token
            while len(x_dict["xof_header"]) < 16 and tokens.left() > 0:
                next_token = tokens.next()
                x_dict["xof_header"] = "%s %s" % (x_dict["xof_header"], next_token)

        elif next_token == "template":
            template_dict = {
                "name": "",
                "guid": "",
                "fields": []
            }

            next_token = tokens.next()
            if next_token != "{":
                template_dict["name"] = next_token
                next_token = tokens.next()

            if next_token == "{":
                next_token = tokens.next()
                while next_token != "}" and tokens.left() > 0:
                    if next_token.startswith("<"):
                        template_dict["guid"] = next_token
                    else:
                        field_dict = {}

                        field_keys = []
                        while next_token != ";" and tokens.left() > 0:
                            field_keys.append(next_token)
                            next_token = tokens.next()
                        if len(field_keys) == 2:
                            field_dict["type"] = field_keys[0]
                            field_dict["name"] = field_keys[1]
                        elif len(field_keys) == 3:
                            field_dict["is_array"] = field_keys[0]
                            field_dict["type"] = field_keys[1]
                            field_dict["name"] = field_keys[2]
                        else:
                            print("Template with more than 3 or 2 entries")

                        template_dict["fields"].append(field_dict)
                    next_token = tokens.next()

            x_dict["templates"].append(template_dict)

        elif next_token == "AnimTicksPerSecond":
            tokens.next()
            x_dict["anim_ticks_per_second"] = int(tokens.next())

        elif next_token == "Material":
            parse_material(x_dict, x_dict, next_token, tokens)

        elif next_token == "Frame":
            parse_frame(x_dict, tokens, x_dict["frames"])

        elif next_token == "Mesh":
            parse_mesh(x_dict, tokens, x_dict["meshes"])

        elif next_token == "AnimationSet":
            anim_dict = {"name": None, "frame_data": []}
            next_token = tokens.next()
            if next_token != "{":
                anim_dict["name"] = next_token
                next_token = tokens.next()

            next_token = tokens.next()
            while next_token != "}" and tokens.left() > 0:
                if next_token == "Animation":
                    frame_data_dict = {"frame_name": None, "key_type": 0, "keyframes": []}
                    tokens.next()
                    tokens.next()
                    tokens.next()
                    frame_data_dict["key_type"] = int(tokens.next())
                    tokens.next()
                    key_count = int(tokens.next())
                    tokens.next()
                    for key_idx in range(key_count):
                        keyframe_dict = {"keyframe_index": 0, "transform": []}
                        keyframe_dict["keyframe_index"] = int(tokens.next())
                        tokens.next()
                        keyframe_length = int(tokens.next())
                        tokens.next()
                        for keyframe_idx in range(keyframe_length):
                            keyframe_dict["transform"].append(float(tokens.next()))
                            tokens.next()
                        tokens.next()
                        tokens.next()

                        frame_data_dict["keyframes"].append(keyframe_dict)

                    tokens.next()
                    tokens.next()
                    frame_data_dict["frame_name"] = tokens.next()
                    tokens.next()
                    tokens.next()

                    anim_dict["frame_data"].append(frame_data_dict)
                next_token = tokens.next()
            x_dict["animation_set"].append(anim_dict)

    return x_dict

def read_x(file_path):
    x_dict = None
    version = 0
    is_binary = False
    is_compressed = False
    with file_path.open("rb") as x_stream:
        file_header = x_stream.read(16).decode('utf-8')
        if file_header == "xof 0302txt 0064":
            version = 0
        elif file_header == "xof 0303txt 0032":
            version = 1
        elif file_header == "xof 0303bin 0032":
            version = 1
            is_binary = True
        elif file_header == "xof 0303bzip0032":
            version = 1
            is_binary = True
            is_compressed = True

    if is_binary:
        if is_compressed:
            with file_path.open("rb") as x_stream:
                file_header = x_stream.read(16).decode('utf-8')
                data = x_stream.read()

                MSZIP_BLOCK = 0x8000
                MSZIP_MAGIC = b"CK"
                offset = 0

                unzipped_size, = struct.unpack_from("<I", data, offset)
                offset += 4

                output = bytearray()

                while offset < len(data):
                    # Read block header
                    uncompressed_size, block_size = struct.unpack_from("<HH", data, offset)
                    offset += 4

                    magic = data[offset:offset + 2]
                    offset += 2

                    if block_size > MSZIP_BLOCK:
                        raise ValueError("Unexpected compressed block size")

                    if magic != MSZIP_MAGIC:
                        raise ValueError("Unexpected compressed block magic")

                    # block_size includes the 2-byte magic
                    compressed_data = data[offset:offset + (block_size - 2)]
                    offset += (block_size - 2)

                    # Raw DEFLATE stream, 32k window
                    decompressed = zlib.decompress(compressed_data,wbits=-zlib.MAX_WBITS,bufsize=MSZIP_BLOCK)

                    output.extend(decompressed)

                output_path = os.path.expanduser("~/Desktop/output.bin")
                with open(output_path, "wb") as f:
                    f.write(output)
        else:
            print()
    else:
        if version == 0:
            x_dict = parse_x_a_txt(file_path)
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            file_path = os.path.join(desktop_path, "data.json")

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(x_dict, f, indent=4)

        elif version == 1:
            x_dict = parse_x_b_txt(file_path)

    return x_dict

def write_x(rmesh_dict, output_path):
    with output_path.open("w") as x_stream:
        xof_header = rmesh_dict["xof_header"]
        x_stream.write("%s\n" % xof_header)
        for template_dict in rmesh_dict["templates"]:
            template_name = template_dict["name"]
            if template_name is None:
                template_name = ""

            x_stream.write("template %s {\n" % template_name)
            x_stream.write("%s%s\n" % (get_indentation(1), template_dict["guid"]))
            for field_dict in template_dict["fields"]:
                field_items = field_dict.values()
                field_string = ""
                field_count = len(field_items)
                for field_idx, field_item in enumerate(field_items):
                    final_seperator = " "
                    if field_idx == field_count - 1:
                        final_seperator = ";"

                    field_string += "%s%s" % (field_item, final_seperator)
                
                x_stream.write("%s%s\n" % (get_indentation(1), field_string))
                
            x_stream.write("}\n")
            x_stream.write("\n")

        x_stream.write("\n")
        anim_ticks = rmesh_dict["anim_ticks_per_second"]
        if anim_ticks is not None:
            x_stream.write("AnimTicksPerSecond {\n")
            x_stream.write("%s%s;\n" % (get_indentation(1), anim_ticks))
            x_stream.write("}\n")
            x_stream.write("\n")

        for frame_dict in rmesh_dict["frames"]:
            write_frame(frame_dict, x_stream)

        x_stream.write("\n")
        mesh_count = len(rmesh_dict["meshes"])
        for mesh_idx, mesh_dict in enumerate(rmesh_dict["meshes"]):
            write_mesh(mesh_dict, x_stream, 0, (mesh_idx == mesh_count - 1))
