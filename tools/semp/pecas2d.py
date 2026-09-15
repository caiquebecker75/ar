# Monta em 3D as peças de PDV que só existem como arte plana (orelha, topper, placa, banner, tapete, totem...).
# O recorte da peça sai da própria arte (transparência do PNG ou fundo claro), com espessura real,
# e pode ser aplicada num modelo já pronto (ex.: o ar-condicionado lido do .lxo).
#
#   CFG=pecas.json PECA=orelha /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/semp/pecas2d.py
#
# pecas.json (metros; frente da peça em −Y do Blender = +Z do glTF; caminhos relativos ao config):
# { "orelha": { "saida": "build/orelha/raw.glb", "itens": [
#     { "tipo": "glb", "arquivo": "ac/raw.glb", "pos": [0, 0, 1.2] },
#     { "tipo": "recorte", "img": "tex/orelha-1.png", "largura": 0.10, "altura": 0.188, "espessura": 0.002,
#       "pos": [-0.4, -0.09, 1.32], "incl": 0, "rot_z": 0, "mascara": "alfa|escuro|claro|nenhuma", "grade": 300,
#       "verso": [240, 240, 240], "borda": [245, 245, 245] },            # verso "img" repete a arte atrás
#       ("curva": 0.04 curva o painel na largura, "segmento": colunas por faceta)
#     { "tipo": "caixa", "tam": [1.88, 0.5, 1.25], "pos": [0, 0.3, 0], "cor": [190, 160, 120] },   # pos = centro da base
#     { "tipo": "cabo", "de": [x, y, z], "ate": [x, y, z], "raio": 0.0008, "cor": [200, 200, 200] },
#     { "tipo": "marco_chao" } ] } }                                     # quadrado invisível em z=0 (peça suspensa)
# "pos" do recorte = centro da peça; "incl" gira em X (−90 deita no chão, arte para cima), "rot_z" gira em Z.
import bpy, bmesh, mathutils, os, json, math
import numpy as np

CFG = os.environ['CFG']
BASE = os.path.dirname(os.path.abspath(CFG)) + '/'
os.chdir(BASE)
PECA = os.environ['PECA']
P = json.load(open(CFG))[PECA]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.image_settings.quality = 90

def lin(c):  # 0-255 sRGB → linear
    return tuple(((x / 255) / 12.92) if x / 255 <= 0.04045 else (((x / 255) + 0.055) / 1.055) ** 2.4 for x in c)

def mat_cor(nome, cor, alfa=1.0, rough=0.55, metal=0.0):
    if nome in bpy.data.materials: return bpy.data.materials[nome]
    m = bpy.data.materials.new(nome); m.use_nodes = True; bs = m.node_tree.nodes['Principled BSDF']
    c = lin(cor); bs.inputs['Base Color'].default_value = (*c, 1); m.diffuse_color = (*c, 1)
    bs.inputs['Roughness'].default_value = rough; bs.inputs['Metallic'].default_value = metal
    if alfa < 1:
        bs.inputs['Alpha'].default_value = alfa
        try: m.surface_render_method = 'BLENDED'
        except Exception: m.blend_method = 'BLEND'
    m.use_backface_culling = True   # geometria já fechada: o prepare-glb não duplica o verso
    return m

def mat_img(nome, caminho):
    m = bpy.data.materials.new(nome); m.use_nodes = True; nt = m.node_tree; bs = nt.nodes['Principled BSDF']
    t = nt.nodes.new('ShaderNodeTexImage'); t.image = bpy.data.images.load(caminho); t.extension = 'EXTEND'
    nt.links.new(t.outputs['Color'], bs.inputs['Base Color']); bs.inputs['Roughness'].default_value = 0.45
    m.use_backface_culling = True
    return m

def arte(item, idx):
    """Lê a arte, calcula a máscara do recorte e grava uma cópia opaca com a cor 'sangrada' para fora do recorte."""
    img = bpy.data.images.load(BASE + item['img']); w, h = img.size
    px = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(h, w, 4)   # linha 0 = base da imagem
    rgb = px[..., :3].copy(); a = px[..., 3]
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    modo = item.get('mascara', 'alfa')
    if modo == 'alfa': mask = a > 0.5
    elif modo == 'escuro': mask = (lum < 0.85) & (a > 0.5)      # peça escura em fundo branco
    elif modo == 'claro': mask = (lum > 0.02) & (a > 0.5)       # fundo preto
    else: mask = np.ones((h, w), bool)
    if item.get('cortar_margem'):                                # a medida vale para a peça, não para a tela do arquivo
        ys, xs = np.nonzero(mask); y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        rgb, mask, px = rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1], px[y0:y1, x0:x1]
        h, w = mask.shape
    item.setdefault('altura', item['largura'] * h / w)
    cheio = mask.copy()
    for _ in range(24):                                          # sangria: evita franja escura na borda do recorte
        vazio = ~cheio
        if not vazio.any(): break
        soma = np.zeros_like(rgb); n = np.zeros((h, w), np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            f = np.roll(cheio, (dy, dx), (0, 1)); leva = vazio & f
            soma[leva] += np.roll(rgb, (dy, dx), (0, 1))[leva]; n[leva] += 1
        novo = n > 0; rgb[novo] = soma[novo] / n[novo][:, None]; cheio |= novo
    out = np.concatenate([rgb, np.ones((h, w, 1), np.float32)], -1).ravel()
    os.makedirs(BASE + 'build/tex', exist_ok=True)
    caminho = BASE + f'build/tex/{PECA}-{idx}.jpg'
    im2 = bpy.data.images.new(f'{PECA}-{idx}', w, h); im2.pixels.foreach_set(out)
    im2.filepath_raw = caminho; im2.file_format = 'JPEG'; im2.save()
    bpy.data.images.remove(img); bpy.data.images.remove(im2)
    return caminho, mask, w, h

def matriz(item):
    return (mathutils.Matrix.Translation(item.get('pos', [0, 0, 0]))
            @ mathutils.Matrix.Rotation(math.radians(item.get('rot_z', 0)), 4, 'Z')
            @ mathutils.Matrix.Rotation(math.radians(item.get('incl', 0)), 4, 'X'))

objetos = []
def novo_objeto(nome, bm, materiais):
    me = bpy.data.meshes.new(nome); bm.to_mesh(me); bm.free()
    for m in materiais: me.materials.append(m)
    ob = bpy.data.objects.new(nome, me); bpy.context.scene.collection.objects.link(ob); objetos.append(ob)
    return ob

for idx, it in enumerate(P['itens']):
    tipo = it['tipo']
    if tipo == 'glb':
        antes = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=BASE + it['arquivo'])
        M = matriz(it)
        for ob in set(bpy.data.objects) - antes:
            if ob.parent is None: ob.matrix_world = M @ ob.matrix_world
            if ob.type == 'MESH': objetos.append(ob)
    elif tipo == 'recorte':
        caminho, mask, w, h = arte(it, idx)
        W, H, E = it['largura'], it['altura'], it.get('espessura', 0.002)
        cs = max(1, int(math.ceil(max(w, h) / it.get('grade', 300))))
        ch, cw = -(-h // cs), -(-w // cs)
        pad = np.zeros((ch * cs, cw * cs), np.float32); pad[:h, :w] = mask
        cel = pad.reshape(ch, cs, cw, cs).mean((1, 3)) > 0.5
        M = matriz(it)
        bm = bmesh.new(); uvl = bm.loops.layers.uv.new('UVMap')
        sag = it.get('curva', 0.0)   # flecha do arco (m): painel curvado na largura, centro para a frente
        R = (W * W / 4 + sag * sag) / (2 * sag) if sag else 0
        def P3(X, Y, t):
            x = X / w * W - W / 2
            dy = -(math.sqrt(max(R * R - x * x, 0)) - (R - sag)) if sag else 0
            return M @ mathutils.Vector((x, t + dy, Y / h * H - H / 2))
        passo = max(1, it.get('segmento', 6)) if sag else 10 ** 9   # painel curvo: quebra as faixas em segmentos
        def face(pts, mi, uvs=None):
            f = bm.faces.new([bm.verts.new(p) for p in pts]); f.material_index = mi
            if uvs:
                for lp, uv in zip(f.loops, uvs): lp[uvl].uv = uv
        verso_img = it.get('verso') == 'img'
        for r in range(ch):
            c = 0
            while c < cw:
                if not cel[r, c]: c += 1; continue
                c1 = c
                while c1 < cw and cel[r, c1] and c1 - c < passo: c1 += 1
                X0, X1, Y0, Y1 = c * cs, min(c1 * cs, w), r * cs, min((r + 1) * cs, h)
                uv = [(X0 / w, Y0 / h), (X1 / w, Y0 / h), (X1 / w, Y1 / h), (X0 / w, Y1 / h)]
                face([P3(X0, Y0, 0), P3(X1, Y0, 0), P3(X1, Y1, 0), P3(X0, Y1, 0)], 0, uv)                          # frente (−Y)
                face([P3(X0, Y1, E), P3(X1, Y1, E), P3(X1, Y0, E), P3(X0, Y0, E)], 0 if verso_img else 1,
                     [uv[3], uv[2], uv[1], uv[0]] if verso_img else None)                                            # verso (+Y)
                face([P3(X0, Y0, 0), P3(X0, Y1, 0), P3(X0, Y1, E), P3(X0, Y0, E)], 2)                             # esquerda
                face([P3(X1, Y0, E), P3(X1, Y1, E), P3(X1, Y1, 0), P3(X1, Y0, 0)], 2)                             # direita
                if r == 0 or not cel[r - 1, c:c1].all():
                    face([P3(X0, Y0, 0), P3(X0, Y0, E), P3(X1, Y0, E), P3(X1, Y0, 0)], 2)                         # base
                if r == ch - 1 or not cel[r + 1, c:c1].all():
                    face([P3(X1, Y1, 0), P3(X1, Y1, E), P3(X0, Y1, E), P3(X0, Y1, 0)], 2)                         # topo
                c = c1
        mats = [mat_img(f'{PECA}-arte-{idx}', caminho), mat_cor(f'verso-{idx}', it.get('verso', [240, 240, 240]) if not verso_img else [240, 240, 240]),
                mat_cor(f'borda-{idx}', it.get('borda', [245, 245, 245]))]
        novo_objeto(f'recorte-{idx}', bm, mats)
        print(f'RECORTE {idx} {it["img"]} {W*100:.1f} × {H*100:.1f} cm, grade {cw}x{ch}, faces {len(bpy.data.objects[f"recorte-{idx}"].data.polygons)}')
    elif tipo == 'caixa':
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        L, D, A = it['tam']; x, y, z = it.get('pos', [0, 0, 0])
        bmesh.ops.transform(bm, matrix=mathutils.Matrix.Translation((x, y, z + A / 2)) @ mathutils.Matrix.Diagonal((L, D, A, 1)), verts=bm.verts)
        novo_objeto(f'caixa-{idx}', bm, [mat_cor(f'caixa-{idx}', it.get('cor', [200, 200, 200]), rough=it.get('rough', 0.8), metal=it.get('metal', 0.0))])
    elif tipo == 'cabo':
        a, b = mathutils.Vector(it['de']), mathutils.Vector(it['ate']); d = b - a
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, segments=8, radius1=it.get('raio', 0.0008), radius2=it.get('raio', 0.0008), depth=d.length)
        R = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
        bmesh.ops.transform(bm, matrix=mathutils.Matrix.Translation((a + b) / 2) @ R, verts=bm.verts)
        novo_objeto(f'cabo-{idx}', bm, [mat_cor(f'cabo-{idx}', it.get('cor', [200, 200, 200]), rough=0.3, metal=it.get('metal', 0.6))])
    elif tipo == 'marco_chao':
        bm = bmesh.new(); s = 0.01
        bm.faces.new([bm.verts.new(v) for v in ((-s, -s, 0), (s, -s, 0), (s, s, 0), (-s, s, 0))])
        novo_objeto(f'marco-{idx}', bm, [mat_cor('marco', [255, 255, 255], alfa=0.01)])

bb = [o.matrix_world @ mathutils.Vector(c) for o in objetos for c in o.bound_box]
dims = [max(p[k] for p in bb) - min(p[k] for p in bb) for k in range(3)]
print('DIMS cm (L x P x A)', [round(x * 100, 1) for x in dims])
os.makedirs(os.path.dirname(BASE + P['saida']), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=BASE + P['saida'], export_format='GLB', export_image_format='AUTO')

diag = os.path.dirname(BASE + P['saida']) + '/diag/'; os.makedirs(diag, exist_ok=True)
sc = bpy.context.scene; sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.color_type = 'TEXTURE'; sc.display.shading.light = 'STUDIO'
cz = (max(p.z for p in bb) + min(p.z for p in bb)) / 2; A = max(dims); alvo = mathutils.Vector((0, 0, cz))
sc.render.resolution_x = 700; sc.render.resolution_y = 700
cam = bpy.data.cameras.new('c'); cam.type = 'ORTHO'; cam.ortho_scale = A * 1.15
co = bpy.data.objects.new('cam', cam); sc.collection.objects.link(co); sc.camera = co
sc.world = bpy.data.worlds.new('w')
for nome, loc in {'1_frente': (0, -3 * A, 0), '4_tras': (0, 3 * A, 0)}.items():
    co.location = alvo + mathutils.Vector(loc); co.rotation_euler = (alvo - co.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = diag + f'{nome}.png'; bpy.ops.render.render(write_still=True)
cam.type = 'PERSP'; cam.lens = 45
co.location = alvo + mathutils.Vector((-1.1 * A, -2.2 * A, 0.7 * A)); co.rotation_euler = (alvo - co.location).to_track_quat('-Z', 'Y').to_euler()
sc.render.filepath = diag + '5_iso.png'; bpy.ops.render.render(write_still=True)
