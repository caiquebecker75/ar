# Monta um .lxo (Modo) no Blender e exporta raw.glb para o pipeline de AR (prepare-glb → usdz).
# Genérico: escolhe malhas visíveis, aplica transformações e cópias (meshInst), texturas por projeção
# cúbica dos localizadores (no espaço local de cada malha), cores/transparência por grupo e verso das artes.
#
#   CFG=config.json /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/modo/build_lxo.py
#
# config.json (caminhos relativos ao próprio config):
# {
#   "lxo": "3D.lxo", "saida": "raw.glb", "diag": "diag",
#   "metros_por_unidade": 0.03532,          # 1 unidade da cena em metros
#   "malhas": [ { "camada": 7, "pos": [-10.1, 26.2, 0], "escala": 53.29, "copias": [[0,0,0]] } ],
#   "texturas": { "Frente": { "img": "tex/Frente.png", "pos": [x,y,z], "escala": [sx,sy,sz], "fora": "frente" } },
#   "cores": { "Preto": [0.01,0.01,0.01], "Transparência": { "cor": [0.8,0.8,0.8], "alfa": 0.25 } },
#   "bordas": { "grupos": ["Base-Branco"], "cor_grande": "Preto", "limite_m": 0.006 },
#   "verso": { "Frente": { "cor": [0.01,0.01,0.01] } },     # ou { "img": "...", "pos":..., "escala":... }
#   "padrao": [0.6, 0.6, 0.6]
# }
# "fora": frente (−Y do Blender = +Z no glTF) · tras · esquerda (−X) · direita (+X) · topo (+Z)
import bpy, bmesh, mathutils, os, struct, json, math

CFG = os.environ['CFG']
BASE = os.path.dirname(os.path.abspath(CFG)) + '/'
C = json.load(open(CFG))
os.chdir(BASE)
bpy.ops.wm.read_factory_settings(use_empty=True)

# ---------- leitura do .lxo ----------
d = open(C['lxo'], 'rb').read()
def cstr(b, o):
    e = b.index(b'\0', o); s = b[o:e]; e += 1
    if (e - o) % 2: e += 1
    return s.decode('utf8', 'replace'), e
tags = []; layers = []; cur = None
i = 12
while i < len(d) - 8:
    tag = d[i:i+4]; n = struct.unpack('>I', d[i+4:i+8])[0]; b = d[i+8:i+8+n]
    if tag == b'TAGS':
        o = 0; tags = []
        while o < n: s, o = cstr(b, o); tags.append(s)
    elif tag == b'LAYR':
        cur = {'idx': struct.unpack('>H', b[0:2])[0], 'name': cstr(b, 16)[0], 'chunks': []}; layers.append(cur)
    elif tag in (b'PNTS', b'POLS', b'PTAG') and cur is not None:
        cur['chunks'].append((tag.decode(), b))
    i += 8 + n + (n & 1)
tags = [t.replace('�', 'ê') for t in tags]

def vx(b, o):
    v = struct.unpack('>H', b[o:o+2])[0]
    if v >= 0xff00: return struct.unpack('>I', b[o:o+4])[0] & 0xffffff, o + 4
    return v, o + 2

def geometria(L):
    pts = []; polys = []; ptag = {}; base = 0
    for t, b in L['chunks']:
        if t == 'PNTS': pts = [struct.unpack('>3f', b[k:k+12]) for k in range(0, len(b), 12)]
        elif t == 'POLS' and b[:4] in (b'FACE', b'PSUB', b'SUBD'):
            base = len(polys); o = 4
            while o < len(b):
                nv = struct.unpack('>H', b[o:o+2])[0]; o += 2; f = []   # LXO: 16 bits cheios
                for _ in range(nv): v, o = vx(b, o); f.append(v)
                polys.append(f)
        elif t == 'PTAG' and b[:4] == b'MATR':
            o = 4
            while o < len(b):
                p, o = vx(b, o); tg = struct.unpack('>H', b[o:o+2])[0]; o += 2; ptag[base + p] = tg
    return pts, polys, ptag

M = C['metros_por_unidade']
FORA = {'frente': (0, -1, 0), 'tras': (0, 1, 0), 'esquerda': (-1, 0, 0), 'direita': (1, 0, 0), 'topo': (0, 0, 1)}

def lin(c):  # sRGB → linear
    return tuple((x / 12.92) if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)

mats = {}
def material(nome, cor=(0.6, 0.6, 0.6), img=None, alfa=1.0, um_lado=False, rough=0.6):
    if nome in mats: return mats[nome]
    m = bpy.data.materials.new(nome); m.use_nodes = True; nt = m.node_tree; bs = nt.nodes['Principled BSDF']
    bs.inputs['Roughness'].default_value = rough
    if img:
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(BASE + img); t.extension = 'CLIP'
        nt.links.new(t.outputs['Color'], bs.inputs['Base Color'])
    else:
        bs.inputs['Base Color'].default_value = (*cor, 1); m.diffuse_color = (*cor, alfa)
    if alfa < 1:
        bs.inputs['Alpha'].default_value = alfa
        try: m.surface_render_method = 'BLENDED'
        except Exception: m.blend_method = 'BLEND'
    m.use_backface_culling = um_lado
    mats[nome] = m; return m

def mat_do_grupo(tag):
    tex = C.get('texturas', {})
    if tag in tex: return material(tag, img=tex[tag]['img'], um_lado=True)
    c = C.get('cores', {}).get(tag)
    if isinstance(c, dict): return material(tag, cor=lin(c['cor']) if c.get('srgb') else tuple(c['cor']), alfa=c.get('alfa', 1.0), rough=c.get('rough', 0.6))
    if c: return material(tag, cor=tuple(c))
    return material('Padrao', cor=tuple(C.get('padrao', [0.6, 0.6, 0.6])))

def uv(tcfg, q, fora):   # q = coordenada local do Modo
    r = [(q[k] - tcfg['pos'][k]) / tcfg['escala'][k] for k in range(3)]
    fx, fy, fz = fora
    if fy < 0: u, v = r[0], r[1]
    elif fy > 0: u, v = -r[0], r[1]
    elif fx < 0: u, v = r[2], r[1]
    elif fx > 0: u, v = -r[2], r[1]
    else: u, v = r[0], -r[2]
    return (u + 0.5, v + 0.5)

me = bpy.data.meshes.new('peca'); bm = bmesh.new(); uvl = bm.loops.layers.uv.new('UVMap')
ordem = []; est = {}
def idx(m):
    if m.name not in ordem: ordem.append(m.name)
    return ordem.index(m.name)

for spec in C['malhas']:
    L = [x for x in layers if x['idx'] == spec['camada']][0]
    pts, polys, ptag = geometria(L)
    pos = spec.get('pos', [0, 0, 0]); esc = spec.get('escala', 1.0)
    for copia in spec.get('copias', [[0, 0, 0]]):
        def local(v):  # arquivo (LWO) → Modo local
            p = pts[v]; return (p[0], p[1], -p[2])
        def mundo(v):
            q = local(v); return tuple(q[k] * esc + pos[k] + copia[k] for k in range(3))
        def B(v):
            w = mundo(v); return mathutils.Vector((w[0] * M, -w[2] * M, w[1] * M))
        for fi, f in enumerate(polys):
            if len(f) < 3: continue
            tag = tags[ptag[fi]] if fi in ptag and ptag[fi] < len(tags) else 'Default'
            if tag in spec.get('ignorar', []): continue
            bordas = C.get('bordas', {})
            if tag in bordas.get('grupos', []):
                cs = [B(v) for v in dict.fromkeys(f)]
                ext = sorted([max(c.x for c in cs) - min(c.x for c in cs), max(c.y for c in cs) - min(c.y for c in cs), max(c.z for c in cs) - min(c.z for c in cs)])
                if ext[1] > bordas.get('limite_m', 0.006): tag = bordas['cor_grande']
            m = mat_do_grupo(tag)
            # polígono com furo (keyhole): separa laços e triangula
            loops = []; cur_ = []
            for v in f:
                if v in cur_:
                    k = cur_.index(v); sub = cur_[k:]; cur_ = cur_[:k+1]
                    if len(sub) >= 3: loops.append(sub)
                else: cur_.append(v)
            if len(cur_) >= 3: loops.append(cur_)
            if len(loops) == 1 and len(loops[0]) == len(f): grupos = [list(f)]
            else:
                loops.sort(key=len, reverse=True); flat = [v for Lp in loops for v in Lp]
                tri = mathutils.geometry.tessellate_polygon([[B(v) for v in Lp] for Lp in loops])
                grupos = [[flat[a], flat[b_], flat[c]] for a, b_, c in tri]
            tcfg = C.get('texturas', {}).get(tag)
            for g in grupos:
                try: face = bm.faces.new([bm.verts.new(B(v)) for v in g])
                except ValueError: continue
                face.material_index = idx(m); est[tag] = est.get(tag, 0) + 1
                if not tcfg: continue
                fora = mathutils.Vector(FORA[tcfg.get('fora', 'frente')])
                face.normal_update()
                if face.normal.dot(fora) < 0: face.normal_flip()
                for loop in face.loops:
                    v = min(g, key=lambda vv: (B(vv) - loop.vert.co).length)
                    loop[uvl].uv = uv(tcfg, local(v), tuple(fora))
                vs = C.get('verso', {}).get(tag)
                if vs is None: continue
                off = -fora * 0.001
                try: tras = bm.faces.new([bm.verts.new(l.vert.co + off) for l in reversed(list(face.loops))])
                except ValueError: continue
                if 'img' in vs:
                    tras.material_index = idx(material(tag + '-verso', img=vs['img'], um_lado=True))
                    for loop in tras.loops:
                        v = min(g, key=lambda vv: (B(vv) - (loop.vert.co - off)).length)
                        loop[uvl].uv = uv(vs, local(v), tuple(-fora))
                else:
                    tras.material_index = idx(material(tag + '-verso', cor=tuple(vs['cor']), um_lado=True))

bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
bm.to_mesh(me); bm.free()
for nome in ordem: me.materials.append(bpy.data.materials[nome])
ob = bpy.data.objects.new('peca', me); bpy.context.scene.collection.objects.link(ob)
# origem no centro da base
bb = [ob.matrix_world @ mathutils.Vector(c) for c in ob.bound_box]
cx = (min(p.x for p in bb) + max(p.x for p in bb)) / 2; cy = (min(p.y for p in bb) + max(p.y for p in bb)) / 2; z0 = min(p.z for p in bb)
me.transform(mathutils.Matrix.Translation((-cx, -cy, -z0)))
print('TRIS por grupo', est)
print('DIMS cm (L x P x A)', [round(x * 100, 1) for x in ob.dimensions])
bpy.ops.export_scene.gltf(filepath=BASE + C.get('saida', 'raw.glb'), export_format='GLB', export_image_format='JPEG', export_jpeg_quality=90)

# ---------- conferência ----------
diag = BASE + C.get('diag', 'diag') + '/'; os.makedirs(diag, exist_ok=True)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.color_type = 'TEXTURE'; sc.display.shading.light = 'STUDIO'
A = max(ob.dimensions); alvo = mathutils.Vector((0, 0, ob.dimensions.z / 2))
sc.render.resolution_x = 700; sc.render.resolution_y = int(700 * max(1, ob.dimensions.z / max(ob.dimensions.x, 1e-3)) ** 0.6)
cam = bpy.data.cameras.new('c'); cam.type = 'ORTHO'; cam.ortho_scale = A * 1.15
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
w = bpy.data.worlds.new('w'); sc.world = w
for n, loc in {'1_frente': (0, -3 * A, 0), '2_esquerda': (-3 * A, 0, 0), '3_direita': (3 * A, 0, 0), '4_tras': (0, 3 * A, 0)}.items():
    co.location = alvo + mathutils.Vector(loc); co.rotation_euler = (alvo - co.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = diag + f'{n}.png'; bpy.ops.render.render(write_still=True)
cam.type = 'PERSP'; cam.lens = 45
co.location = alvo + mathutils.Vector((-1.1 * A, -2.2 * A, 0.7 * A)); co.rotation_euler = (alvo - co.location).to_track_quat('-Z', 'Y').to_euler()
sc.render.filepath = diag + '5_iso.png'; bpy.ops.render.render(write_still=True)
