# Exemplo completo (Display PP Polenguinho): .lxo -> Blender -> raw.glb com texturas por projeção cúbica dos localizadores do Modo.
# Rodar: LXO=... /Applications/Blender.app/Contents/MacOS/Blender -b -P build_display_pp.py  (ajuste BASE, TEX, FORA)
import bpy, bmesh, mathutils, os, struct, math
bpy.ops.wm.read_factory_settings(use_empty=True)
BASE='/Users/caiquebecker/produtos-75lab/.work/drive-pp/'
os.chdir(BASE)
exec(open('lxo_parse.py').read().split("import collections")[0])
def vx(b,o):
    v=struct.unpack('>H',b[o:o+2])[0]
    if v>=0xff00: return struct.unpack('>I',b[o:o+4])[0]&0xffffff,o+4
    return v,o+2
def layer_geo(L):
    pts=None;polys=[];ptag={}
    for t,b in L['chunks']:
        if t=='PNTS': pts=[struct.unpack('>3f',b[k:k+12]) for k in range(0,len(b),12)]
        elif t=='POLS' and b[:4]==b'FACE':
            o=4
            while o<len(b):
                nv=struct.unpack('>H',b[o:o+2])[0]; o+=2; f=[]   # LXO: contagem em 16 bits cheios
                for _ in range(nv): v,o=vx(b,o); f.append(v)
                polys.append(f)
        elif t=='PTAG' and b[:4]==b'MATR':
            o=4
            while o<len(b):
                p,o=vx(b,o); tg=struct.unpack('>H',b[o:o+2])[0]; o+=2; ptag[p]=tg
    return pts,polys,ptag
L=[x for x in layers if x['name']=='Base-Display'][0]
pts,polys,ptag=layer_geo(L)
xs=[p[0] for p in pts]; ys=[p[1] for p in pts]; zs=[p[2] for p in pts]
ALT=1.40; S=ALT/(max(ys)-min(ys))
CX=(min(xs)+max(xs))/2; CZ=(min(zs)+max(zs))/2; Y0=min(ys)
def B(p): return mathutils.Vector(((p[0]-CX)*S, (p[2]-CZ)*S, (p[1]-Y0)*S))
# texturas: localizador do Modo (pos, escala) — no Modo z = -z do arquivo
TEX={
 'Azul':        ('texturas/Cor.png',        (0.058,17.591,-1.6266),(9.438,16.452,0.05)),
 'Lateral1':    ('texturas/Lateral-2.jpg',  (-4.661,15.996,-3.2772),(1.0,31.6415,6.5331)),
 'Lateral2':    ('texturas/Lateral.jpg',    (4.777,15.996,-3.2772),(1.0,31.6415,6.5331)),
 'Faixa':       ('texturas/Frente.jpg',     (-2.0962,17.5557,0.0175),(9.3208,21.1639,0.065)),
 'Base':        ('texturas/Base-Update.png',(-2.2669,4.038,-0.038),(5.4128,7.7957,1.1424)),
 'Testeira-Ok': ('texturas/Testeira-1.png', (-2.2759,35.1458,-6.443),(5.5337,8.2020,1.0)),
}
COR={'Base-Branco':(0.92,0.92,0.92),'Black':(0.02,0.02,0.02),'Default':(0.6,0.6,0.6)}
# lado de fora de cada arte (em coordenadas do Blender) e textura do verso
FORA={'Faixa':(0,-1,0),'Base':(0,-1,0),'Testeira-Ok':(0,-1,0),'Lateral1':(-1,0,0),'Lateral2':(1,0,0)}
VERSO={'Testeira-Ok':'texturas/Testeira-2.png'}
mats={}
def mat(nome, img=None, cor=None, um_lado=False):
    if nome in mats: return mats[nome]
    m=bpy.data.materials.new(nome); m.use_nodes=True; nt=m.node_tree; bsdf=nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value=0.6
    if img:
        t=nt.nodes.new('ShaderNodeTexImage'); t.image=bpy.data.images.load(BASE+img); t.extension='CLIP'
        nt.links.new(t.outputs['Color'],bsdf.inputs['Base Color'])
    else:
        bsdf.inputs['Base Color'].default_value=(*cor,1)
        m.diffuse_color=(*cor,1)   # cor no Workbench (conferência)
    m.use_backface_culling=um_lado   # glTF: doubleSided = não culling (o prepare-glb duplica o verso só desses)
    mats[nome]=m; return m
# azul do polionda = média do Cor.png (espaço linear)
im=bpy.data.images.load(BASE+'texturas/Cor.png'); px=im.pixels[:]; n=len(px)//4
_srgb=tuple(sum(px[i*4+c] for i in range(0,n,97))/len(range(0,n,97)) for c in range(3))
AZUL=tuple((c/12.92) if c<=0.04045 else ((c+0.055)/1.055)**2.4 for c in _srgb)
print('AZUL linear', [round(c,3) for c in AZUL])
def material_do_grupo(tag):
    if tag=='Azul': return mat('Azul', cor=AZUL)
    if tag in TEX: return mat(tag, img=TEX[tag][0], um_lado=True)
    return mat(tag, cor=COR.get(tag,(1,0,1)))
def uv_fora(tag, v, fora, img_verso=False):
    _,pos,scl=TEX[tag]
    q=(pts[v][0],pts[v][1],-pts[v][2])            # coordenadas do Modo
    r=[(q[i]-pos[i])/scl[i] for i in range(3)]
    fx,fy,fz=fora
    if fy<0:   u= r[0]        # frente (-Y): direita da câmera = +X
    elif fy>0: u=-r[0]        # trás (+Y)
    elif fx<0: u= r[2]        # lado esquerdo (-X): direita = frente = +Z do Modo
    else:      u=-r[2]        # lado direito (+X)
    return (u+0.5, r[1]+0.5)
_tt=[fi for fi,f in enumerate(polys) if tags[ptag.get(fi,11)]=='Testeira-Ok']
_tv=[B(pts[v]) for fi in _tt for v in polys[fi]]
TX0,TX1=min(p.x for p in _tv),max(p.x for p in _tv); TZ0,TZ1=min(p.z for p in _tv),max(p.z for p in _tv)
print('TESTEIRA m', round(TX0,3),round(TX1,3),round(TZ0,3),round(TZ1,3))
def na_testeira(cs):
    return all(TX0-0.004<=c.x<=TX1+0.004 and TZ0-0.004<=c.z<=TZ1+0.004 for c in cs)
me=bpy.data.meshes.new('DisplayPP'); bm=bmesh.new(); uvl=bm.loops.layers.uv.new('UVMap')
ordem=[]; est={}
def idx_mat(m):
    if m.name not in ordem: ordem.append(m.name)
    return ordem.index(m.name)
def novo_tri(coords):
    return bm.faces.new([bm.verts.new(c) for c in coords])
for fi,f in enumerate(polys):
    if len(f)<3: continue
    tag=tags[ptag.get(fi,11)]
    if tag=='Base-Branco':
        cs=[B(pts[v]) for v in dict.fromkeys(f)]
        ext=sorted([max(c.x for c in cs)-min(c.x for c in cs), max(c.y for c in cs)-min(c.y for c in cs), max(c.z for c in cs)-min(c.z for c in cs)])
        if ext[1]>0.006: tag='Azul'
    m=material_do_grupo(tag)
    loops=[]; cur=[]
    for v in f:
        if v in cur:
            k=cur.index(v); sub=cur[k:]; cur=cur[:k+1]
            if len(sub)>=3: loops.append(sub)
        else: cur.append(v)
    if len(cur)>=3: loops.append(cur)
    grupos=[]
    if len(loops)==1 and len(loops[0])==len(f):
        grupos=[list(f)]
    else:
        loops.sort(key=len, reverse=True); flat=[v for Lp in loops for v in Lp]
        tri=mathutils.geometry.tessellate_polygon([[B(pts[v]) for v in Lp] for Lp in loops])
        grupos=[[flat[a],flat[b_],flat[c]] for a,b_,c in tri]
    for idx in grupos:
        try: face=novo_tri([B(pts[v]) for v in idx])
        except ValueError: continue
        face.material_index=idx_mat(m); est[tag]=est.get(tag,0)+1
        if tag in ('Azul','Base-Branco'):
            face.normal_update()
            cs=[l.vert.co for l in face.loops]
            if abs(face.normal.y)>0.9 and na_testeira(cs) and min(c.z for c in cs)>TZ0+0.02:
                if face.normal.y<0: face.normal_flip()
                mt=mat('Testeira-verso', img='texturas/Testeira-2.png', um_lado=True); face.material_index=idx_mat(mt)
                for loop in face.loops:
                    v=min(idx, key=lambda vv:(B(pts[vv])-loop.vert.co).length)
                    loop[uvl].uv=uv_fora('Testeira-Ok', v, (0,1,0))
                est['Testeira-verso']=est.get('Testeira-verso',0)+1
            continue
        if tag not in FORA: continue
        fora=mathutils.Vector(FORA[tag])
        face.normal_update()
        if face.normal.dot(fora)<0:
            face.normal_flip(); idx=list(reversed(idx))
            # normal_flip inverte a ordem dos loops: realinha os índices
        lp=list(face.loops)
        # casa cada loop com o vértice original pela posição
        for loop in lp:
            co_=loop.vert.co
            v=min(idx, key=lambda vv:(B(pts[vv])-co_).length)
            loop[uvl].uv=uv_fora(tag, v, FORA[tag])
        # verso explícito, 1 mm para dentro
        off=-fora*0.001
        try: tras=bm.faces.new([bm.verts.new(l.vert.co+off) for l in reversed(lp)])
        except ValueError: continue
        if tag in VERSO:
            mv=mat(tag+'-verso', img=VERSO[tag], um_lado=True); tras.material_index=idx_mat(mv)
            for loop in tras.loops:
                v=min(idx, key=lambda vv:(B(pts[vv])-(loop.vert.co-off)).length)
                loop[uvl].uv=uv_fora(tag, v, tuple(-c for c in FORA[tag]))
        else:
            tras.material_index=idx_mat(mat('Azul-verso', cor=AZUL, um_lado=True))
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
bm.to_mesh(me); bm.free()
for nome in ordem: me.materials.append(bpy.data.materials[nome])
ob=bpy.data.objects.new('DisplayPP',me); bpy.context.scene.collection.objects.link(ob)
print('TRIS por grupo', est); print('DIMS cm', [round(x*100,1) for x in ob.dimensions])
out=os.environ.get('OUT','raw.glb')
bpy.ops.export_scene.gltf(filepath=BASE+out, export_format='GLB', export_image_format='JPEG', export_jpeg_quality=90)
# conferência: vistas com textura (workbench)
sc=bpy.context.scene; sc.render.engine='BLENDER_WORKBENCH'
sc.display.shading.color_type='TEXTURE'; sc.display.shading.light='STUDIO'; sc.display.shading.show_backface_culling=os.environ.get('CULL','1')=='1'
sc.render.resolution_x=500; sc.render.resolution_y=1300
cam=bpy.data.cameras.new('c'); cam.type='ORTHO'; cam.ortho_scale=1.5; co=bpy.data.objects.new('cam',cam); sc.collection.objects.link(co); sc.camera=co
alvo=mathutils.Vector((0,0,0.70))
os.makedirs(BASE+'diag',exist_ok=True)
for n,loc in {'1_frente':(0,-3,0.7),'2_esquerda':(-3,0,0.7),'3_direita':(3,0,0.7),'4_tras':(0,3,0.7)}.items():
    co.location=loc; co.rotation_euler=(alvo-mathutils.Vector(loc)).to_track_quat('-Z','Y').to_euler()
    sc.render.filepath=BASE+f'diag/tex{os.environ.get("SUF","")}_{n}.png'; bpy.ops.render.render(write_still=True)
cam.type='PERSP'; cam.lens=40; sc.render.resolution_x=700
co.location=(-1.3,-2.2,1.3); co.rotation_euler=(alvo-co.location).to_track_quat('-Z','Y').to_euler()
co.location=(-0.9,-1.9,1.25); co.rotation_euler=(alvo-co.location).to_track_quat('-Z','Y').to_euler()
sc.render.filepath=BASE+f'diag/tex{os.environ.get("SUF","")}_5_iso.png'; bpy.ops.render.render(write_still=True)
