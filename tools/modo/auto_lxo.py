# Monta um .lxo (Modo) no Blender lendo a árvore de shaders do PRÓPRIO arquivo, sem mapear textura na mão:
# malhas visíveis, transformações (com pais), grupos de material (ptag), camada de imagem de cima que está
# ligada, projeção UV (VMAP/VMAD), planar e cúbica pelos localizadores, cores e luminosos dos materiais.
#
#   CFG=config.json /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/modo/auto_lxo.py
#
# config.json (caminhos relativos ao próprio config):
# {
#   "lxo": "peca.lxo", "saida": "raw.glb", "diag": "diag",
#   "metros_por_unidade": 0.01,
#   "imagens": { "UV-Cubo3": "tex/cubo-uv-cubo3.jpg" },     # nome do arquivo no Modo (sem pasta/extensão) → imagem local
#   "excluir_tags": ["Sandro"],                              # grupos de material que não entram (Shadow Catcher sempre sai)
#   "excluir_camadas": [0],                                  # índice da camada (ordem dos itens mesh)
#   "incluir_camadas": [3],                                  # força camada escondida a entrar
#   "cores": { "Branco": [0.95, 0.95, 0.95] },               # sobrescreve cor de um grupo (linear)
#   "sem_textura": ["Testeira2"],                            # ignora imagem do grupo e usa só a cor
#   "decimar_tags": { "Black": 0.1 }                          # reduz só as faces desse grupo (ex.: estrutura de tubos)
# }
import bpy, bmesh, mathutils, os, struct, json, math, re, unicodedata, difflib

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
def vx(b, o):
    v = struct.unpack('>H', b[o:o+2])[0]
    if v >= 0xff00: return struct.unpack('>I', b[o:o+4])[0] & 0xffffff, o + 4
    return v, o + 2

chnm = []; items = []; layers = []; tags = []; cur = None
i = 12
while i < len(d) - 8:
    tag = d[i:i+4]; n = struct.unpack('>I', d[i+4:i+8])[0]; b = d[i+8:i+8+n]
    if tag == b'CHNM':
        o = 4
        while o < n: s, o = cstr(b, o); chnm.append(s)
    elif tag == b'TAGS':
        o = 0
        while o < n: s, o = cstr(b, o); tags.append(s)
    elif tag == b'LAYR':
        cur = {'idx': struct.unpack('>H', b[0:2])[0], 'name': cstr(b, 16)[0], 'chunks': []}; layers.append(cur)
    elif tag in (b'PNTS', b'POLS', b'VMAP', b'VMAD', b'PTAG') and cur is not None:
        cur['chunks'].append((tag.decode(), b))
    elif tag == b'ITEM':
        typ, o = cstr(b, 0); name, o = cstr(b, o); ref = struct.unpack('>I', b[o:o+4])[0]; o += 4
        it = {'id': ref, 'type': typ, 'name': name, 'links': [], 'ch': {}, 's': {}}
        while o + 6 <= n:
            st = b[o:o+4]; sn = struct.unpack('>H', b[o+4:o+6])[0]; sb = b[o+6:o+6+sn]
            try:
                if st == b'CHAN':
                    ci, ct = struct.unpack('>HH', sb[:4]); v = sb[4:]; t = ct & 0xff
                    if t in (1, 0x21): val = struct.unpack('>i', v[:4])[0]
                    elif t in (2, 0x22): val = struct.unpack('>f', v[:4])[0]
                    elif t in (3, 0x23): val = v.split(b'\0')[0].decode('utf8', 'replace')
                    else: val = None
                    it['ch'][chnm[ci] if ci < len(chnm) else ci] = val
                elif st == b'CHNV':
                    nm, o2 = cstr(sb, 0); o2 += 4; vals = []
                    while o2 + 6 <= len(sb):
                        sub, o3 = cstr(sb, o2); vals.append(struct.unpack('>f', sb[o3:o3+4])[0]); o2 = o3 + 4
                    it['ch'][nm] = vals
                elif st == b'CHNS':
                    ss = [m.decode('utf8', 'replace') for m in re.findall(rb'[ -~\x80-\xff]{2,}', sb)]
                    if ss:
                        full = ' '.join(ss); k = full.split(' ')[0]; it['s'][k] = full[len(k):].strip()
                elif st == b'LINK':
                    ln, o2 = cstr(sb, 0); it['links'].append((ln,) + struct.unpack('>II', sb[o2:o2+8]))
            except Exception:
                pass
            o += 6 + sn + (sn & 1)
        items.append(it)
    i += 8 + n + (n & 1)
byid = {it['id']: it for it in items}
parent = {}; kids = {}
for it in items:
    for l in it['links']:
        if l[0] == 'parent': parent[it['id']] = l[1]; kids.setdefault(l[1], []).append((l[2], it))

def ligado(it):
    x = it
    while x is not None:
        if x['ch'].get('enable') == 0: return False
        x = byid.get(parent.get(x['id']))
    return True

# ---------- transformações ----------
def xfrm(obj_id):
    T = mathutils.Vector((0, 0, 0)); R = mathutils.Matrix.Identity(4); S = mathutils.Vector((1, 1, 1))
    for x in items:
        if x['type'] not in ('translation', 'rotation', 'scale'): continue
        if not any(l[1] == obj_id for l in x['links']): continue
        if x['type'] == 'translation' and isinstance(x['ch'].get('pos'), list): T += mathutils.Vector(x['ch']['pos'])
        if x['type'] == 'scale' and isinstance(x['ch'].get('scl'), list):
            S = mathutils.Vector([S[k] * x['ch']['scl'][k] for k in range(3)])
        if x['type'] == 'rotation' and isinstance(x['ch'].get('rot'), list):
            r = x['ch']['rot']; ordem = x['ch'].get('order') or 'xyz'
            ordem = ['XYZ', 'XZY', 'YXZ', 'YZX', 'ZXY', 'ZYX'][ordem] if isinstance(ordem, int) else str(ordem).upper()
            if any(abs(a) > 1e-6 for a in r) and sum(abs(a) > 1e-6 for a in r) > 1: print('AVISO rotação em mais de um eixo', obj_id, r, ordem)
            M = mathutils.Matrix.Identity(4)
            for eixo in ordem:   # o primeiro eixo da ordem é aplicado primeiro
                M = mathutils.Matrix.Rotation(r['XYZ'.index(eixo)], 4, eixo) @ M
            R = M @ R
    return mathutils.Matrix.Translation(T) @ R @ mathutils.Matrix.Diagonal((*S, 1))
def mundo_de(obj_id):
    M = xfrm(obj_id); p = parent.get(obj_id)
    while p is not None and p in byid and byid[p]['type'] in ('locator', 'groupLocator', 'mesh', 'meshInst'):
        M = xfrm(p) @ M; p = parent.get(p)
    return M

# ---------- materiais pela árvore de shaders ----------
def norm(s):
    s = os.path.splitext(os.path.basename(s.replace('\\', '/')))[0]
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', s)
IMGS = {norm(k): v for k, v in C.get('imagens', {}).items()}
def imagem_local(fn):
    k = norm(fn)
    if k in IMGS: return IMGS[k]
    m = difflib.get_close_matches(k, IMGS.keys(), n=1, cutoff=0.85)
    return IMGS[m[0]] if m else None

base_mat = next((x for x in items if x['type'] == 'advancedMaterial' and x['name'] == 'Base Material'), None)
def cor_mat(x):
    dc = x['ch'].get('diffCol'); amt = x['ch'].get('diffAmt') or 1.0
    c = [min(1.0, v * max(amt, 0.0)) for v in dc] if isinstance(dc, list) else [0.6, 0.6, 0.6]
    return c, (x['ch'].get('radiance') or 0.0), 1.0 - (x['ch'].get('tranAmt') or 0.0), x['ch'].get('rough') or 0.4

decisao = {}
def plano(tag):
    if tag in decisao: return decisao[tag]
    masks = [x for x in items if x['type'] == 'mask' and x['s'].get('ptag') == tag and ligado(x)]
    info = {'cor': [0.6, 0.6, 0.6], 'lumi': 0.0, 'alfa': 1.0, 'rough': 0.4, 'img': None, 'loc': None, 'arquivo': None}
    if base_mat: info['cor'], info['lumi'], info['alfa'], info['rough'] = cor_mat(base_mat)
    if masks:
        filhos = sorted(kids.get(masks[0]['id'], []), key=lambda k: -k[0])
        mat = next((k for _, k in filhos if k['type'] == 'advancedMaterial' and k['ch'].get('enable') != 0), None)
        if mat: info['cor'], info['lumi'], info['alfa'], info['rough'] = cor_mat(mat)
        if tag not in C.get('sem_textura', []):
            for _, k in filhos:
                if k['type'] != 'imageMap' or k['ch'].get('enable') == 0 or k['s'].get('effect') != 'diffColor': continue
                shades = [byid.get(l[1]) for l in k['links'] if l[0] == 'shadeLoc']
                loc = next((s for s in shades if s and s['type'] == 'txtrLocator'), None)
                vs = next((s for s in shades if s and s['type'] == 'videoStill'), None)
                if not vs or not loc: continue
                fn = vs['s'].get('filename', ''); img = imagem_local(fn)
                info['arquivo'] = fn
                if img is None: print('AVISO sem imagem local para', tag, '→', fn); continue
                L = {'proj': loc['ch'].get('projType'), 'eixo': loc['ch'].get('projAxis', 2), 'uv': loc['s'].get('uvMap', ''),
                     'pos': [0, 0, 0], 'esc': [1, 1, 1]}
                for x in items:
                    if x['type'] in ('translation', 'scale') and any(l[1] == loc['id'] for l in x['links']):
                        if isinstance(x['ch'].get('pos'), list): L['pos'] = x['ch']['pos']
                        if isinstance(x['ch'].get('scl'), list): L['esc'] = x['ch']['scl']
                info['img'] = img; info['loc'] = L
                break
    over = C.get('cores', {}).get(tag)
    if over is not None:
        if isinstance(over, dict): info.update(over)
        else: info['cor'] = over; info['img'] = None
    decisao[tag] = info; return info

mats = {}
def material(tag):
    if tag in mats: return mats[tag]
    p = plano(tag)
    m = bpy.data.materials.new(tag); m.use_nodes = True; nt = m.node_tree; bs = nt.nodes['Principled BSDF']
    bs.inputs['Roughness'].default_value = max(0.25, min(0.9, p['rough']))
    if p['img']:
        t = nt.nodes.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(BASE + p['img']); t.extension = 'REPEAT'
        nt.links.new(t.outputs['Color'], bs.inputs['Base Color'])
        if p['img'].lower().endswith('.png') and C.get('alfa_das_imagens'):
            nt.links.new(t.outputs['Alpha'], bs.inputs['Alpha'])
    else:
        bs.inputs['Base Color'].default_value = (*p['cor'], 1); m.diffuse_color = (*p['cor'], 1)
    if p['lumi'] > 0.5:
        bs.inputs['Emission Color'].default_value = (*p['cor'], 1); bs.inputs['Emission Strength'].default_value = 1.0
    if p['alfa'] < 1:
        bs.inputs['Alpha'].default_value = p['alfa']
        try: m.surface_render_method = 'BLENDED'
        except Exception: m.blend_method = 'BLEND'
    m.use_backface_culling = False
    mats[tag] = m; return m

# ---------- geometria ----------
def geometria(L):
    pts = []; polys = []; ptag = {}; vmap = {}; vmad = {}; base = 0
    for t, b in L['chunks']:
        if t == 'PNTS': pts = [struct.unpack('>3f', b[k:k+12]) for k in range(0, len(b), 12)]
        elif t == 'POLS':
            if b[:4] not in (b'FACE', b'PSUB', b'SUBD'): continue
            base = len(polys); o = 4
            while o < len(b):
                nv = struct.unpack('>H', b[o:o+2])[0]; o += 2; f = []   # LXO: 16 bits cheios
                for _ in range(nv): v, o = vx(b, o); f.append(v)
                polys.append(f)
        elif t == 'PTAG' and b[:4] == b'MATR':
            o = 4
            while o < len(b):
                p, o = vx(b, o); tg = struct.unpack('>H', b[o:o+2])[0]; o += 2; ptag[base + p] = tg
        elif t in ('VMAP', 'VMAD') and b[:4] == b'TXUV':
            dim = struct.unpack('>H', b[4:6])[0]; nome, o = cstr(b, 6)
            alvo = (vmap if t == 'VMAP' else vmad).setdefault(nome, {})
            while o < len(b):
                v, o = vx(b, o)
                if t == 'VMAD': p, o = vx(b, o)
                uvv = struct.unpack('>%df' % dim, b[o:o+4*dim]); o += 4 * dim
                if t == 'VMAP': alvo[v] = uvv[:2]
                else: alvo[(v, base + p)] = uvv[:2]
    return pts, polys, ptag, vmap, vmad

M = C['metros_por_unidade']
excl_tags = set(C.get('excluir_tags', [])) | {'Shadow Catcher'}
DEC = C.get('decimar_tags', {})
meshes = [it for it in items if it['type'] == 'mesh']
objetos = []; est = {}
for k, (it, L) in enumerate(zip(meshes, layers)):
    vis = it['ch'].get('visible')
    if k in C.get('excluir_camadas', []): continue
    if vis in ('allOff', 'off') and k not in C.get('incluir_camadas', []): continue
    pts, polys, ptag, vmap, vmad = geometria(L)
    if not polys: continue
    Mx = mundo_de(it['id']); espelha = Mx.to_3x3().determinant() < 0
    alvos = {}   # '' = malha da camada; grupos de decimar_tags ficam em malha própria
    def alvo(key):
        if key not in alvos:
            b_ = bmesh.new(); alvos[key] = {'bm': b_, 'uvl': b_.loops.layers.uv.new('UVMap'), 'ordem': [], 'n': 0}
        return alvos[key]
    local = lambda v: mathutils.Vector((pts[v][0], pts[v][1], -pts[v][2]))
    def B(v):
        w = Mx @ local(v); return mathutils.Vector((w.x * M, -w.z * M, w.y * M))
    for fi, f in enumerate(polys):
        if len(f) < 3: continue
        tg = tags[ptag[fi]] if fi in ptag and ptag[fi] < len(tags) else 'Default'
        if tg in excl_tags or tg.endswith('.lxl'): continue
        p = plano(tg); m = material(tg)
        A_ = alvo(tg if tg in DEC else ''); bm, uvl, ordem = A_['bm'], A_['uvl'], A_['ordem']
        if m.name not in ordem: ordem.append(m.name)
        # polígono com furo (keyhole): separa laços e triangula
        loops = []; cur_ = []
        for v in f:
            if v in cur_:
                kk = cur_.index(v); sub = cur_[kk:]; cur_ = cur_[:kk+1]
                if len(sub) >= 3: loops.append(sub)
            else: cur_.append(v)
        if len(cur_) >= 3: loops.append(cur_)
        if len(loops) == 1 and len(loops[0]) == len(f): grupos = [list(f)]
        else:
            loops.sort(key=len, reverse=True); flat = [v for Lp in loops for v in Lp]
            tri = mathutils.geometry.tessellate_polygon([[B(v) for v in Lp] for Lp in loops])
            grupos = [[flat[a], flat[b_], flat[c]] for a, b_, c in tri]
        # normal local (Newell) para a projeção cúbica
        nrm = mathutils.Vector((0, 0, 0)); q = [local(v) for v in dict.fromkeys(f)]
        for a in range(len(q)):
            c1, c2 = q[a], q[(a + 1) % len(q)]
            nrm += mathutils.Vector(((c1.y - c2.y) * (c1.z + c2.z), (c1.z - c2.z) * (c1.x + c2.x), (c1.x - c2.x) * (c1.y + c2.y)))
        def uv_de(v):
            Lc = p['loc']
            if not Lc: return (0.0, 0.0)
            if Lc['proj'] == 'uv':
                nome = Lc['uv'] or 'Texture'
                if nome not in vmap and nome not in vmad: nome = next(iter(vmap or vmad), nome)
                u = vmad.get(nome, {}).get((v, fi)) or vmap.get(nome, {}).get(v) or (0.0, 0.0)
                return (u[0], u[1])
            qv = local(v); r = [(qv[a] - Lc['pos'][a]) / (Lc['esc'][a] or 1) for a in range(3)]
            if Lc['proj'] == 'planar':
                e = Lc['eixo']
                if e == 2: u, w = r[0], r[1]
                elif e == 1: u, w = r[0], -r[2]
                else: u, w = -r[2], r[1]
            else:   # cúbica: planar pelo eixo dominante da face; o sentido do polígono no Modo não é confiável
                ax = max(range(3), key=lambda a: abs(nrm[a]))
                if ax == 2: u, w = r[0], r[1]
                elif ax == 0: u, w = -r[2], r[1]
                else: u, w = r[0], -r[2]
            return (u + 0.5, w + 0.5)
        for g in grupos:
            vs_ = list(reversed(g)) if espelha else g
            try: face = bm.faces.new([bm.verts.new(B(v)) for v in vs_])
            except ValueError: continue
            face.material_index = ordem.index(m.name); A_['n'] += 1; est[tg] = est.get(tg, 0) + 1
            for lp, v in zip(face.loops, vs_): lp[uvl].uv = uv_de(v)
    for key, A_ in alvos.items():
        bm = A_['bm']
        if not A_['n']: bm.free(); continue
        bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)   # o Modo renderiza os dois lados; o Quick Look não
        me = bpy.data.meshes.new(f'camada{k}{key}'); bm.to_mesh(me); bm.free()
        for nome in A_['ordem']: me.materials.append(bpy.data.materials[nome])
        ob_ = bpy.data.objects.new(f'camada{k}-{L["name"]}{"-" + key if key else ""}', me); bpy.context.scene.collection.objects.link(ob_)
        if key:
            antes = len(me.polygons); bpy.context.view_layer.objects.active = ob_
            mod = ob_.modifiers.new('reduz', 'DECIMATE'); mod.ratio = DEC[key]
            bpy.ops.object.modifier_apply(modifier='reduz')
            print('DECIMAR', key, antes, '->', len(ob_.data.polygons))
        objetos.append(ob_)
        print(f'CAMADA {k} {L["name"]!r} {key or ""} faces={A_["n"]} espelha={espelha}')

for tg, p in decisao.items():
    print('GRUPO', repr(tg), 'img=', p['img'], 'proj=', p['loc'] and p['loc']['proj'], 'cor=', [round(c, 3) for c in p['cor']], 'lumi=', p['lumi'], 'modo=', p['arquivo'] and os.path.basename(p['arquivo']))

# frente da peça em +Z do glTF (−Y do Blender): "girar_y" em graus, sentido anti-horário visto de cima
if C.get('girar_y'):
    for o in objetos: o.data.transform(mathutils.Matrix.Rotation(math.radians(C['girar_y']), 4, 'Z'))
# origem no centro da base (todas as malhas juntas)
bb =[o.matrix_world @ mathutils.Vector(c) for o in objetos for c in o.bound_box]
cx = (min(p.x for p in bb) + max(p.x for p in bb)) / 2; cy = (min(p.y for p in bb) + max(p.y for p in bb)) / 2; z0 = min(p.z for p in bb)
for o in objetos: o.data.transform(mathutils.Matrix.Translation((-cx, -cy, -z0)))
dims = [max(p.x for p in bb) - min(p.x for p in bb), max(p.y for p in bb) - min(p.y for p in bb), max(p.z for p in bb) - min(p.z for p in bb)]
print('TRIS por grupo', est)
print('DIMS cm (L x P x A)', [round(x * 100, 1) for x in dims])
bpy.ops.export_scene.gltf(filepath=BASE + C.get('saida', 'raw.glb'), export_format='GLB', export_image_format='AUTO')

# ---------- conferência (faces de costas escondidas: face invertida aparece como buraco) ----------
diag = BASE + C.get('diag', 'diag') + '/'; os.makedirs(diag, exist_ok=True)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.color_type = 'TEXTURE'; sc.display.shading.light = 'STUDIO'
sc.display.shading.show_backface_culling = bool(C.get('diag_culling', True))
A = max(dims); alvo = mathutils.Vector((0, 0, dims[2] / 2))
sc.render.resolution_x = 700; sc.render.resolution_y = int(700 * max(0.5, min(1.6, dims[2] / max(dims[0], 1e-3))))
cam = bpy.data.cameras.new('c'); cam.type = 'ORTHO'; cam.ortho_scale = A * 1.15
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
w = bpy.data.worlds.new('w'); sc.world = w
for nome, loc in {'1_frente': (0, -3 * A, 0), '2_esquerda': (-3 * A, 0, 0), '3_direita': (3 * A, 0, 0), '4_tras': (0, 3 * A, 0)}.items():
    co.location = alvo + mathutils.Vector(loc); co.rotation_euler = (alvo - co.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = diag + f'{nome}.png'; bpy.ops.render.render(write_still=True)
cam.type = 'PERSP'; cam.lens = 45
co.location = alvo + mathutils.Vector((1.1 * A, -2.2 * A, 0.7 * A)); co.rotation_euler = (alvo - co.location).to_track_quat('-Z', 'Y').to_euler()
sc.render.filepath = diag + '5_iso.png'; bpy.ops.render.render(write_still=True)
