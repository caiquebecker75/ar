# Etapa 4: monta o GLB de AR com a luz assada.
#   blender -b <saida>/prep.blend --python tools/bake/export.py   (lê <saida>/bake/*.jpg, grava <saida>/assado.glb)
# Cada atlas ganha um material só com a textura assada como EMISSÃO (base preta, sem reflexo):
# no celular aparece como no render, sem a luz do lugar mudar as cores. O acrílico (Material.009)
# continua translúcido. Só o UV de bake vai para o GLB.
import bpy, os, mathutils

PASTA = bpy.path.abspath("//")
sc = bpy.context.scene

# parte da textura assada entra como COR, não só como emissão: assim o ambiente do visualizador
# (AR ou 3D) devolve o reflexo que o bake difuso não guarda, e painel brilhante branco para de
# aparecer cinza. 0 = só emissão (comportamento antigo).
COR_AMBIENTE = float(os.environ.get("BAKE_COR_AMBIENTE", "0.45"))

def material_assado(nome, imagem, rugosidade=None):
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = (0, 0, 0, 1)
    p.inputs["Roughness"].default_value = 1.0
    p.inputs["Metallic"].default_value = 0.0
    p.inputs["Specular IOR Level"].default_value = 0.5   # reflexo normal: o ambiente real (AR) ou o HDR (3D) reflete
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = imagem
    uv = nt.nodes.new("ShaderNodeUVMap"); uv.uv_map = "bake"
    nt.links.new(uv.outputs["UV"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = 1.0 - COR_AMBIENTE
    if COR_AMBIENTE > 0:
        mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type = 'MULTIPLY'
        mix.inputs[0].default_value = 1.0
        mix.inputs[2].default_value = (COR_AMBIENTE, COR_AMBIENTE, COR_AMBIENTE, 1)
        nt.links.new(tex.outputs["Color"], mix.inputs[1])
        nt.links.new(mix.outputs["Color"], p.inputs["Base Color"])
    if rugosidade:
        rugosidade.colorspace_settings.name = 'Non-Color'
        tr = nt.nodes.new("ShaderNodeTexImage"); tr.image = rugosidade
        nt.links.new(uv.outputs["UV"], tr.inputs["Vector"])
        nt.links.new(tr.outputs["Color"], p.inputs["Roughness"])
    return m

acrilico = bpy.data.materials.new("ACRILICO")
acrilico.use_nodes = True
pa = next(n for n in acrilico.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
pa.inputs["Base Color"].default_value = (0.95, 0.96, 0.98, 1)
# acrílico leitoso (o do módulo Panasonic tem rugosidade 0,5): vidro liso deixava ver a peça de trás
# escura, e no render é o painel que clareia a cena
pa.inputs["Alpha"].default_value = 0.55
pa.inputs["Roughness"].default_value = 0.5
acrilico.surface_render_method = 'BLENDED'

def translucido(m):
    """Vidro e acrílico não têm cor difusa: no bake saem pretos. Reconhece pelo material original
    (transmissão ou alfa), além do nome antigo Material.009 do stand da NGV."""
    if not m: return False
    if m.name.startswith("Material.009"): return True
    if not m.use_nodes: return False
    # vidro puro (Glass/Refraction/Transparent BSDF) não tem cor difusa nenhuma
    if any(n.type in {'BSDF_GLASS','BSDF_REFRACTION','BSDF_TRANSPARENT'} for n in m.node_tree.nodes): return True
    for n in m.node_tree.nodes:
        if n.type != 'BSDF_PRINCIPLED': continue
        t = n.inputs.get("Transmission Weight")
        a = n.inputs.get("Alpha")
        if t is not None and not t.is_linked and t.default_value > 0.2: return True
        if a is not None and not a.is_linked and a.default_value < 0.9: return True
    return False

# grava a posição final de cada atlas na geometria antes de apagar os vazios-pais do GLB importado
# (em duas fases: um atlas pode ser pai de outro, e mexer no pai antes move o filho)
atlas = [x for x in sc.objects if x.type == 'MESH' and x.name.startswith("ATLAS_")]
finais = {o.name: o.matrix_world.copy() for o in atlas}
for o in atlas:
    o.parent = None
    o.data.transform(finais[o.name])
    o.matrix_world = mathutils.Matrix.Identity(4)

for o in list(sc.objects):
    if o.type != 'MESH' or not o.name.startswith("ATLAS_"):
        bpy.data.objects.remove(o)   # luzes, câmeras e o que sobrou
        continue
    caminho = os.path.join(PASTA, "bake", f"{o.name}.jpg")
    img = bpy.data.images.load(caminho)
    cr = os.path.join(PASTA, "bake", f"{o.name}_rug.png")
    assado = material_assado(f"BAKE_{o.name[6:]}", img, bpy.data.images.load(cr) if os.path.exists(cr) else None)
    for slot in o.material_slots:
        slot.material = acrilico if translucido(slot.material) else assado
    # só o UV de bake segue para o GLB
    me = o.data
    # cor de vértice herdada de modelos prontos (móveis): no USD vira primvars:Color e o motor da Apple
    # pinta a peça de branco por cima da textura assada
    for ca in list(me.color_attributes):
        me.color_attributes.remove(ca)
    for uv in [u for u in me.uv_layers if u.name != "bake"]:
        me.uv_layers.remove(uv)
    me.uv_layers["bake"].active = True
    me.uv_layers["bake"].active_render = True
    print("atlas", o.name, img.size[:], "slots", len(o.material_slots), flush=True)

import numpy as np, bmesh
from collections import defaultdict
# sobras escondidas debaixo do piso (no render o piso cobre; no AR o stand flutuaria): remove faces inteiras abaixo de -5 cm
for o in [x for x in sc.objects if x.type == 'MESH']:
    bm = bmesh.new(); bm.from_mesh(o.data); info = defaultdict(lambda: [0, 9e9, -9e9])
    apagar = [f for f in bm.faces if max(v.co.z for v in f.verts) < -0.05]
    for f in apagar:
        m = o.data.materials[f.material_index]; k = m.name if m else None
        i = info[k]; i[0] += 1; i[1] = min(i[1], min(v.co.z for v in f.verts)); i[2] = max(i[2], max(v.co.z for v in f.verts))
    for k, (n, a, b) in info.items(): print("ABAIXO DO PISO", o.name, k, "faces", n, "z", round(a, 2), "a", round(b, 2), flush=True)
    bmesh.ops.delete(bm, geom=apagar, context='FACES')
    bm.to_mesh(o.data); bm.free()
bpy.ops.export_scene.gltf(
    filepath=os.path.join(PASTA, "assado.glb"), export_format='GLB',
    export_apply=True, export_cameras=False, export_lights=False, export_yup=True,
    export_image_format='AUTO', export_materials='EXPORT')
print("EXPORT OK", os.path.getsize(os.path.join(PASTA, "assado.glb")) // 1048576, "MB", flush=True)
