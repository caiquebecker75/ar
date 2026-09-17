# Etapa 3: bake da iluminação do Cycles nos atlas (qualidade "Viewport Shading: Rendered").
#   blender -b <saida>/prep.blend --python tools/bake/bake.py -- [--so=ATLAS_grande1] [--luz-px=1024] [--luz-amostras=512]
# Por atlas: cor (albedo, 4096) + emissão (LEDs, 4096) + luz difusa (direta + indireta, 1024, suavizada
# para tirar ruído sem borrar as artes). Resultado = cor × luz + emissão, com a mesma gestão de cor da cena
# (Filmic High Contrast, exposição 0,5), gravado em JPEG em bake/<atlas>.jpg.
import bpy, numpy as np, os, sys, time

T0 = time.time()
def log(*a): print(f"[{time.time()-T0:6.0f}s]", *a, flush=True)
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
opt = lambda k, d: next((a.split("=", 1)[1] for a in args if a.startswith(f"--{k}=")), d)
SO = opt("so", None)            # um ou mais atlas separados por vírgula
FATOR_METAL = float(opt("metal-fator", 0.4))
APENAS_RUG = "--apenas-rugosidade" in args   # refaz só o mapa de rugosidade (rápido)
LUZ_PX = int(opt("luz-px", 1024))
LUZ_AMOSTRAS = int(opt("luz-amostras", 512))
PASTA = bpy.path.abspath("//bake")
os.makedirs(PASTA, exist_ok=True)

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'METAL'; prefs.get_devices()
for d in prefs.devices: d.use = True
sc.cycles.device = 'GPU'
sc.render.bake.use_clear = True
sc.render.bake.margin_type = 'EXTEND'
sc.render.bake.target = 'IMAGE_TEXTURES'

def imagem(nome, px):
    img = bpy.data.images.new(nome, px, px, alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Linear Rec.709'
    return img

def alvo(obj, img):
    # o bake grava no nó de imagem ATIVO de cada material do objeto
    for slot in obj.material_slots:
        m = slot.material
        if not m: continue
        nt = m.node_tree
        n = nt.nodes.get("BAKE_ALVO") or nt.nodes.new("ShaderNodeTexImage")
        n.name = "BAKE_ALVO"; n.image = img; n.select = True
        nt.nodes.active = n

def bake(obj, tipo, filtro, px, amostras, margem):
    img = imagem(f"{obj.name}_{tipo}_{'_'.join(sorted(filtro))}", px)
    alvo(obj, img)
    sc.cycles.samples = amostras
    sc.render.bake.margin = margem
    t = time.time()
    bpy.ops.object.bake(type=tipo, pass_filter=filtro, margin=margem, use_clear=True)
    log(f"  {tipo} {sorted(filtro)} {px}px {amostras}spp em {time.time()-t:.0f}s")
    return img

def pixels(img):
    a = np.empty(img.size[0] * img.size[1] * 4, dtype=np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(img.size[1], img.size[0], 4)

def suavizar(a, sigma):
    # gaussiana separável (tira o ruído do bake de luz, que varia devagar)
    r = int(3 * sigma); x = np.arange(-r, r + 1); k = np.exp(-x**2 / (2 * sigma**2)); k /= k.sum()
    for eixo in (0, 1):
        a = np.apply_along_axis(lambda v: np.convolve(np.pad(v, r, mode='edge'), k, mode='valid'), eixo, a)
    return a

# metal não tem cor difusa: no bake ele sairia preto (ex.: estantes azuis). Zera o metálico para a cor entrar na textura.
for m in bpy.data.materials:
    if not m.use_nodes: continue
    for n in m.node_tree.nodes:
        if n.type == 'BSDF_PRINCIPLED':
            ent = n.inputs['Metallic']
            metal = 0.0 if ent.links else ent.default_value
            for l in list(ent.links): m.node_tree.links.remove(l)
            ent.default_value = 0.0
            # metal reflete menos luz que tinta fosca da mesma cor: escurece na proporção do metálico
            # (calibrado na coluna laranja do stand NGV contra o render do Cycles)
            cor = n.inputs['Base Color']
            if metal > 0 and not cor.links:
                k = 1 - metal * (1 - FATOR_METAL)
                cor.default_value = (cor.default_value[0] * k, cor.default_value[1] * k, cor.default_value[2] * k, cor.default_value[3])

def salvar_rugosidade(o, px):
    # rugosidade assada (reflexos ao vivo no AR e no 3D). A imagem do bake é float: salvar direto em PNG dá zero,
    # então copia para uma imagem de 8 bits sem gestão de cor.
    rpx = max(1024, px // 4)
    rug = bake(o, 'ROUGHNESS', set(), rpx, 1, 4)
    r = pixels(rug)
    rb = bpy.data.images.new(f"{o.name}_rug8", rpx, rpx, alpha=False, float_buffer=False)
    rb.colorspace_settings.name = 'Non-Color'
    rb.pixels.foreach_set(np.clip(r, 0, 1).ravel().astype(np.float32))
    caminho_r = os.path.join(PASTA, f"{o.name}_rug.png")
    rb.filepath_raw = caminho_r; rb.file_format = 'PNG'; rb.save()
    log(f"  rugosidade média {float(r[..., 0].mean()):.2f}", caminho_r)
    bpy.data.images.remove(rug); bpy.data.images.remove(rb)

atlas = [o for o in sc.objects if o.type == 'MESH' and o.name.startswith("ATLAS_") and (not SO or o.name in SO.split(","))]
for o in atlas:
    px = int(o.get("atlas_px", 4096))
    log(o.name, px, "px", len(o.data.polygons), "faces")
    o.data.uv_layers.active = o.data.uv_layers["bake"]
    o.data.uv_layers["UVMap"].active_render = True
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True); bpy.context.view_layer.objects.active = o

    if APENAS_RUG:
        salvar_rugosidade(o, px); continue
    cor = bake(o, 'DIFFUSE', {'COLOR'}, px, 8, 16 if px >= 4096 else 8)
    emi = bake(o, 'EMIT', set(), px, 4, 16 if px >= 4096 else 8)
    luz_px = LUZ_PX if px >= 4096 else LUZ_PX // 2
    luz = bake(o, 'DIFFUSE', {'DIRECT', 'INDIRECT'}, luz_px, LUZ_AMOSTRAS, 4)

    def st(n, a):
        a = a[..., :3]; nz = (a.max(-1) > 1e-6).mean()
        log(f"  STAT {n}: media={a.mean():.4f} max={a.max():.3f} preenchido={nz*100:.1f}%")
    st("cor", pixels(cor)); st("emissao", pixels(emi)); st("luz", pixels(luz))
    # luz: suaviza no tamanho do bake e amplia para o tamanho do atlas
    L = pixels(luz)[..., :3]
    L = np.stack([suavizar(L[..., c], 1.4) for c in range(3)], -1)
    luz.pixels.foreach_set(np.dstack([L, np.ones(L.shape[:2])]).ravel().astype(np.float32))
    luz.scale(px, px)
    L = pixels(luz)[..., :3]
    st("luz ampliada", L)

    final = pixels(cor)[..., :3] * L + pixels(emi)[..., :3]
    out = bpy.data.images.new(f"{o.name}_final", px, px, alpha=False, float_buffer=True)
    out.colorspace_settings.name = 'Linear Rec.709'
    out.pixels.foreach_set(np.dstack([final, np.ones(final.shape[:2], np.float32)]).ravel().astype(np.float32))

    s = sc.render.image_settings
    s.file_format = 'JPEG'; s.quality = 92; s.color_mode = 'RGB'
    caminho = os.path.join(PASTA, f"{o.name}.jpg")
    out.save_render(caminho, scene=sc)   # aplica Filmic High Contrast / exposição da cena
    log("  salvo", caminho, os.path.getsize(caminho) // 1024, "KB")

    salvar_rugosidade(o, px)
    for img in (cor, emi, luz, out): bpy.data.images.remove(img)

log("fim")
