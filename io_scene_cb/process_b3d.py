#!/usr/bin/python3
# by Joric, https://github.com/joric/io_scene_b3d

import io
import os
import struct

class B3DParser:
    def __init__(self):
        self.fp = None

    def gets(self):
        s = b''
        while True:
            c = self.fp.read(1)
            if c == b'\x00':
                return s.decode(errors='ignore')
            s += c

    def i(self, n):
        return struct.unpack(n * 'i', self.fp.read(n * 4))

    def f(self, n):
        return struct.unpack(n * 'f', self.fp.read(n * 4))

    def next_chunk(self):
        pos = self.fp.tell()
        s1, s2, s3, s4, size = struct.unpack('4ci', self.fp.read(8))
        chunk = ''.join(chr(x[0]) for x in (s1, s2, s3, s4))
        next_pos = pos + size + 8
        return chunk, pos, size, next_pos

    def cb_result(self):
        return True

    def parse(self, filepath):
        filesize = os.stat(filepath).st_size
        self.fp = filepath.open("rb")
        stack = []

        while self.fp.tell() <= filesize - 8:
            while stack and stack[-1] == self.fp.tell():
                stack.pop()
                self.cb_prev()

            chunk, pos, size, next_pos = self.next_chunk()

            if chunk == 'BB3D':
                self.cb_data(chunk, {'version': self.i(1)[0]})
                continue

            elif chunk == 'ANIM':
                flags, frames = self.i(2)
                fps = self.f(1)[0]
                self.cb_data(chunk, {'anim': {'flags': flags, 'frames': frames, 'fps': fps}})

            elif chunk == 'SEQS':
                seqs = []
                while self.fp.tell() < next_pos:
                    name = self.gets()
                    start, end, flags = self.i(3)
                    seqs.append({'name': name, 'start': start, 'end': end, 'flags': flags})
                self.cb_data(chunk, {'sequences': seqs})

            elif chunk == 'TEXS':
                tex = []
                while self.fp.tell() < next_pos:
                    name = self.gets()
                    flags, blend = self.i(2)
                    pos2 = self.f(2)
                    scale = self.f(2)
                    rot = self.f(1)[0]
                    tex.append({
                        'name': name,
                        'flags': flags,
                        'blend': blend,
                        'position': pos2,
                        'scale': scale,
                        'rotation': rot
                    })
                self.cb_data(chunk, {'textures': tex})

            elif chunk == 'BRUS':
                n_texs = self.i(1)[0]
                mats = []
                while self.fp.tell() < next_pos:
                    name = self.gets()
                    rgba = self.f(4)
                    shine = self.f(1)[0]
                    blend, fx = self.i(2)
                    tids = self.i(n_texs)
                    mats.append({
                        'name': name,
                        'rgba': rgba,
                        'shine': shine,
                        'blend': blend,
                        'fx': fx,
                        'tids': tids
                    })
                self.cb_data(chunk, {'materials': mats})

            elif chunk == 'NODE':
                self.cb_next()
                stack.append(next_pos)
                name = self.gets()
                p = self.f(3)
                s = self.f(3)
                r = self.f(4)
                self.cb_data(chunk, {'name': name, 'position': p, 'scale': s, 'rotation': r})
                continue

            elif chunk == 'MESH':
                self.cb_data(chunk, {'mesh': {'brush_id': self.i(1)[0]}})
                continue

            elif chunk == 'VRTS':
                flags, tcs, tcss = self.i(3)
                v, n, c, u = [], [], [], []
                while self.fp.tell() < next_pos:
                    v.append(self.f(3))
                    if flags & 1: n.append(self.f(3))
                    if flags & 2: c.append(self.f(4))
                    if tcs * tcss: u.append(self.f(tcs * tcss))
                self.cb_data(chunk, {'vertices': v, 'normals': n, 'rgba': c, 'uvs': u})

            elif chunk == 'TRIS':
                brush_id = self.i(1)[0]
                faces = []
                while self.fp.tell() < next_pos:
                    faces.append(self.i(3))
                self.cb_data(chunk, {'brush_id': brush_id, 'indices': faces})

            elif chunk == 'KEYS':
                flags = self.i(1)[0]
                keys = []
                while self.fp.tell() < next_pos:
                    k = {'frame': self.i(1)[0]}
                    if flags & 1: k['position'] = self.f(3)
                    if flags & 2: k['scale'] = self.f(3)
                    if flags & 4: k['rotation'] = self.f(4)
                    keys.append(k)
                self.cb_data(chunk, {'flags': flags, 'keys': keys})

            elif chunk == 'BONE':
                bones = []
                while self.fp.tell() < next_pos:
                    vertex_idx = self.i(1)[0]
                    weight  = self.f(1)[0]
                    bones.append({
                        'vertex_idx': vertex_idx,
                        'weight': weight
                    })
                self.cb_data(chunk, {'bones': bones})

            self.fp.seek(next_pos)

        return self.cb_result()

class B3DList(B3DParser):
    def __init__(self):
        super().__init__()
        self.index = -1
        self.data = {'nodes': []}

    def cb_next(self):
        self.data['nodes'].append({'parent': self.index})
        self.index = len(self.data['nodes']) - 1

    def cb_prev(self):
        self.index = self.data['nodes'][self.index]['parent']

    def cb_data(self, chunk, data):
        if self.index != -1:
            node = self.data['nodes'][self.index]

        if chunk == 'NODE':
            node.update(data)

        elif chunk == 'MESH':
            node['mesh'] = data['mesh']

        elif chunk == 'VRTS':
            node['mesh'].update(data)

        elif chunk == 'TRIS':
            node['mesh'].setdefault('faces', []).append(data)

        elif chunk == 'BONE':
            node['bones'] = data['bones']

        elif chunk == 'KEYS':
            node.setdefault('key', []).append(data['keys'])

        elif chunk == 'ANIM':
            node['anim'] = data['anim']

        elif chunk == 'SEQS':
            node.setdefault('sequences', []).extend(data['sequences'])

        elif chunk in ('TEXS', 'BRUS'):
            self.data.update(data)

    def cb_result(self):
        return self.data

class B3DTree(B3DList):
    def cb_result(self):
        nodes = self.data['nodes']
        for n in nodes:
            n['nodes'] = []

        roots = []
        for n in nodes:
            if n['parent'] == -1:
                roots.append(n)
            else:
                nodes[n['parent']]['nodes'].append(n)
            del n['parent']

        self.data['nodes'] = roots
        return self.data

class ChunkWriter:
    def __init__(self):
        self.buf = io.BytesIO()

    def writes(self, s):
        self.buf.write(s.encode("utf8") + b"\x00")

    def i(self, *v):
        self.buf.write(struct.pack(f"{len(v)}i", *v))

    def f(self, *v):
        self.buf.write(struct.pack(f"{len(v)}f", *v))

    def raw(self, b):
        self.buf.write(b)

    def bytes(self):
        return self.buf.getvalue()

def make_chunk(tag, payload):
    return tag.encode("ascii") + struct.pack("i", len(payload)) + payload

def make_KEYS(keys):
    if not keys:
        return b''
    w = ChunkWriter()
    first = keys[0]
    flags = 0
    if 'position' in first: flags |= 1
    if 'scale' in first: flags |= 2
    if 'rotation' in first: flags |= 4
    w.i(flags)
    for k in keys:
        w.i(k['frame'])
        if flags & 1: w.f(*k['position'])
        if flags & 2: w.f(*k['scale'])
        if flags & 4: w.f(*k['rotation'])
    return make_chunk("KEYS", w.bytes())

def make_BONE(bones):
    w = ChunkWriter()

    for b in bones:
        w.i(b['vertex_idx'])
        w.f(b['weight'])

    return make_chunk("BONE", w.bytes())

def make_VRTS(mesh):
    w = ChunkWriter()
    flags = (1 if mesh.get('normals') else 0) | (2 if mesh.get('rgba') else 0)
    tcss = 2 if mesh.get('uvs') else 0
    tcs = (len(mesh['uvs'][0]) // tcss) if mesh.get('uvs') else 0
    w.i(flags, tcs, tcss)
    for i, v in enumerate(mesh['vertices']):
        w.f(*v)
        if flags & 1: w.f(*mesh['normals'][i])
        if flags & 2: w.f(*mesh['rgba'][i])
        if tcs * tcss:
            uv = mesh['uvs'][i]
            for j in range(tcs):
                w.f(*uv[j*2:j*2+2])
    return make_chunk("VRTS", w.bytes())

def make_TRIS(tris):
    w = ChunkWriter()
    w.i(tris['brush_id'])
    for face in tris['indices']:
        w.i(*face)
    return make_chunk("TRIS", w.bytes())

def make_MESH(mesh):
    w = ChunkWriter()
    w.i(mesh['brush_id'])
    w.raw(make_VRTS(mesh))
    for tris in mesh.get('faces', []):
        w.raw(make_TRIS(tris))
    return make_chunk("MESH", w.bytes())

def make_NODE(node):
    w = ChunkWriter()
    w.writes(node['name'])
    w.f(*node['position'])
    w.f(*node['scale'])
    w.f(*node['rotation'])

    if 'mesh' in node:
        w.raw(make_MESH(node['mesh']))

    if 'bones' in node:
        w.raw(make_BONE(node['bones']))

    for keys in node.get('key', []):
        w.raw(make_KEYS(keys))

    if 'anim' in node:
        w.raw(make_chunk("ANIM", struct.pack("2if",
            node['anim']['flags'],
            node['anim']['frames'],
            node['anim']['fps']
        )))

    for seq in node.get('sequences', []):
        w.raw(make_chunk("SEQS",
            seq['name'].encode() + b"\x00" +
            struct.pack("3i", seq['start'], seq['end'], seq['flags'])
        ))

    for child in node.get('nodes', []):
        w.raw(make_NODE(child))

    return make_chunk("NODE", w.bytes())

def write_b3d(path, data, version=1):
    payload = b""
    if 'textures' in data:
        w = ChunkWriter()

        for t in data['textures']:
            w.writes(t['name'])
            w.i(t['flags'], t['blend'])
            w.f(*t['position'])
            w.f(*t['scale'])
            w.f(t['rotation'])

        payload += make_chunk("TEXS", w.bytes())

    if 'materials' in data:
        mats = data['materials']

        n_texs = len(mats[0]['tids']) if mats else 0

        w = ChunkWriter()
        w.i(n_texs)

        for m in mats:
            w.writes(m['name'])
            w.f(*m['rgba'])
            w.f(m['shine'])
            w.i(m['blend'], m['fx'])

            w.i(*m['tids'])

        payload += make_chunk("BRUS", w.bytes())

    for node in data['nodes']:
        payload += make_NODE(node)

    with open(path, "wb") as f:
        f.write(b"BB3D")
        f.write(struct.pack("i", 4 + len(payload)))
        f.write(struct.pack("i", version))
        f.write(payload)

