// Gera a versão IMERSIVA de um ambiente (ex.: stand): o modelo já preparado ganha piso e
// cúpula virtuais em volta, com as faces para dentro. Em AR, quem está dentro da cúpula deixa
// de ver o lugar real e vê só o stand (iPhone Quick Look e Android Scene Viewer).
//
//   node tools/imersivo-glb.mjs <pasta>/display.glb <pasta>/imersivo.glb [--raio=15] [--recuo=4]
//
// O AR põe o centro da caixa do modelo à frente de quem abre. A cúpula fica centrada ali e o
// stand recua (--recuo, em metros; padrão: metade da profundidade + 1,5 m): a pessoa começa
// do lado de fora, de frente para a entrada.
//
// Piso e cúpula usam só cor emissiva (base preta): a luz do lugar real não muda o "estúdio".
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { getBounds } from '@gltf-transform/functions';
import sharp from 'sharp';
import { statSync } from 'node:fs';

const [input, output] = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const flag = (name, def) => {
  const hit = process.argv.find((a) => a.startsWith(`--${name}=`));
  return hit ? Number(hit.split('=')[1]) : def;
};
if (!input || !output) {
  console.error('uso: node tools/imersivo-glb.mjs <pasta>/display.glb <pasta>/imersivo.glb [--raio=15] [--recuo=metros]');
  process.exit(1);
}
const R = flag('raio', 15);
const Y0 = -0.02; // piso virtual 2 cm abaixo do piso do stand: sem briga de profundidade

const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(input);
const root = doc.getRoot();
const scene = root.getDefaultScene() || root.listScenes()[0];
const buffer = root.listBuffers()[0];

// ---------- stand recuado ----------
const { min, max } = getBounds(scene);
const RECUO = flag('recuo', (max[2] - min[2]) / 2 + 1.5);
const meiaLargura = (max[0] - min[0]) / 2, meiaProf = (max[2] - min[2]) / 2;
const stand = doc.createNode('Stand').setTranslation([0, 0, -RECUO]);
for (const child of scene.listChildren()) {
  scene.removeChild(child);
  stand.addChild(child);
}
scene.addChild(stand);

// ---------- texturas (gradientes) ----------
const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const mix = (a, b, t) => a.map((v, i) => v + (b[i] - v) * t);
const smooth = (e0, e1, x) => {
  const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
};
const PISO_CENTRO = hex('#B4B5B0'), HORIZONTE = hex('#DCDDD8'), TOPO = hex('#F1F1EC');

async function jpeg(w, h, cor) {
  const px = Buffer.alloc(w * h * 3);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const c = cor(x / (w - 1), y / (h - 1)), ruido = (Math.random() - 0.5) * 2; // evita faixas no gradiente
    for (let k = 0; k < 3; k++) px[(y * w + x) * 3 + k] = Math.max(0, Math.min(255, Math.round(c[k] + ruido)));
  }
  return new Uint8Array(await sharp(px, { raw: { width: w, height: h, channels: 3 } }).jpeg({ quality: 92, mozjpeg: true }).toBuffer());
}

// piso: claro no horizonte (emenda com a cúpula), um pouco mais escuro perto do stand,
// com uma sombra suave em volta da área do stand
const texPiso = await jpeg(1024, 1024, (u, v) => {
  const X = (u - 0.5) * 2 * R, Z = (v - 0.5) * 2 * R;
  const base = mix(PISO_CENTRO, HORIZONTE, smooth(0.2, 1, Math.hypot(X, Z) / R));
  const fora = Math.hypot(Math.max(0, Math.abs(X) - meiaLargura), Math.max(0, Math.abs(Z + RECUO) - meiaProf));
  return base.map((c) => c * (1 - 0.22 * (1 - smooth(0, 1.6, fora))));
});
// cúpula: v = 0 no topo, 1 no horizonte
const texCupula = await jpeg(8, 512, (u, v) => mix(TOPO, HORIZONTE, smooth(0.05, 1, v)));

// ---------- geometria ----------
function malha(nome, P, N, UV, I, tex) {
  const acc = (type, arr) => doc.createAccessor().setType(type).setArray(arr).setBuffer(buffer);
  const mat = doc.createMaterial(nome)
    .setBaseColorFactor([0, 0, 0, 1]).setMetallicFactor(0).setRoughnessFactor(1)
    .setEmissiveFactor([1, 1, 1])
    .setEmissiveTexture(doc.createTexture(nome).setImage(tex).setMimeType('image/jpeg'));
  const prim = doc.createPrimitive().setMaterial(mat)
    .setAttribute('POSITION', acc('VEC3', new Float32Array(P)))
    .setAttribute('NORMAL', acc('VEC3', new Float32Array(N)))
    .setAttribute('TEXCOORD_0', acc('VEC2', new Float32Array(UV)))
    .setIndices(acc('SCALAR', new Uint16Array(I)));
  scene.addChild(doc.createNode(nome).setMesh(doc.createMesh(nome).addPrimitive(prim)));
}
// triângulo com a frente virada para `dir(centroide)` (faces de um lado só: o Quick Look não desenha o verso)
function tri(P, I, a, b, c, dir) {
  const p = (i) => [P[i * 3], P[i * 3 + 1], P[i * 3 + 2]];
  const [pa, pb, pc] = [p(a), p(b), p(c)];
  const e1 = pb.map((x, k) => x - pa[k]), e2 = pc.map((x, k) => x - pa[k]);
  const n = [e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2], e1[0] * e2[1] - e1[1] * e2[0]];
  const d = dir(pa.map((x, k) => (x + pb[k] + pc[k]) / 3));
  I.push(...(n[0] * d[0] + n[1] * d[1] + n[2] * d[2] >= 0 ? [a, b, c] : [a, c, b]));
}

// cúpula (meia esfera que desce um pouco abaixo do piso, faces para dentro)
{
  const LAT = 24, LON = 64, TMAX = Math.PI / 2 + 0.03;
  const P = [], N = [], UV = [], I = [];
  for (let i = 0; i <= LAT; i++) {
    const t = (TMAX * i) / LAT;
    for (let j = 0; j <= LON; j++) {
      const f = (2 * Math.PI * j) / LON;
      const s = [Math.sin(t) * Math.cos(f), Math.cos(t), Math.sin(t) * Math.sin(f)];
      P.push(R * s[0], R * s[1] + Y0, R * s[2]);
      N.push(-s[0], -s[1], -s[2]);
      UV.push(j / LON, Math.min(1, t / (Math.PI / 2)));
    }
  }
  const paraDentro = (c) => [-c[0], -(c[1] - Y0), -c[2]];
  for (let i = 0; i < LAT; i++) for (let j = 0; j < LON; j++) {
    const a = i * (LON + 1) + j, b = a + 1, c = a + LON + 1, d = c + 1;
    if (i > 0) tri(P, I, a, c, b, paraDentro); // no polo, a e b são o mesmo ponto
    tri(P, I, b, c, d, paraDentro);
  }
  malha('Ambiente cúpula', P, N, UV, I, texCupula);
}

// piso (disco)
{
  const SEG = 96, P = [0, Y0, 0], N = [0, 1, 0], UV = [0.5, 0.5], I = [];
  for (let k = 0; k < SEG; k++) {
    const f = (2 * Math.PI * k) / SEG, X = R * Math.cos(f), Z = R * Math.sin(f);
    P.push(X, Y0, Z); N.push(0, 1, 0); UV.push(X / (2 * R) + 0.5, Z / (2 * R) + 0.5);
  }
  for (let k = 0; k < SEG; k++) tri(P, I, 0, 1 + k, 1 + ((k + 1) % SEG), () => [0, 1, 0]);
  malha('Ambiente piso', P, N, UV, I, texPiso);
}

await io.write(output, doc);
const b = getBounds(scene);
console.log(JSON.stringify({
  saida: output,
  tamanho_mb: +(statSync(output).size / 1048576).toFixed(2),
  raio_m: R,
  recuo_m: +RECUO.toFixed(2),
  caixa_m: b.min.map((v, i) => +(b.max[i] - v).toFixed(2)),
}));
