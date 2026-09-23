# Etapa 0: prepara a cena de um .blend de cliente para o bake de luz.
#   blender -b ARQUIVO.blend --python tools/bake/cena.py -- --saida=CENA.blend [--hdr=MUNDO.hdr]
#       [--excluir=Cenario,Materiais] [--so=Modulo Único,Acessorios]
#
# O que ela resolve, que já custou caro em projeto de cliente:
#   · coleção excluída do view layer volta (senão nada pode ser selecionado) mas o que ela contém
#     só entra se for pedido: amostra de material e cenário atrás do produto estragam a luz;
#   · filho de vazio de instância sai longe no glTF: solta mantendo a posição;
#   · instância de coleção vira malha real pelo depsgraph (duplicates_make_real falha em arquivo linkado);
#   · cortador de boolean escondido no render é mantido até aplicar os modificadores, e só então sai;
#   · normal virada para dentro assa preta: recalcula para fora;
#   · asset com visibilidade de raio desligada faz o bake sair preto sem erro: religa tudo;
#   · material preso ao OBJETO vai para a MALHA (o glTF e o bake leem o da malha);
#   · grava o HDR do mundo em arquivo, para o prep.py usar a mesma luz da cena.
import bpy, bmesh, sys, os
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = lambda k, d=None: next((a.split("=", 1)[1] for a in args if a.startswith(f"--{k}=")), d)
SAIDA = opt("saida", "cena.blend")
HDR = opt("hdr")
EXCLUIR = {x.strip() for x in (opt("excluir") or "").split(",") if x.strip()}
SO = {x.strip() for x in (opt("so") or "").split(",") if x.strip()}
sc = bpy.context.scene

# ---------- o que fica
guardar = set()
if SO:
    for nome in SO:
        c = bpy.data.collections.get(nome)
        if c:
            for o in c.all_objects: guardar.add(o.name)
else:
    guardar = {o.name for o in bpy.data.objects if o.type in {'MESH', 'EMPTY'}}
for nome in EXCLUIR:
    c = bpy.data.collections.get(nome)
    if c:
        for o in c.all_objects: guardar.discard(o.name)
escondidos = {o.name for o in bpy.data.objects if o.hide_render}
guardar -= escondidos

# cortadores de boolean voltam (saem depois que os modificadores forem aplicados)
cortadores = set()
for nome in list(guardar):
    o = bpy.data.objects.get(nome)
    if not o: continue
    for m in o.modifiers:
        if m.type == 'BOOLEAN' and m.object:
            cortadores.add(m.object.name); guardar.add(m.object.name)
print("objetos mantidos:", len(guardar), "| cortadores:", sorted(cortadores), flush=True)

def religa(lc):
    lc.exclude = False; lc.hide_viewport = False
    for f in lc.children: religa(f)
religa(bpy.context.view_layer.layer_collection)

# ---------- HDR do mundo (a mesma luz do render do cliente)
if HDR and sc.world and sc.world.use_nodes:
    img = next((n.image for n in sc.world.node_tree.nodes if n.type == 'TEX_ENVIRONMENT' and n.image), None)
    if img:
        try:
            img.filepath_raw = os.path.abspath(HDR); img.file_format = 'HDR'; img.save()
            print("HDR do mundo gravado em", HDR, flush=True)
        except Exception as e: print("não deu para gravar o HDR:", e, flush=True)
    else:
        print("mundo sem imagem de ambiente (cor lisa)", flush=True)

# ---------- instância de coleção vira malha real
dg = bpy.context.evaluated_depsgraph_get()
novos = []
for inst in dg.object_instances:
    if not inst.is_instance: continue
    pai = inst.parent
    if not pai or pai.name not in guardar: continue
    ob = inst.object
    if ob.type != 'MESH': continue
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    if not len(me.polygons): bpy.data.meshes.remove(me); continue
    novo = bpy.data.objects.new(f"{pai.name}__{ob.name}", me)
    novo.matrix_world = inst.matrix_world.copy()
    sc.collection.objects.link(novo); novos.append(novo.name)
if novos: print("peças reais criadas das instâncias:", len(novos), flush=True)
guardar |= set(novos)

for o in list(bpy.data.objects):
    if o.type == 'LIGHT': continue
    if o.name not in guardar: bpy.data.objects.remove(o, do_unlink=True)

vis = set(bpy.context.view_layer.objects)
for o in sc.objects:
    if o in vis: o.hide_set(False)
    o.hide_viewport = False; o.hide_select = False; o.hide_render = False

# filho de vazio de instância: soltar mantendo a posição
for o in list(sc.objects):
    if o.parent and o.parent.type == 'EMPTY' and o.parent.instance_collection:
        m = o.matrix_world.copy(); o.parent = None; o.matrix_world = m

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.make_local(type='ALL')
bpy.ops.object.make_single_user(object=True, obdata=True, material=False, animation=False)

for o in sc.objects:
    if o.type != 'MESH': continue
    for s in o.material_slots:
        if s.link == 'OBJECT': m = s.material; s.link = 'DATA'; s.material = m
    for campo in ("visible_camera", "visible_diffuse", "visible_glossy", "visible_transmission",
                  "visible_volume_scatter", "visible_shadow"):
        setattr(o, campo, True)
    o.is_holdout = False

# modificadores aplicados (solidify, bevel, boolean, geometry nodes) e cortadores fora
dg = bpy.context.evaluated_depsgraph_get()
for o in [x for x in sc.objects if x.type == 'MESH' and x.name not in cortadores]:
    me = bpy.data.meshes.new_from_object(o.evaluated_get(dg))
    velha = o.data; o.modifiers.clear(); o.data = me
    if velha.users == 0: bpy.data.meshes.remove(velha)
for nome in cortadores:
    o = bpy.data.objects.get(nome)
    if o: bpy.data.objects.remove(o, do_unlink=True)

viradas = 0
for o in [x for x in sc.objects if x.type == 'MESH']:
    bm = bmesh.new(); bm.from_mesh(o.data)
    antes = [f.normal.copy() for f in bm.faces]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    viradas += sum(1 for f, n in zip(bm.faces, antes) if f.normal.dot(n) < 0)
    bm.to_mesh(o.data); bm.free()
if viradas: print("faces com normal recalculada:", viradas, flush=True)

for i, l in enumerate([x for x in sc.objects if x.type == 'LIGHT'], 1): l.name = f"Area{i}"
for o in list(sc.objects):
    if o.type not in {'MESH', 'LIGHT'}: bpy.data.objects.remove(o, do_unlink=True)

mn = Vector((9e9,) * 3); mx = Vector((-9e9,) * 3); faces = 0
for o in sc.objects:
    if o.type != 'MESH': continue
    faces += len(o.data.polygons)
    for v in o.bound_box:
        w = o.matrix_world @ Vector(v); mn = Vector(map(min, mn, w)); mx = Vector(map(max, mx, w))
d = (mx - mn) * 100
print(f"malhas: {len([o for o in sc.objects if o.type=='MESH'])} | faces: {faces} | cena: {d.x:.0f} x {d.y:.0f} x {d.z:.0f} cm", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(SAIDA))
print("CENA OK", SAIDA, flush=True)
