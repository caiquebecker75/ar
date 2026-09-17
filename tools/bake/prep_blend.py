# Etapa 1 (a partir do .blend do projeto, o jeito mais fiel): usa a cena como está (luzes, ambiente, materiais,
# modificadores, instâncias), converte tudo que aparece no render em malha, solda/reduz, agrupa em atlas e
# cria o UV "bake". Salva <saida>/prep.blend.
#   blender -b PROJETO.blend --python tools/bake/prep_blend.py -- --saida=PASTA [--hdr=ARQ.hdr] [--escala-alvo=1]
# --hdr: substitui um HDR de ambiente que não abriu (ex.: caminho D:\ de outra máquina).
import bpy, bmesh, math, mathutils, time, sys, os
T0=time.time()
def log(*a): print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)
_args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
_opt = lambda k, d=None: next((a.split("=", 1)[1] for a in _args if a.startswith(f"--{k}=")), d)
SAIDA = os.path.abspath(_opt("saida", "."))
HDR = _opt("hdr")
ESCALA = float(_opt("escala-alvo", 1))   # multiplica os limites de triângulos por malha
sc = bpy.context.scene

# ---------- ambiente: troca HDR que não abriu ----------
if HDR and sc.world and sc.world.use_nodes:
    for n in sc.world.node_tree.nodes:
        if n.type == 'TEX_ENVIRONMENT' and (not n.image or n.image.size[0] == 0):
            n.image = bpy.data.images.load(HDR, check_existing=True)
            log("HDR trocado:", HDR, tuple(n.image.size))

# ---------- tudo que aparece no render vira malha real (modificadores e instâncias aplicados) ----------
dg = bpy.context.evaluated_depsgraph_get()
col = bpy.data.collections.new("AR_MALHAS"); sc.collection.children.link(col)
novos = 0
for inst in dg.object_instances:
    ob = inst.object
    if ob.type not in {'MESH', 'CURVE', 'FONT', 'SURFACE', 'META'}: continue
    orig = ob.original
    if not inst.is_instance and (orig.hide_render or not orig.visible_get()): continue
    try:
        me = bpy.data.meshes.new_from_object(ob, preserve_all_data_layers=True, depsgraph=dg)
    except RuntimeError:
        continue
    if not me.polygons: bpy.data.meshes.remove(me); continue
    o = bpy.data.objects.new(orig.name, me)
    o.matrix_world = inst.matrix_world.copy()
    col.objects.link(o); novos += 1
# apaga o resto (menos luzes)
for o in list(sc.objects):
    if o.type == 'LIGHT' or o.name in col.objects: continue
    bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections):
    if c != col and c.users == 0: bpy.data.collections.remove(c)
log("malhas do render:", novos, "| luzes:", sum(1 for o in sc.objects if o.type == 'LIGHT'))

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
meshes=[o for o in sc.objects if o.type=='MESH']
for o in meshes:
    if o.data.users>1: o.data=o.data.copy()
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
    def aplicar(mod):
        dg=bpy.context.evaluated_depsgraph_get()
        novo=bpy.data.meshes.new_from_object(o.evaluated_get(dg))
        velho=o.data; o.modifiers.clear(); o.data=novo; bpy.data.meshes.remove(velho)
    if tri>alvo:
        # 1) junta faces planas sem atravessar corte de UV/material (artes continuam no lugar, sem picotar a malha)
        m=o.modifiers.new("planar",'DECIMATE'); m.decimate_type='DISSOLVE'; m.angle_limit=math.radians(4)
        m.delimit={'MATERIAL','UV'}; aplicar(m)
        tri2=sum(len(p.vertices)-2 for p in o.data.polygons)
        # 2) se ainda passa do limite, colapso. Nunca em peça com arte impressa (placa, KV, logo, backlight):
        #    o colapso junta vértices e embaralha o UV da arte (logo picotado em triângulos)
        if tri2>alvo and not tem_arte(o):
            m=o.modifiers.new("reduz",'DECIMATE'); m.ratio=max(alvo/tri2, 0.003); m.use_collapse_triangulate=True; aplicar(m)
    depois+=sum(len(p.vertices)-2 for p in o.data.polygons)
log("triangulos", antes, "->", depois, "| vertices soldados", soldados)

# ---------- grupos de atlas por tamanho e área ----------
def area(o):
    M=o.matrix_world; s=0
    for p in o.data.polygons:
        v=[M@o.data.vertices[i].co for i in p.vertices]
        for k in range(1,len(v)-1): s+=((v[k]-v[0]).cross(v[k+1]-v[0])).length/2
    return s
info=[(area(o), max(o.dimensions), o) for o in meshes]
def bins(itens, alvo):
    n=max(1, math.ceil(sum(a for a,_,_ in itens)/alvo)); caixas=[[0,[]] for _ in range(n)]
    for a,_,o in sorted(itens, key=lambda x:-x[0]):
        c=min(caixas, key=lambda c:c[0]); c[0]+=a; c[1].append(o)
    return caixas
grupos={}
for nome, filtro, alvo, px in [("grande", lambda d: d>=1.5, 25, 4096), ("medio", lambda d: 0.25<=d<1.5, 14, 4096), ("pequeno", lambda d: d<0.25, 2.5, 2048)]:
    for i,(a,objs) in enumerate(bins([x for x in info if filtro(x[1])], alvo)):
        grupos[f"{nome}{i+1}"]=(objs, px, a)
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
    o.data.uv_layers[0].active_render=True
    o.data.uv_layers.active=o.data.uv_layers["bake"]
    bpy.context.view_layer.objects.active=o; o.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    # faces grandes/côncavas da dissolução planar quebram a área de UV: triangula antes
    bpy.ops.mesh.quads_convert_to_tris(quad_method='BEAUTY', ngon_method='BEAUTY')
    bpy.ops.uv.smart_project(angle_limit=math.radians(89), island_margin=0.0, area_weight=0.0, correct_aspect=False, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode='OBJECT')
    ag=consertar_agulhas(o)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=1.5/px, shape_method="AABB")
    bpy.ops.object.mode_set(mode='OBJECT'); o.select_set(False)
    log("  ilhas-agulha refeitas:", ag)
    o["atlas_px"]=px
    import numpy as np
    def cobertura():
        uvb=o.data.uv_layers["bake"].data; c=0
        for p in o.data.polygons:
            pts=[uvb[i].uv for i in p.loop_indices]
            for k in range(1,len(pts)-1): c+=abs((pts[k]-pts[0]).cross(pts[k+1]-pts[0]))/2
        return c
    cob=cobertura()
    if cob<0.35:
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
            bpy.ops.uv.pack_islands(rotate=True, margin_method="FRACTION", margin=1.5/px, shape_method="AABB")
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
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(SAIDA, "prep.blend"), compress=True)
log("prep.blend salvo")

