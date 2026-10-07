# Etapa 1 (a partir do .blend do projeto, o jeito mais fiel): usa a cena como está (luzes, ambiente, materiais,
# modificadores, instâncias), converte tudo que aparece no render em malha, solda/reduz, agrupa em atlas e
# cria o UV "bake". Salva <saida>/prep.blend.
#   blender -b PROJETO.blend --python tools/bake/prep_blend.py -- --saida=PASTA [--hdr=ARQ.hdr] [--escala-alvo=1]
#       [--excluir-colecoes=Escala humana,References] [--densidade-arte=15000] [--atlas-m2=25,14,2.5]
# --hdr: substitui um HDR de ambiente que não abriu (ex.: caminho D:\ de outra máquina).
# --excluir-objetos=REGEX: peças que ficam fora pelo nome (do objeto ou de quem instancia), ex.: conteúdo
#   guardado dentro de gabinete que o render não mostra mas que, sem a porta certinha, aparece no AR.
# --excluir-colecoes: coleções que ficam fora (ex.: boneco de escala que o render esconde pela coleção).
# --colapso-densidade=N: colapso só em peça acima de N triângulos/m² (planta, ferramenta, banqueta). Painel e
#   móvel ficam só com a dissolução planar: o colapso por proporção fecha recorte de peça com espessura (o
#   furo da cartela no mostruário virou parede). A redução final fica com o compacta-glb (erro limitado).
# --densidade-arte: peça com textura só fica protegida do colapso abaixo desta densidade (triângulos/m²).
#   Arte impressa é plana e leve; planta, grama e objeto comprado (ferramenta, banqueta) passam de 15 mil/m².
# --atlas-m2: área por atlas grande, médio e pequeno (ambiente grande: aumentar, senão vira dezenas de 4096).
# --recorte=REGEX: materiais de folha/grama com recorte por transparência (nome casa com a expressão).
#   As faces deles vão para atlas próprios ("folha", marcados com recorte=1): o bake.py assa também o alfa
#   e o export.py grava a textura com transparência (alphaMode MASK). Sem isso a folha vira retângulo leitoso.
#   [--atlas-folha-m2=20] [--folha-tri-por-parte=4] [--folha-tri-m2=3000] [--folha-max=50000]
#   Folhagem densa (milhares de folhas soltas) não aguenta o colapso comum: cada folha vira 1 triângulo.
#   Aqui cada folha fica com ~4 triângulos (o formato vem do alfa assado) e, se passar do limite por área,
#   parte das folhas sai por sorteio fixo (raleio uniforme).
import bpy, bmesh, math, mathutils, time, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import coords_originais
T0=time.time()
def log(*a): print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)
_args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
_opt = lambda k, d=None: next((a.split("=", 1)[1] for a in _args if a.startswith(f"--{k}=")), d)
SAIDA = os.path.abspath(_opt("saida", "."))
HDR = _opt("hdr")
ESCALA = float(_opt("escala-alvo", 1))   # multiplica os limites de triângulos por malha
EXCLUIR = {x.strip() for x in (_opt("excluir-colecoes") or "").split(",") if x.strip()}
DENS_ARTE = float(_opt("densidade-arte", 0)) or None
COLAPSO_DENS = float(_opt("colapso-densidade", 0)) or None
REFAZER_UV = float(_opt("refazer-uv-abaixo", 0.35))
# --pack-forma=CONCAVE: empacota pelo formato exato. Fita de LED de 11 m vira ilha em laço e, por caixa (AABB),
# o retângulo do laço come o atlas inteiro (mostruário do stand Alltak ficou minúsculo e escuro)
PACK_FORMA = _opt("pack-forma", "AABB")
import re as _re
EXCLUIR_OBJ = _re.compile(_opt("excluir-objetos")) if _opt("excluir-objetos") else None
ATLAS_M2 = [float(x) for x in _opt("atlas-m2", "25,14,2.5").split(",")]
import re
RECORTE = re.compile(_opt("recorte")) if _opt("recorte") else None
ATLAS_FOLHA_M2 = float(_opt("atlas-folha-m2", 20))
FOLHA_TPP = float(_opt("folha-tri-por-parte", 4))
FOLHA_M2 = float(_opt("folha-tri-m2", 3000))
FOLHA_MAX = float(_opt("folha-max", 50000))
sc = bpy.context.scene
fora = set()
for nome in EXCLUIR:
    c = bpy.data.collections.get(nome)
    if c: fora |= {o.name for o in c.all_objects}
    else: log("coleção não encontrada:", nome)

# ---------- ambiente: troca HDR que não abriu ----------
if HDR and sc.world and sc.world.use_nodes:
    for n in sc.world.node_tree.nodes:
        if n.type == 'TEX_ENVIRONMENT' and (not n.image or n.image.size[0] == 0):
            n.image = bpy.data.images.load(HDR, check_existing=True)
            log("HDR trocado:", HDR, tuple(n.image.size))

# ---------- tudo que aparece no render vira malha real (modificadores e instâncias aplicados) ----------
# A cena é avaliada como no RENDER (não como na viewport): um motor de render "falso" recebe o depsgraph de
# render do Blender. Assim vale tudo que o Cycles respeita: esconder no render dentro de arquivo linkado,
# modificador só de render (boolean de porta e gaveta), nível de subdivisão de render etc.
# --depsgraph=viewport volta ao comportamento antigo.
col = bpy.data.collections.new("AR_MALHAS"); sc.collection.children.link(col)
novos = 0
uvs_normalizados = 0
_capturas = []
_duplicadas = [0]
def _capturar(dg):
    vistos = set()
    for inst in dg.object_instances:
        ob = inst.object
        if ob.type not in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}: continue
        # a mesma peça duas vezes no mesmo lugar (coleção instanciada que puxa a peça por dois caminhos):
        # no render não aparece, mas em malha as duas superfícies coincidentes se sombreiam (pontas escuras na
        # testeira) e no AR dariam z-fighting com texturas assadas diferentes
        chave = (ob.original.name, ob.original.library and ob.original.library.filepath,
                 tuple(round(x, 4) for linha in inst.matrix_world for x in linha))
        if chave in vistos:
            _duplicadas[0] += 1; continue
        vistos.add(chave)
        try:
            # preserve_all_data_layers=False: com True o Blender REAVALIA os modificadores numa cópia e o boolean
            # falha (recorte da cartela vira parede), o array de nós sai em outro lugar e o UV muda
            me = bpy.data.meshes.new_from_object(ob, preserve_all_data_layers=False, depsgraph=dg)
        except RuntimeError:
            continue
        if not me.polygons: bpy.data.meshes.remove(me); continue
        _capturas.append((ob.original, inst.is_instance, inst.parent.original if inst.is_instance and inst.parent else None,
                          inst.matrix_world.copy(), me))
if _opt("depsgraph", "render") == "render":
    class _Captura(bpy.types.RenderEngine):
        bl_idname = "AR_CAPTURA"; bl_label = "captura AR"
        def render(self, depsgraph):
            _capturar(depsgraph)
            r = self.begin_result(0, 0, 4, 4); self.end_result(r)
    bpy.utils.register_class(_Captura)
    _motor, _rx, _ry, _rp = sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage
    sc.render.engine = "AR_CAPTURA"; sc.render.resolution_x = sc.render.resolution_y = 4; sc.render.resolution_percentage = 100
    bpy.ops.render.render()
    sc.render.engine, sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = _motor, _rx, _ry, _rp
    log("cena avaliada como no render:", len(_capturas), "peças | duplicadas descartadas:", _duplicadas[0])
else:
    _capturar(bpy.context.evaluated_depsgraph_get())

_viewport = _opt("depsgraph", "render") != "render"
for orig, _is_inst, _pai, _mw, me in _capturas:
    # só no modo viewport: o depsgraph de render já vem filtrado (e o "olho" da viewport não vale no render)
    if _viewport and ((not _is_inst and (orig.hide_render or not orig.visible_get())) or (_is_inst and orig.hide_render)):
        bpy.data.meshes.remove(me); continue
    if EXCLUIR_OBJ and (EXCLUIR_OBJ.search(orig.name) or (_pai is not None and EXCLUIR_OBJ.search(_pai.name))):
        bpy.data.meshes.remove(me); continue
    if orig.name in fora or (_pai is not None and _pai.name in fora):
        bpy.data.meshes.remove(me); continue
    o = bpy.data.objects.new(orig.name, me)
    o.matrix_world = _mw
    col.objects.link(o); novos += 1
    # invisível para a câmera (rebatedor, bloqueio de luz): fica na cena para o bake, fora dos atlas e do AR
    if not orig.visible_camera or orig.is_holdout:
        for campo in ("visible_camera","visible_diffuse","visible_glossy","visible_transmission","visible_volume_scatter","visible_shadow"):
            setattr(o, campo, getattr(orig, campo))
        o["so_luz"] = 1
    uvs_normalizados += coords_originais.normalizar_uv(o)
    # coordenada Object/Generated e Random Per Island do objeto original viram atributo (o atlas junta tudo)
    coords_originais.gravar(o, orig.data)
# apaga o resto (menos luzes)
for o in list(sc.objects):
    if o.type == 'LIGHT' or o.name in col.objects: continue
    bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections):
    if c != col and c.users == 0: bpy.data.collections.remove(c)
log("malhas do render:", novos, "| luzes:", sum(1 for o in sc.objects if o.type == 'LIGHT'))
log("nós de coordenada trocados por atributo:", coords_originais.trocar_nos(), "| UV renomeado para UVMap:", uvs_normalizados,
    "| só luz (invisível p/ câmera):", sum(1 for o in col.objects if o.get("so_luz")))

# ---------- render ----------
sc.render.engine='CYCLES'
prefs=bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type='METAL'; prefs.get_devices()
for d in prefs.devices: d.use=True
sc.cycles.device='GPU'
sc.tool_settings.use_uv_select_sync = True   # pack_islands só mexe no que está selecionado no UV
log("cor:", sc.view_settings.view_transform, sc.view_settings.look, "exposição", sc.view_settings.exposure)

REPETE = ('carpet','leather','fabric','wood','metal','powder','steel','plastic','tv_','office','gwc','rough','normal','smudge','tech_','bump','disp','gloss','ambientocclusion','couro','pine','oak','82.jpg')
def tem_arte(o):
    """Material com imagem que não é textura repetida (arte única: placa, painel, KV, logo)."""
    for m in o.data.materials:
        if not m or not m.use_nodes: continue
        for n in m.node_tree.nodes:
            if n.type == 'TEX_IMAGE' and n.image and not any(k in n.image.name.lower() for k in REPETE):
                return True
    return False

# ---------- malhas: dados únicos, sem modificadores, redução ----------
meshes=[o for o in sc.objects if o.type=='MESH' and not o.get("so_luz")]
for o in meshes:
    if o.data.users>1: o.data=o.data.copy()

# ---------- folhas com recorte: faces separadas em objeto próprio ----------
eh_recorte = lambda m: bool(RECORTE and m and RECORTE.search(m.name))
if RECORTE:
    for m in bpy.data.materials:
        if eh_recorte(m): m["recorte"] = 1
    log("materiais de recorte:", sorted(m.name for m in bpy.data.materials if m.get("recorte")))
    separados = 0
    for o in list(meshes):
        mats = list(o.data.materials)
        rec = {i for i, m in enumerate(mats) if eh_recorte(m)}
        if not rec: continue
        if all(p.material_index in rec for p in o.data.polygons):
            o["recorte"] = 1; continue
        if not any(p.material_index in rec for p in o.data.polygons): continue
        f = o.copy(); f.data = o.data.copy(); f.name = o.name + "__folha"; col.objects.link(f); f["recorte"] = 1
        for alvo_o, apagar in ((o, lambda p: p.material_index in rec), (f, lambda p: p.material_index not in rec)):
            bm = bmesh.new(); bm.from_mesh(alvo_o.data)
            bm.faces.ensure_lookup_table()
            fs = [bm.faces[p.index] for p in alvo_o.data.polygons if apagar(p)]
            bmesh.ops.delete(bm, geom=fs, context='FACES'); bm.to_mesh(alvo_o.data); bm.free()
        meshes.append(f); separados += 1
    log("objetos com folha separada:", separados, "| objetos de recorte:", sum(1 for o in meshes if o.get("recorte")))
dg=bpy.context.evaluated_depsgraph_get()
antes=depois=0
soldados=0
for o in meshes:
    # o GLB chega com vértices separados em toda quina/costura: solda (UV fica por canto de face, não muda)
    bm=bmesh.new(); bm.from_mesh(o.data); n0=len(bm.verts)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.0001); soldados+=n0-len(bm.verts)
    bm.to_mesh(o.data); bm.free()
    tri=sum(len(p.vertices)-2 for p in o.data.polygons); antes+=tri
    maior=max(o.dimensions) if max(o.dimensions)>0 else 0
    _M=o.matrix_world; _a=0.0
    for _p in o.data.polygons: _a+=_p.area
    _a*=abs(_M.to_scale()[0]*_M.to_scale()[1])   # aproximação da área real
    alvo = int(min(40000, max(600, _a*6000)) * ESCALA)
    if o.get("recorte"):
        import random
        bm=bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table()
        visto=set(); partes=[]
        for f in bm.faces:
            if f.index in visto: continue
            pilha=[f]; visto.add(f.index); fs=[]
            while pilha:
                g=pilha.pop(); fs.append(g)
                for e in g.edges:
                    for h in e.link_faces:
                        if h.index not in visto: visto.add(h.index); pilha.append(h)
            partes.append(fs)
        teto = min(FOLHA_MAX, max(600, _a*FOLHA_M2)) * ESCALA
        cabe = int(teto / FOLHA_TPP)
        if len(partes) > cabe:
            rnd = random.Random(7); sai = rnd.sample(range(len(partes)), len(partes) - cabe)
            bmesh.ops.delete(bm, geom=[g for i in sai for g in partes[i]], context='FACES')
            log(f"  raleio {o.name}: {len(partes)} -> {cabe} folhas")
        bm.to_mesh(o.data); bm.free()
        # meta: ~4 triângulos por folha, mas nunca abaixo do limite por área (fronde de palmeira é UMA parte
        # com dezenas de folíolos: com 4 triângulos ela some)
        alvo = int(max(min(len(partes), cabe) * FOLHA_TPP, teto))
        tri = sum(len(p.vertices)-2 for p in o.data.polygons)
    def aplicar(mod):
        dg=bpy.context.evaluated_depsgraph_get()
        # preserve_all_data_layers=True: sem isso o Blender só interpola o UV ativo e as faces novas da dissolução
        # ficam com os outros UVs zerados (madeira do mostruário saiu preta). Aqui é seguro: malha simples + decimate
        novo=bpy.data.meshes.new_from_object(o.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
        velho=o.data; o.modifiers.clear(); o.data=novo; bpy.data.meshes.remove(velho)
    # com --colapso-densidade, peça leve (painel, móvel) não passa por redução nenhuma aqui: a dissolução planar
    # junta faces de superfície curva subdividida (cada vizinha difere < 4°) em polígonos enormes e não planos,
    # que dobram ao triangular (madeira do mostruário e do balcão saiu preta e quadriculada)
    if COLAPSO_DENS is not None and not o.get("recorte") and tri / max(_a, 1e-6) < COLAPSO_DENS:
        alvo = tri
    if tri>alvo:
        # 1) junta faces planas sem atravessar corte de UV/material (artes continuam no lugar, sem picotar a malha)
        m=o.modifiers.new("planar",'DECIMATE'); m.decimate_type='DISSOLVE'; m.angle_limit=math.radians(4)
        m.delimit={'MATERIAL','UV'}; aplicar(m)
        tri2=sum(len(p.vertices)-2 for p in o.data.polygons)
        # 2) se ainda passa do limite, colapso. Nunca em peça com arte impressa (placa, KV, logo, backlight):
        #    o colapso junta vértices e embaralha o UV da arte (logo picotado em triângulos)
        protegido = not o.get("recorte") and tem_arte(o) and (DENS_ARTE is None or tri2 / max(_a, 1e-6) < DENS_ARTE)
        denso = COLAPSO_DENS is None or o.get("recorte") or tri2 / max(_a, 1e-6) >= COLAPSO_DENS
        if tri2>alvo and not protegido and denso:
            m=o.modifiers.new("reduz",'DECIMATE'); m.ratio=max(alvo/tri2, 0.003); m.use_collapse_triangulate=True
            if not o.get("recorte"):
                # o colapso fecha furo (recorte de boolean onde encaixa a cartela) e engole contorno de material:
                # vértices de borda e de divisa de material ficam "caros" de colapsar (peso 0 no grupo invertido)
                bm=bmesh.new(); bm.from_mesh(o.data)
                borda={v.index for e in bm.edges for v in e.verts
                       if len(e.link_faces)!=2 or e.link_faces[0].material_index!=e.link_faces[1].material_index}
                nv=len(bm.verts); bm.free()
                # só em peça "fechada" (painel, móvel): em folhagem opaca e cartela solta quase tudo é borda,
                # e protegê-la impediria qualquer redução
                if borda and len(borda) < 0.25*nv:
                    vg=o.vertex_groups.new(name="ar_borda"); vg.add(list(borda), 1.0, 'REPLACE')
                    m.vertex_group="ar_borda"; m.invert_vertex_group=True; m.vertex_group_factor=100
            aplicar(m)
    depois+=sum(len(p.vertices)-2 for p in o.data.polygons)
log("triangulos", antes, "->", depois, "| vertices soldados", soldados)

# ---------- geometria em coordenadas do mundo (atlas com transformação identidade) ----------
# O atlas herda a transformação da primeira peça do grupo. Se ela é espelhada (escala negativa), as outras
# entram com a normal virada para dentro: no render não aparece (o Cycles desenha o verso), mas o bake de luz
# usa o lado da normal e a peça sai PRETA (mostruário do stand Alltak). Aplica a matriz em cada malha antes.
espelhadas = 0
for o in meshes:
    M = o.matrix_world.copy()
    o.data.transform(M)
    if M.determinant() < 0:
        o.data.flip_normals(); espelhadas += 1
    o.matrix_world = mathutils.Matrix.Identity(4)
log("transformação aplicada nas malhas | espelhadas (normal corrigida):", espelhadas)

# ---------- grupos de atlas por tamanho e área ----------
def area(o):
    M=o.matrix_world; s=0
    for p in o.data.polygons:
        v=[M@o.data.vertices[i].co for i in p.vertices]
        for k in range(1,len(v)-1): s+=((v[k]-v[0]).cross(v[k+1]-v[0])).length/2
    return s
meshes=[o for o in meshes if len(o.data.polygons)]
info=[(area(o), max(o.dimensions), o) for o in meshes if not o.get("recorte")]
folhas=[(area(o), max(o.dimensions), o) for o in meshes if o.get("recorte")]
def bins(itens, alvo):
    n=max(1, math.ceil(sum(a for a,_,_ in itens)/alvo)); caixas=[[0,[]] for _ in range(n)]
    for a,_,o in sorted(itens, key=lambda x:-x[0]):
        c=min(caixas, key=lambda c:c[0]); c[0]+=a; c[1].append(o)
    return caixas
grupos={}
for nome, filtro, alvo, px in [("grande", lambda d: d>=1.5, ATLAS_M2[0], 4096), ("medio", lambda d: 0.25<=d<1.5, ATLAS_M2[1], 4096), ("pequeno", lambda d: d<0.25, ATLAS_M2[2], 2048)]:
    for i,(a,objs) in enumerate(bins([x for x in info if filtro(x[1])], alvo)):
        grupos[f"{nome}{i+1}"]=(objs, px, a)
if folhas:
    for i,(a,objs) in enumerate(bins(folhas, ATLAS_FOLHA_M2)):
        grupos[f"folha{i+1}"]=(objs, 4096, a)
for g,(objs,px,a) in grupos.items(): log(f"atlas {g}: {len(objs)} objetos, {a:.1f} m2, {px}px")


def consertar_agulhas(o):
    """Ilhas pequenas com UV degenerado (agulha): refaz por projeção no plano da própria ilha, na escala mediana."""
    import numpy as np
    me=o.data; bm=bmesh.new(); bm.from_mesh(me); uvl=bm.loops.layers.uv["bake"]; visto=set(); ilhas=[]
    def uvarea(f):
        q=[l[uvl].uv for l in f.loops]; return sum(abs((q[k]-q[0]).cross(q[k+1]-q[0]))/2 for k in range(1,len(q)-1))
    for f in bm.faces:
        if f.index in visto: continue
        pilha=[f]; visto.add(f.index); faces=[]
        while pilha:
            g=pilha.pop(); faces.append(g)
            for l in g.loops:
                for el in l.edge.link_loops:
                    h=el.face
                    if h.index in visto: continue
                    a1,a2=l[uvl].uv,l.link_loop_next[uvl].uv; b1,b2=el[uvl].uv,el.link_loop_next[uvl].uv
                    if ((a1-b2).length<1e-7 and (a2-b1).length<1e-7) or ((a1-b1).length<1e-7 and (a2-b2).length<1e-7):
                        visto.add(h.index); pilha.append(h)
        ilhas.append(faces)
    razoes=[]; dados=[]
    for faces in ilhas:
        a3=sum(g.calc_area() for g in faces); au=sum(uvarea(g) for g in faces)
        uv=np.array([[l[uvl].uv.x,l[uvl].uv.y] for g in faces for l in g.loops]); caixa=float(np.prod(np.ptp(uv,0)))
        dados.append((faces,a3,au,caixa))
        if a3>1e-9 and au>1e-12: razoes.append(au/a3)
    med=float(np.median(razoes)) if razoes else 1.0
    k=math.sqrt(med); consertadas=0
    for faces,a3,au,caixa in dados:
        if len(faces)>8 or a3<1e-9: continue
        if au>1e-12 and caixa/au<30 and 0.2<(au/a3)/med<5: continue
        n=mathutils.Vector((0,0,0))
        for g in faces: n+=g.normal*g.calc_area()
        if n.length<1e-9: continue
        n.normalize(); t=n.orthogonal().normalized(); b=n.cross(t)
        for g in faces:
            for l in g.loops: l[uvl].uv=(l.vert.co.dot(t)*k, l.vert.co.dot(b)*k)
        consertadas+=1
    bm.to_mesh(me); bm.free()
    return consertadas

# ---------- UV de bake: junta cada grupo e projeta ----------
falhas=[]
bpy.ops.object.select_all(action='DESELECT')
for g,(objs,px,a) in grupos.items():
    for o in objs:
        uv=o.data.uv_layers
        if not uv: uv.new(name="UVMap")    # mantém todos os UVs: materiais usam UVMap.001 etc.
        uv.new(name="bake")
    ctx={"active_object":objs[0],"selected_editable_objects":objs,"selected_objects":objs}
    with bpy.context.temp_override(**ctx): bpy.ops.object.join()
    o=objs[0]; o.name=f"ATLAS_{g}"; o.data.name=o.name
    # peça sem material (no Cycles aparece cinza claro): slot vazio faz o bake do atlas inteiro sair preto
    for sl in o.material_slots:
        if sl.material is None:
            pm=bpy.data.materials.get("PADRAO_SEM_MATERIAL") or bpy.data.materials.new("PADRAO_SEM_MATERIAL")
            pm.use_nodes=True; sl.material=pm
    # UV que os materiais usam no render (normalizar_uv deixou "UVMap" em todas as peças)
    (o.data.uv_layers.get("UVMap") or o.data.uv_layers[0]).active_render=True
    o.data.uv_layers.active=o.data.uv_layers["bake"]
    bpy.context.view_layer.objects.active=o; o.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    # faces grandes/côncavas da dissolução planar quebram a área de UV: triangula antes
    bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
    bpy.ops.uv.smart_project(angle_limit=math.radians(89), island_margin=0.0, area_weight=0.0, correct_aspect=False, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    ag=consertar_agulhas(o)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=1.5/px, shape_method=PACK_FORMA)
    bpy.ops.object.mode_set(mode='OBJECT'); o.select_set(False)
    log("  ilhas-agulha refeitas:", ag)
    o["atlas_px"]=px
    if g.startswith("folha"): o["recorte"]=1
    import numpy as np
    def cobertura():
        uvb=o.data.uv_layers["bake"].data; c=0
        for p in o.data.polygons:
            pts=[uvb[i].uv for i in p.loop_indices]
            for k in range(1,len(pts)-1): c+=abs((pts[k]-pts[0]).cross(pts[k+1]-pts[0]))/2
        return c
    cob=cobertura()
    if cob>1.0:
        # ilhas sobrepostas (faces mínimas com escala de UV desproporcional): normaliza a escala e reempacota
        bpy.context.view_layer.objects.active=o; o.select_set(True)
        o.data.uv_layers.active=o.data.uv_layers["bake"]
        bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.reveal(); bpy.ops.mesh.select_all(action='SELECT')
        bpy.ops.uv.average_islands_scale()
        bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=1.5/px, shape_method=PACK_FORMA)
        bpy.ops.object.mode_set(mode='OBJECT')
        o.select_set(False)
        antes_cob=cob; cob=cobertura(); log(f"  UV sobreposto: cobertura {antes_cob*100:.0f}% -> {cob*100:.0f}%")
    # --refazer-uv-abaixo: só refaz o UV por costuras se o Smart UV ficou abaixo disto (padrão 0,35, do stand
    # da NGV). Em ambiente com muita peça curva e fina o recorte em grade de 25 cm picota tudo em centenas de
    # ilhas e o bake sai manchado (mostruário do stand Alltak): ali 0,15 deixa o Smart UV como está.
    if cob<REFAZER_UV:
        # anéis/faixas longas: corta costuras nas quinas e numa grade (1,5 m; se não bastar, 0,5 e 0,25 m) e desdobra
        antes_cob=cob
        for CEL in (1.5, 0.5, 0.25):
            bpy.ops.object.mode_set(mode='EDIT')
            bm=bmesh.from_edit_mesh(o.data); M=o.matrix_world
            cel=lambda f: tuple(int(math.floor(c/CEL)) for c in (M@f.calc_center_median()))
            for e in bm.edges:
                if e.is_boundary or not e.is_manifold: e.seam=True; continue
                f0,f1=e.link_faces[0],e.link_faces[1]
                e.seam = e.calc_face_angle(0) > math.radians(60) or cel(f0) != cel(f1)
            bmesh.update_edit_mesh(o.data)
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.unwrap(method='CONFORMAL', fill_holes=False, correct_aspect=False, margin=0.0)
            bpy.ops.uv.average_islands_scale()
            bpy.ops.object.mode_set(mode='OBJECT'); consertar_agulhas(o)
            bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=1.5/px, shape_method=PACK_FORMA)
            bpy.ops.object.mode_set(mode='OBJECT')
            cob=cobertura()
            log(f"  refeito com costuras a cada {CEL} m: cobertura {antes_cob*100:.0f}% -> {cob*100:.0f}%")
            if cob>=0.3: break
        if cob<0.2:
            # último recurso: Lightmap Pack (face a face, proporcional à área; feito para bake)
            bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.uv.lightmap_pack(PREF_CONTEXT='ALL_FACES', PREF_PACK_IN_ONE=True, PREF_NEW_UVLAYER=False, PREF_BOX_DIV=12, PREF_MARGIN_DIV=0.1)
            bpy.ops.object.mode_set(mode='OBJECT')
            cob=cobertura(); log(f"  lightmap pack: cobertura {cob*100:.0f}%")
    a=np.empty(len(o.data.loops)*2,dtype=np.float32); o.data.uv_layers["bake"].data.foreach_get("uv",a); a=a.reshape(-1,2)
    log("uv ok", o.name, len(o.data.polygons), "faces, faixa", np.ptp(a,0).round(3), f"cobertura {cob*100:.0f}%")
    if cob<0.2:
        log("  !!! UV ruim, diagnosticando", o.name)
        bm=bmesh.new(); bm.from_mesh(o.data); uvl=bm.loops.layers.uv["bake"]; visto=set(); ilhas=[]
        for f in bm.faces:
            if f.index in visto: continue
            pilha=[f]; visto.add(f.index); faces=[]
            while pilha:
                g=pilha.pop(); faces.append(g)
                for l in g.loops:
                    for el in l.edge.link_loops:
                        h=el.face
                        if h.index in visto: continue
                        a1,a2=l[uvl].uv,l.link_loop_next[uvl].uv; b1,b2=el[uvl].uv,el.link_loop_next[uvl].uv
                        if ((a1-b2).length<1e-6 and (a2-b1).length<1e-6) or ((a1-b1).length<1e-6 and (a2-b2).length<1e-6):
                            visto.add(h.index); pilha.append(h)
            uv=np.array([[l[uvl].uv.x,l[uvl].uv.y] for g in faces for l in g.loops]); pts=np.array([list(v.co) for g in faces for v in g.verts])
            ilhas.append((float(np.ptp(uv,0).max()), sum(g.calc_area() for g in faces), len(faces), o.data.materials[faces[0].material_index].name if o.data.materials[faces[0].material_index] else None, np.ptp(pts,0).round(2)))
        log("  ilhas", len(ilhas))
        for x in sorted(ilhas, key=lambda x:-x[0])[:6]: log(f"  MAIOR extUV={x[0]:.3f} area3d={x[1]:.3f} faces={x[2]} {x[3]} dims={x[4]}")
        por={}
        for x in ilhas: por.setdefault(x[3],[0,0]); por[x[3]][0]+=1; por[x[3]][1]+=x[2]
        for k,v in sorted(por.items(), key=lambda kv:-kv[1][0])[:6]: log(f"  MAT {k} ilhas={v[0]} faces={v[1]}")
        bm.free(); falhas.append(o.name)

for x in list(bpy.data.meshes):
    if x.users==0: bpy.data.meshes.remove(x)
log("atlas com UV ruim:", falhas)
# caminhos absolutos e reais: o prep.blend fica em outra pasta (às vezes atrás de um atalho/symlink) e o caminho
# relativo das bibliotecas linkadas não resolve. Aí o Cycles não acha as texturas que moram nelas e desenha o
# xadrez de "imagem não encontrada" (madeira do mostruário, tela do monitor, frente do balcão)
for _l in bpy.data.libraries:
    _l.filepath = os.path.realpath(bpy.path.abspath(_l.filepath))
for _i in bpy.data.images:
    if _i.library is None and _i.source == 'FILE' and not _i.packed_file and _i.filepath:
        _i.filepath = os.path.realpath(bpy.path.abspath(_i.filepath))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(SAIDA, "prep.blend"), compress=True, relative_remap=False)
log("prep.blend salvo")

