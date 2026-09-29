# Levanta o pote em 3D girando a silhueta medida pelo rotulo.py e envolvendo a faixa de 360 graus.
#
#   CFG=potes.json PECA=creatina /Applications/Blender.app/Contents/MacOS/Blender -b -P tools/ftw/potes.py
#
# potes.json (caminhos relativos ao config; medidas em metros):
# { "creatina": { "perfil": "med/creatina.json", "tira": "tex/creatina.png",
#                 "diametro": 0.095, "saida": "build/creatina/raw.glb",
#                 "segmentos": 96, "topo": [242,242,240], "base": [236,236,234] } }
#
# O perfil vem em fracao do raio maximo, do topo para a base; a altura sai da razao medida.
# A emenda da textura fica em u=0, que o rotulo.py deixa no centro das costas.
import bpy, bmesh, os, json, math
import numpy as np

CFG = os.environ['CFG']
BASE = os.path.dirname(os.path.abspath(CFG)) + '/'
os.chdir(BASE)
PECA = os.environ['PECA']
P = json.load(open(CFG))[PECA]
MED = json.load(open(P['perfil']))
SEG = int(P.get('segmentos', 96))

bpy.ops.wm.read_factory_settings(use_empty=True)


def lin(c):   # 0-255 sRGB para linear
    return tuple(((x / 255) / 12.92) if x / 255 <= 0.04045 else (((x / 255) + 0.055) / 1.055) ** 2.4 for x in c)


perfil = np.array(MED['perfil'], float)          # raio relativo, topo -> base
razao = float(MED['razao_altura_diametro'])
raio = float(P['diametro']) / 2.0
altura = razao * float(P['diametro'])
n = len(perfil)

# ---------------------------------------------------------------- corpo girado
me = bpy.data.meshes.new(PECA)
bm = bmesh.new()
uv = bm.loops.layers.uv.new('UVMap')

anel = []
for i, r in enumerate(perfil):
    z = altura * (1.0 - i / (n - 1))             # perfil[0] e o topo
    rr = max(r * raio, 1e-5)
    anel.append([bm.verts.new((rr * math.cos(2 * math.pi * s / SEG),
                               rr * math.sin(2 * math.pi * s / SEG), z)) for s in range(SEG)])

for i in range(n - 1):
    for s in range(SEG):
        s2 = (s + 1) % SEG
        f = bm.faces.new((anel[i][s], anel[i][s2], anel[i + 1][s2], anel[i + 1][s]))
        f.material_index = 0
        # a frente do rotulo (u = 0.5) tem de olhar para -Y do Blender, que vira +Z do glTF
        us = [s / SEG - 0.25, (s + 1) / SEG - 0.25, (s + 1) / SEG - 0.25, s / SEG - 0.25]
        vs = [1 - i / (n - 1), 1 - i / (n - 1), 1 - (i + 1) / (n - 1), 1 - (i + 1) / (n - 1)]
        for lo, u, v in zip(f.loops, us, vs):
            lo[uv].uv = (u, v)

# tampas: disco no centro de cada extremidade, material proprio (plastico)
for anel_i, z, idx in ((anel[0], altura, 1), (anel[-1], 0.0, 2)):
    c = bm.verts.new((0, 0, z))
    for s in range(SEG):
        s2 = (s + 1) % SEG
        tri = (c, anel_i[s2], anel_i[s]) if idx == 1 else (c, anel_i[s], anel_i[s2])
        f = bm.faces.new(tri)
        f.material_index = idx
        for lo in f.loops:
            lo[uv].uv = (0.5, 1.0 if idx == 1 else 0.0)

bm.normal_update()
bm.to_mesh(me)
bm.free()
ob = bpy.data.objects.new(PECA, me)
bpy.context.scene.collection.objects.link(ob)

# ---------------------------------------------------------------- materiais
def material(nome, cor=None, img=None, rug=0.42, cor_linear=None):
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = rug
    bsdf.inputs['Metallic'].default_value = 0.0
    if img:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = bpy.data.images.load(os.path.abspath(img))
        tex.image.colorspace_settings.name = 'sRGB'
        tex.interpolation = 'Cubic'
        nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
        m.diffuse_color = (0.8, 0.1, 0.1, 1)
    else:
        c = cor_linear if cor_linear is not None else lin(cor)
        bsdf.inputs['Base Color'].default_value = (*c, 1)
        m.diffuse_color = (*c, 1)
    return m

def cor_da_borda(caminho, topo=True, faixa=0.03):
    """Cor media da primeira ou da ultima faixa do rotulo, para o disco da ponta
    nao aparecer como um adesivo cinza no alto do pote."""
    im = bpy.data.images.load(os.path.abspath(caminho))
    w, h = im.size
    px = np.asarray(im.pixels[:], dtype=np.float32).reshape(h, w, im.channels)
    n = max(1, int(h * faixa))
    banda = px[-n:] if topo else px[:n]          # bpy guarda a imagem de baixo para cima
    c = banda[..., :3].reshape(-1, 3).mean(0)    # ja esta em linear
    bpy.data.images.remove(im)
    return tuple(float(v) for v in c)

ob.data.materials.append(material('rotulo', img=P['tira'], rug=P.get('rugosidade', 0.56)))
ob.data.materials.append(material('tampa', cor_linear=P.get('topo') or cor_da_borda(P['tira'], True), rug=0.5))
ob.data.materials.append(material('fundo', cor_linear=P.get('base') or cor_da_borda(P['tira'], False), rug=0.55))

# suaviza o ombro, mantendo as bordas das tampas vivas
for p in ob.data.polygons:
    p.use_smooth = True
ob.data.shade_smooth()
if hasattr(ob.data, 'use_auto_smooth'):
    ob.data.use_auto_smooth = True
    ob.data.auto_smooth_angle = math.radians(50)

saida = P['saida']
os.makedirs(os.path.dirname(saida), exist_ok=True)
bpy.ops.object.select_all(action='DESELECT')
ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.export_scene.gltf(filepath=saida, export_format='GLB', use_selection=True,
                          export_apply=True, export_yup=True)
print('OK %s  %.1f x %.1f cm  %d faces' % (PECA, P['diametro'] * 100, altura * 100, len(ob.data.polygons)))
