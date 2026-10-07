# Coordenadas que dependem do objeto original e mudam quando as peças viram um atlas só:
#   · Texture Coordinate > Object / Generated (e textura procedural sem vetor ligado, que usa Generated);
#   · Geometry > Random Per Island (sorteio de cor por ilha: cartelas de cor, folhas).
# Grava tudo como atributo na malha ANTES de juntar e troca os nós dos materiais por "Attribute".
# Usado pelo prep_blend.py logo depois de converter o render em malha.
import bpy, numpy as np

PROCEDURAIS = {'TEX_NOISE', 'TEX_WAVE', 'TEX_VORONOI', 'TEX_GRADIENT', 'TEX_MAGIC', 'TEX_CHECKER',
               'TEX_BRICK', 'TEX_WHITE_NOISE', 'TEX_GABOR', 'TEX_MUSGRAVE'}

def _rot(x, k): return ((x << k) | (x >> (32 - k))) & 0xFFFFFFFF

def hash_uint_to_float(kx):
    """hash_uint_to_float do Cycles (Jenkins lookup3, util/hash.h)."""
    M = 0xFFFFFFFF
    a = b = c = (0xdeadbeef + (1 << 2) + 13) & M
    a = (a + kx) & M
    c ^= b; c = (c - _rot(b, 14)) & M
    a ^= c; a = (a - _rot(c, 11)) & M
    b ^= a; b = (b - _rot(a, 25)) & M
    c ^= b; c = (c - _rot(b, 16)) & M
    a ^= c; a = (a - _rot(c, 4)) & M
    b ^= a; b = (b - _rot(a, 14)) & M
    c ^= b; c = (c - _rot(b, 24)) & M
    return c / float(M)

def random_por_ilha(me):
    """Mesmo cálculo do Cycles (blender/mesh.cpp, attr_create_random_per_island): DisjointSet nas arestas,
    união por rank, raiz do 1o vértice de cada face."""
    n = len(me.vertices)
    pai = list(range(n)); rank = [0] * n
    def find(x):
        r = x
        while pai[r] != r: r = pai[r]
        while pai[x] != r: pai[x], x = r, pai[x]
        return r
    ed = np.empty(len(me.edges) * 2, dtype=np.int64); me.edges.foreach_get("vertices", ed)
    for i in range(0, len(ed), 2):
        x, y = find(int(ed[i])), find(int(ed[i + 1]))
        if x == y: continue
        if rank[x] < rank[y]: pai[x] = y
        elif rank[x] > rank[y]: pai[y] = x
        else: pai[y] = x; rank[x] += 1
    lt = np.empty(len(me.polygons), dtype=np.int64); me.polygons.foreach_get("loop_start", lt)
    lv = np.empty(len(me.loops), dtype=np.int64); me.loops.foreach_get("vertex_index", lv)
    cache = {}
    out = np.empty(len(me.polygons), dtype=np.float32)
    for i, ls in enumerate(lt):
        r = find(int(lv[ls]))
        if r not in cache: cache[r] = hash_uint_to_float(r)
        out[i] = cache[r]
    return out

def _arvores(m):
    vistos = set(); fila = [m.node_tree]
    while fila:
        nt = fila.pop()
        if nt is None or nt in vistos: continue
        vistos.add(nt); yield nt
        fila += [n.node_tree for n in nt.nodes if n.type == 'GROUP' and n.node_tree]

def precisa(materiais):
    """Quais atributos estes materiais usam: {'obj','gen','ilha'}."""
    uso = set()
    for m in materiais:
        if not m or not m.node_tree: continue
        for nt in _arvores(m):
            for n in nt.nodes:
                if n.type == 'TEX_COORD':
                    if n.outputs['Object'].is_linked: uso.add('obj')
                    if n.outputs['Generated'].is_linked: uso.add('gen')
                elif n.type == 'NEW_GEOMETRY' and n.outputs['Random Per Island'].is_linked: uso.add('ilha')
                elif n.type in PROCEDURAIS and 'Vector' in n.inputs and not n.inputs['Vector'].is_linked: uso.add('gen')
    return uso

def gravar(o, orig_data):
    """Grava os atributos na malha de o (coordenadas locais = espaço do objeto original)."""
    me = o.data
    uso = precisa(list(me.materials))
    if not uso: return uso
    co = np.empty(len(me.vertices) * 3, dtype=np.float32); me.vertices.foreach_get("co", co)
    if 'obj' in uso:
        a = me.attributes.get("ar_obj") or me.attributes.new("ar_obj", 'FLOAT_VECTOR', 'POINT')
        a.data.foreach_set("vector", co)
    if 'gen' in uso:
        c = co.reshape(-1, 3)
        try:
            loc = np.array(orig_data.texspace_location); tam = np.array(orig_data.texspace_size)
        except Exception:
            loc = tam = None
        if loc is None or not np.all(tam > 1e-9):
            mn, mx = c.min(0), c.max(0); loc = (mn + mx) / 2; tam = np.maximum((mx - mn) / 2, 1e-9)
        g = (c - (loc - tam)) / (2 * tam)
        a = me.attributes.get("ar_gen") or me.attributes.new("ar_gen", 'FLOAT_VECTOR', 'POINT')
        a.data.foreach_set("vector", g.astype(np.float32).ravel())
    if 'ilha' in uso:
        a = me.attributes.get("ar_ilha") or me.attributes.new("ar_ilha", 'FLOAT', 'FACE')
        a.data.foreach_set("value", random_por_ilha(me))
    return uso

def trocar_nos():
    """Troca nos materiais (e grupos) as fontes originais pelos atributos gravados. Torna locais antes."""
    for ng in list(bpy.data.node_groups):
        if ng.library: ng.make_local()
    for m in list(bpy.data.materials):
        if m.library: m.make_local()
    trocados = 0
    for m in bpy.data.materials:
        if not m.node_tree: continue
        for nt in _arvores(m):
            if nt.get("ar_coords"): continue
            nt["ar_coords"] = 1
            def attr(nome, saida):
                at = nt.nodes.new("ShaderNodeAttribute"); at.attribute_type = 'GEOMETRY'; at.attribute_name = nome
                return at.outputs[saida]
            for n in list(nt.nodes):
                if n.type == 'TEX_COORD':
                    for sock, nome in (('Object', 'ar_obj'), ('Generated', 'ar_gen')):
                        if n.outputs[sock].is_linked:
                            src = attr(nome, 'Vector')
                            for l in list(n.outputs[sock].links): nt.links.new(src, l.to_socket); trocados += 1
                elif n.type == 'NEW_GEOMETRY' and n.outputs['Random Per Island'].is_linked:
                    src = attr('ar_ilha', 'Fac')
                    for l in list(n.outputs['Random Per Island'].links): nt.links.new(src, l.to_socket); trocados += 1
                elif n.type in PROCEDURAIS and 'Vector' in n.inputs and not n.inputs['Vector'].is_linked:
                    nt.links.new(attr('ar_gen', 'Vector'), n.inputs['Vector']); trocados += 1
    return trocados


# ---------- UV: o que a peça usa no render vira "UVMap" (o atlas junta camadas pelo NOME) ----------
# Asset comprado costuma trazer o UV como "LayerUV_0", "uv0", "automap"... Ao juntar, a peça fica sem nada na
# camada "UVMap" do atlas e a textura sai branca (folha da palmeira) ou com outro desenho (mármore do piso).
_variantes = {}

def _refs_uv(m):
    """Nós com UV por nome nesta árvore (e grupos)."""
    out = []
    for nt in _arvores(m):
        for n in nt.nodes:
            if n.type in ('UVMAP', 'NORMAL_MAP', 'TANGENT') and getattr(n, 'uv_map', ''):
                out.append(n)
            elif n.type == 'ATTRIBUTE' and n.attribute_name:
                out.append(n)
    return out

def _remapear_material(m, mapa):
    chave = (m.name, tuple(sorted(mapa.items())))
    if chave in _variantes: return _variantes[chave]
    if not any((getattr(n, 'uv_map', '') in mapa) or (n.type == 'ATTRIBUTE' and n.attribute_name in mapa) for n in _refs_uv(m)):
        _variantes[chave] = m; return m
    c = m.copy(); c.name = m.name + "__uv"
    copiados = {}
    def fundo(nt):
        for n in nt.nodes:
            if n.type == 'GROUP' and n.node_tree:
                if n.node_tree.name not in copiados: copiados[n.node_tree.name] = n.node_tree.copy()
                n.node_tree = copiados[n.node_tree.name]; fundo(n.node_tree)
            if n.type in ('UVMAP', 'NORMAL_MAP', 'TANGENT') and getattr(n, 'uv_map', '') in mapa: n.uv_map = mapa[n.uv_map]
            elif n.type == 'ATTRIBUTE' and n.attribute_name in mapa: n.attribute_name = mapa[n.attribute_name]
    fundo(c.node_tree)
    _variantes[chave] = c
    return c

def normalizar_uv(o):
    me = o.data
    if not me.uv_layers: return False
    r = next((u for u in me.uv_layers if u.active_render), me.uv_layers[0])
    if r.name == "UVMap": return False
    mapa = {r.name: "UVMap"}
    velho = me.uv_layers.get("UVMap")
    if velho: velho.name = "UVMap_orig"; mapa["UVMap"] = "UVMap_orig"
    r.name = "UVMap"
    me.uv_layers.active = r
    for i, m in enumerate(me.materials):
        if m and m.node_tree: me.materials[i] = _remapear_material(m, mapa)
    return True
