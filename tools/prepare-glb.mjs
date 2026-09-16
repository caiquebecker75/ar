// Prepara um .glb exportado do Blender para AR (web, Android Scene Viewer e iPhone Quick Look).
//
//   node tools/prepare-glb.mjs <entrada.glb> <saida.glb> [--rotate-y=-90] [--max-texture=2048]
//
// 1. Aplica todas as transformações dos nós na geometria (escala negativa vira
//    geometria espelhada com a ordem dos triângulos corrigida — o Quick Look não
//    lida bem com escala negativa).
// 2. "Assa" o KHR_texture_transform nas UVs: o Quick Look interpreta errado
//    rotação/offset de textura. Se a textura normal usa uma transformação
//    diferente da cor, ela ganha um conjunto de UV próprio.
// 3. Gira (opcional) para a frente do display ficar em +Z e põe a origem no
//    centro da base: em AR o modelo nasce apoiado no chão, de frente para quem olha.
// 4. Transforma faces "de dois lados" em geometria real (verso recuado 1 mm), menos
//    nas malhas fechadas, que nunca mostram o lado de dentro.
// 5. Reduz as texturas (máx. 2048 px; faixas muito largas até 4096) e converte para JPEG.
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { prune, dedup, getBounds, weldPrimitive, simplifyPrimitive } from '@gltf-transform/functions';
import { MeshoptSimplifier } from 'meshoptimizer';
import sharp from 'sharp';
import { statSync } from 'node:fs';

const [input, output] = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const flag = (name, def) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? Number(hit.split('=')[1]) : def;
};
const ROTATE_Y = flag('rotate-y', 0);
const MAX_TEX = flag('max-texture', 2048);
const MAX_TRI = flag('max-tri', 4000);
// cenas grandes (ex.: stand inteiro): mapas técnicos (normal, rugosidade) menores que a cor
const MAX_TEX_DATA = flag('max-texture-data', MAX_TEX);
const SIMPLIFY_ERROR = flag('simplify-error', 0.005);
// --no-verso: mantém doubleSided (web/Android) em vez de duplicar faces; --keep-alpha: textura com transparência continua PNG
const NO_VERSO = process.argv.includes('--no-verso');
const KEEP_ALPHA = process.argv.includes('--keep-alpha');
if (!input || !output) {
  console.error('uso: node tools/prepare-glb.mjs <entrada.glb> <saida.glb> [--rotate-y=graus] [--max-texture=2048]');
  process.exit(1);
}

// ---------- matrizes 4x4 (column-major, como no glTF) ----------
const mul = (a, b) => {
  const o = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) for (let r = 0; r < 4; r++) for (let k = 0; k < 4; k++) o[c * 4 + r] += a[k * 4 + r] * b[c * 4 + k];
  return o;
};
const rotY = (deg) => {
  const t = (deg * Math.PI) / 180, c = Math.cos(t), s = Math.sin(t);
  return [c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1];
};
// matriz normal = inversa transposta do bloco 3x3
const normalMatrix = (m) => {
  const [a, b, c, d, e, f, g, h, i] = [m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10]];
  const det = a * (e * i - f * h) - d * (b * i - c * h) + g * (b * f - c * e);
  const inv = [
    (e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det,
    (f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det,
    (d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det,
  ]; // column-major inverse
  // transposta
  return { n: [inv[0], inv[3], inv[6], inv[1], inv[4], inv[7], inv[2], inv[5], inv[8]], det };
};

// KHR_texture_transform: uv' = T * R * S * uv (mesmo sentido de rotação do three.js)
const uvMatrix = (tr) => {
  const [ox, oy] = tr.getOffset(), [sx, sy] = tr.getScale(), r = tr.getRotation();
  const c = Math.cos(r), s = Math.sin(r);
  return (u, v) => [c * sx * u + s * sy * v + ox, -s * sx * u + c * sy * v + oy];
};

const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(input);
const root = doc.getRoot();
const scene = root.getDefaultScene() || root.listScenes()[0];

// ---------- plano de UV por material ----------
const SLOTS = ['BaseColor', 'Normal', 'MetallicRoughness', 'Occlusion', 'Emissive'];
const plans = new Map();
for (const mat of root.listMaterials()) {
  const slots = SLOTS.map((slot) => ({ slot, tex: mat[`get${slot}Texture`](), info: mat[`get${slot}TextureInfo`]() }))
    .filter((s) => s.tex)
    .map((s) => {
      const tr = s.info.getExtension('KHR_texture_transform');
      const tc = tr && tr.getTexCoord() != null ? tr.getTexCoord() : s.info.getTexCoord();
      const key = tr ? JSON.stringify([tr.getOffset(), tr.getRotation(), tr.getScale()]) : 'I';
      return { ...s, tr, tc, key };
    });
  if (!slots.some((s) => s.tr)) continue;
  // grupos (conjunto de UV de origem + transformação)
  const groups = new Map();
  for (const s of slots) {
    const g = `${s.tc}|${s.key}`;
    if (!groups.has(g)) groups.set(g, { tc: s.tc, tr: s.tr, slots: [] });
    groups.get(g).slots.push(s);
  }
  // em cada conjunto de origem, fica "no lugar" o grupo da cor base; senão o sem transformação; senão o primeiro
  const inPlace = new Map();
  for (const g of groups.values()) {
    const cur = inPlace.get(g.tc);
    const score = (x) => (x.slots.some((s) => s.slot === 'BaseColor') ? 2 : x.tr ? 0 : 1);
    if (!cur || score(g) > score(cur)) inPlace.set(g.tc, g);
  }
  plans.set(mat, { groups: [...groups.values()], inPlace });
}

// quantos conjuntos de UV cada material precisa (para os novos conjuntos serem contíguos)
const uvCount = (prim) => prim.listSemantics().filter((s) => s.startsWith('TEXCOORD_')).length;
for (const [mat, plan] of plans) {
  const prims = root.listMeshes().flatMap((m) => m.listPrimitives()).filter((p) => p.getMaterial() === mat);
  let next = Math.max(...prims.map(uvCount));
  for (const g of plan.groups) g.dst = plan.inPlace.get(g.tc) === g ? g.tc : next++;
  plan.total = next;
}

// ---------- aplicar transformações na geometria ----------
const correction = rotY(ROTATE_Y);
const oldNodes = [...root.listNodes()];
const baked = [];
scene.traverse((node) => {
  const mesh = node.getMesh();
  if (!mesh) return;
  const M = mul(correction, node.getWorldMatrix());
  const { n: N, det } = normalMatrix(M);
  const out = doc.createMesh(mesh.getName());
  for (const src of mesh.listPrimitives()) {
    const prim = doc.createPrimitive().setMode(src.getMode()).setMaterial(src.getMaterial());
    const buffer = src.getAttribute('POSITION').getBuffer();
    const pos = src.getAttribute('POSITION');
    const P = new Float32Array(pos.getCount() * 3);
    for (let i = 0, el = [0, 0, 0]; i < pos.getCount(); i++) {
      pos.getElement(i, el);
      P[i * 3] = M[0] * el[0] + M[4] * el[1] + M[8] * el[2] + M[12];
      P[i * 3 + 1] = M[1] * el[0] + M[5] * el[1] + M[9] * el[2] + M[13];
      P[i * 3 + 2] = M[2] * el[0] + M[6] * el[1] + M[10] * el[2] + M[14];
    }
    prim.setAttribute('POSITION', doc.createAccessor().setType('VEC3').setArray(P).setBuffer(buffer));
    const nor = src.getAttribute('NORMAL');
    if (nor) {
      const A = new Float32Array(nor.getCount() * 3);
      for (let i = 0, el = [0, 0, 0]; i < nor.getCount(); i++) {
        nor.getElement(i, el);
        const x = N[0] * el[0] + N[3] * el[1] + N[6] * el[2];
        const y = N[1] * el[0] + N[4] * el[1] + N[7] * el[2];
        const z = N[2] * el[0] + N[5] * el[1] + N[8] * el[2];
        const l = Math.hypot(x, y, z) || 1;
        A.set([x / l, y / l, z / l], i * 3);
      }
      prim.setAttribute('NORMAL', doc.createAccessor().setType('VEC3').setArray(A).setBuffer(buffer));
    }
    // UVs: copia e aplica o plano de transformação do material
    const plan = plans.get(src.getMaterial());
    const uvSrc = src.listSemantics().filter((s) => s.startsWith('TEXCOORD_'));
    const readUV = (tc) => {
      const a = src.getAttribute(`TEXCOORD_${tc}`) || src.getAttribute('TEXCOORD_0');
      const arr = new Float32Array(a.getCount() * 2);
      for (let i = 0, el = [0, 0]; i < a.getCount(); i++) { a.getElement(i, el); arr[i * 2] = el[0]; arr[i * 2 + 1] = el[1]; }
      return arr;
    };
    const uvOut = new Map(uvSrc.map((s) => [Number(s.split('_')[1]), readUV(Number(s.split('_')[1]))]));
    if (plan) {
      for (let k = uvSrc.length; k < plan.total; k++) uvOut.set(k, readUV(0)); // mantém contíguo
      for (const g of plan.groups) {
        if (!g.tr) { if (g.dst !== g.tc) uvOut.set(g.dst, readUV(g.tc)); continue; }
        const f = uvMatrix(g.tr), base = readUV(g.tc), arr = new Float32Array(base.length);
        for (let i = 0; i < base.length; i += 2) { const [u, v] = f(base[i], base[i + 1]); arr[i] = u; arr[i + 1] = v; }
        uvOut.set(g.dst, arr);
      }
    }
    for (const [tc, arr] of uvOut) prim.setAttribute(`TEXCOORD_${tc}`, doc.createAccessor().setType('VEC2').setArray(arr).setBuffer(buffer));
    for (const sem of src.listSemantics()) {
      if (sem === 'POSITION' || sem === 'NORMAL' || sem.startsWith('TEXCOORD_')) continue;
      if (sem === 'TANGENT') continue; // recalculada pelo visualizador
      prim.setAttribute(sem, src.getAttribute(sem).clone());
    }
    // índices; escala negativa → inverte a ordem dos triângulos
    const idx = src.getIndices();
    const I = idx ? Uint32Array.from(idx.getArray()) : Uint32Array.from({ length: pos.getCount() }, (_, i) => i);
    if (det < 0) for (let i = 0; i < I.length; i += 3) [I[i + 1], I[i + 2]] = [I[i + 2], I[i + 1]];
    const maxIndex = I.reduce((m, v) => (v > m ? v : m), 0);
    prim.setIndices(doc.createAccessor().setType('SCALAR').setArray(maxIndex < 65535 ? Uint16Array.from(I) : I).setBuffer(buffer));
    out.addPrimitive(prim);
  }
  baked.push(doc.createNode(node.getName()).setMesh(out));
});

// substitui a cena pela versão "assada"
for (const child of scene.listChildren()) scene.removeChild(child);
oldNodes.forEach((n) => n.dispose());
const display = doc.createNode('Display');
baked.forEach((n) => display.addChild(n));
scene.addChild(display);

// materiais: tira o KHR_texture_transform e aponta cada textura para o conjunto de UV certo
for (const [mat, plan] of plans) {
  for (const g of plan.groups) for (const s of g.slots) {
    s.info.setExtension('KHR_texture_transform', null);
    s.info.setTexCoord(g.dst);
  }
}
const stillUsed = root.listMaterials().some((m) => SLOTS.some((s) => m[`get${s}TextureInfo`]()?.getExtension('KHR_texture_transform')));
if (!stillUsed) root.listExtensionsUsed().filter((e) => e.extensionName === 'KHR_texture_transform').forEach((e) => e.dispose());

// só as malhas novas: as antigas ainda estão no documento até o prune
const bakedMeshes = () => baked.map((n) => n.getMesh());

// Malhas densas demais (ex.: melões de 18 mil triângulos cada) caem para ~MAX_TRI.
// Erro máximo de 0,5% do tamanho da própria malha: num melão de 15 cm, menos de 1 mm.
await MeshoptSimplifier.ready;
const simplificacao = { malhas: 0, antes: 0, depois: 0 };
for (const mesh of bakedMeshes()) for (const prim of mesh.listPrimitives()) {
  const tri = prim.getIndices() ? prim.getIndices().getCount() / 3 : 0;
  if (tri <= MAX_TRI) continue;
  weldPrimitive(prim);
  simplifyPrimitive(prim, { simplifier: MeshoptSimplifier, ratio: MAX_TRI / tri, error: SIMPLIFY_ERROR });
  simplificacao.malhas++;
  simplificacao.antes += tri;
  simplificacao.depois += prim.getIndices().getCount() / 3;
}

// origem no centro da base (medidas reais, antes do verso de 1 mm)
const { min, max } = getBounds(scene);
const off = [-(min[0] + max[0]) / 2, -min[1], -(min[2] + max[2]) / 2];
for (const acc of new Set(root.listMeshes().flatMap((m) => m.listPrimitives()).map((p) => p.getAttribute('POSITION')))) {
  const a = acc.getArray();
  for (let i = 0; i < a.length; i += 3) { a[i] += off[0]; a[i + 1] += off[1]; a[i + 2] += off[2]; }
  acc.setArray(a);
}
const dims = { largura_m: +(max[0] - min[0]).toFixed(3), altura_m: +(max[1] - min[1]).toFixed(3), profundidade_m: +(max[2] - min[2]).toFixed(3) };

// Faces "de dois lados" viram geometria real: o Quick Look ignora doubleSided e cada
// renderizador resolve de um jeito as faces coincidentes (ex.: lado de fora impresso e
// lado de dentro preto da caixa no mesmo plano). O verso é duplicado com a ordem invertida
// e recuado 1 mm para trás da própria face — assim ganha sempre a face virada para quem olha.
const VERSO_OFFSET = flag('verso-offset', 0.001);
// Malha fechada com as faces para fora (ex.: os melões) nunca mostra o lado de dentro:
// não precisa de verso, e poupa metade dos triângulos dela.
function closedOutward(prim) {
  const pos = prim.getAttribute('POSITION').getArray(), idx = prim.getIndices().getArray();
  const ids = new Map(), weld = new Uint32Array(pos.length / 3);
  for (let i = 0; i < weld.length; i++) {
    const k = `${Math.round(pos[i * 3] * 1e5)},${Math.round(pos[i * 3 + 1] * 1e5)},${Math.round(pos[i * 3 + 2] * 1e5)}`;
    if (!ids.has(k)) ids.set(k, ids.size);
    weld[i] = ids.get(k);
  }
  const edges = new Map();
  let volume = 0;
  for (let t = 0; t < idx.length; t += 3) {
    const v = [idx[t], idx[t + 1], idx[t + 2]];
    for (let e = 0; e < 3; e++) {
      const a = weld[v[e]], b = weld[v[(e + 1) % 3]];
      if (a === b) continue;
      const k = a < b ? `${a}_${b}` : `${b}_${a}`;
      edges.set(k, (edges.get(k) || 0) + 1);
    }
    const [p, q, r] = v.map((i) => [pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]]);
    volume += p[0] * (q[1] * r[2] - q[2] * r[1]) - p[1] * (q[0] * r[2] - q[2] * r[0]) + p[2] * (q[0] * r[1] - q[1] * r[0]);
  }
  for (const c of edges.values()) if (c !== 2) return false;
  return volume > 0;
}
const doubleSided = NO_VERSO ? [] : root.listMaterials().filter((m) => m.getDoubleSided());
const versoStats = { comVerso: 0, fechadas: 0 };
for (const mesh of bakedMeshes()) for (const prim of mesh.listPrimitives()) {
  if (!doubleSided.includes(prim.getMaterial()) || !prim.getAttribute('NORMAL') || !prim.getIndices()) continue;
  // transparente precisa do verso mesmo fechada: o lado de trás aparece através dela
  if (prim.getMaterial().getAlphaMode() === 'OPAQUE' && closedOutward(prim)) { versoStats.fechadas++; continue; }
  versoStats.comVerso++;
  const n = prim.getAttribute('NORMAL').getArray(), count = n.length / 3;
  for (const sem of prim.listSemantics()) {
    const acc = prim.getAttribute(sem), a = acc.getArray(), dup = new a.constructor(a.length * 2);
    dup.set(a); dup.set(a, a.length);
    if (sem === 'POSITION') for (let i = 0; i < count * 3; i++) dup[a.length + i] += n[i] * VERSO_OFFSET;
    if (sem === 'NORMAL') for (let i = 0; i < count * 3; i++) dup[a.length + i] = -a[i];
    acc.setArray(dup);
  }
  const idx = prim.getIndices().getArray(), I = new Uint32Array(idx.length * 2);
  I.set(idx);
  for (let i = 0; i < idx.length; i += 3) I.set([idx[i] + count, idx[i + 2] + count, idx[i + 1] + count], idx.length + i);
  prim.getIndices().setArray(count * 2 < 65535 ? Uint16Array.from(I) : I);
}
doubleSided.forEach((m) => m.setDoubleSided(false));

// uma mesma imagem usada como cor (sRGB) e como mapa técnico (normal/rugosidade, linear)
// confunde o three.js e o Quick Look: a cor ganha uma cópia própria (bytes diferentes
// para o dedup não juntar de novo)
const COLOR_SLOTS = ['BaseColor', 'Emissive'];
for (const tex of root.listTextures()) {
  const uses = root.listMaterials().flatMap((m) => SLOTS.filter((s) => m[`get${s}Texture`]() === tex).map((s) => ({ m, s })));
  const colorUses = uses.filter((u) => COLOR_SLOTS.includes(u.s));
  if (!colorUses.length || colorUses.length === uses.length) continue;
  const bytes = await sharp(tex.getImage()).jpeg({ quality: 90, mozjpeg: true }).toBuffer();
  const copy = doc.createTexture(`${tex.getName()} (cor)`).setImage(new Uint8Array(bytes)).setMimeType('image/jpeg');
  for (const { m, s } of colorUses) m[`set${s}Texture`](copy);
}

await doc.transform(dedup(), prune());

// texturas: todas opacas → JPEG; lado maior até MAX_TEX (faixas muito largas, como a
// régua de gôndola, até 2×MAX_TEX para o texto não borrar)
for (const tex of root.listTextures()) {
  const img = tex.getImage();
  const meta = await sharp(img).metadata();
  const long = Math.max(meta.width, meta.height), short = Math.min(meta.width, meta.height);
  const soDados = !root.listMaterials().some((m) => COLOR_SLOTS.some((s) => m[`get${s}Texture`]() === tex));
  const base = soDados ? MAX_TEX_DATA : MAX_TEX;
  const limit = long / short >= 6 ? base * 2 : base;
  if (long <= limit && tex.getMimeType() === 'image/jpeg') continue;
  const k = Math.min(1, limit / long);
  if (KEEP_ALPHA && meta.hasAlpha) {
    const st = await sharp(img).stats();
    if (st.channels[3] && st.channels[3].min < 250) {
      if (k < 1 || tex.getMimeType() !== 'image/png') tex.setImage(new Uint8Array(await sharp(img).resize(Math.round(meta.width * k), Math.round(meta.height * k)).png({ compressionLevel: 9, palette: false }).toBuffer())).setMimeType('image/png');
      continue;
    }
  }
  const buf = await sharp(img).resize(Math.round(meta.width * k), Math.round(meta.height * k))
    .flatten({ background: '#ffffff' }).jpeg({ quality: 88, mozjpeg: true }).toBuffer();
  tex.setImage(new Uint8Array(buf)).setMimeType('image/jpeg');
  if (tex.getURI()) tex.setURI(tex.getURI().replace(/\.\w+$/, '.jpg'));
}

await io.write(output, doc);

const texs = [];
for (const t of root.listTextures()) {
  const m = await sharp(t.getImage()).metadata();
  texs.push(`${t.getName()} ${m.width}x${m.height} ${(t.getImage().byteLength / 1024).toFixed(0)}KB ${t.getMimeType()}`);
}
const triangulos = root.listMeshes().flatMap((m) => m.listPrimitives()).reduce((s, p) => s + p.getIndices().getCount() / 3, 0);
console.log(JSON.stringify({ saida: output, tamanho_mb: +(statSync(output).size / 1048576).toFixed(2), dims, triangulos, simplificacao, verso: versoStats, texturas: texs }, null, 2));
