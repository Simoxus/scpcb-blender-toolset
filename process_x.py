import os
import re
import json

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
    """Helper class for reading in JMS/JMA/ASS files"""

    __comment_regex = re.compile("[^\"]*?;(?!.*\")")

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

                mesh_dict["normal_indices"].append(face_indicies)

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
            print(material_dict["name"])
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
            print()
        else:
            print()
    else:
        if version == 0:
            x_dict = parse_x_a_txt(file_path)
        elif version == 1:
            x_dict = parse_x_b_txt(file_path)

    return x_dict

def write_x(rmesh_dict, output_path, file_type):
    print()