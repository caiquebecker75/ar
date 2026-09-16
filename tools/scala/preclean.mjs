// Limpeza dos GLB do display Scala Flow antes do prepare-glb, SEM mudar a forma da peça:
// - acrílicos, painéis de arte e parafusos vinham com a mesma face repetida várias vezes: remove só as
//   repetições exatas (mesmos 3 pontos, mesma ordem), sem fundir vértices nem simplificar (normais e UV intactos);
// - material do acrílico: transparente, liso e incolor (reflete o HDR como no render do cliente).
// Depois: prepare-glb com --no-verso --keep-alpha --max-tri=1000000 (o verso de 1 mm cobria a arte).
//   node tools/scala/preclean.mjs entrada.glb saida.glb
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS, KHRMaterialsTransmission, KHRMaterialsIOR } from '@gltf-transform/extensions';
import { compactPrimitive, prune, getBounds } from '@gltf-transform/functions';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(process.argv[2]);
const before = getBounds(doc.getRoot().listScenes()[0]);
let tA = 0, tB = 0;
for (const n of doc.getRoot().listNodes()) { const m = n.getMesh(); if (!m) continue;
  for (const p of m.listPrimitives()) {
    const name = p.getMaterial()?.getName() || ''; const t0 = p.getIndices().getCount() / 3; tA += t0;
    // duplicata = mesmos 3 pontos na mesma ordem (comparando posição, sem fundir vértices: normais e UV ficam intactos)
    const dedupe = () => {
      const pos = p.getAttribute('POSITION'), idx = p.getIndices(), arr = idx.getArray(), seen = new Set(), out = [], el = [0, 0, 0];
      const key = (v) => { pos.getElement(v, el); return `${Math.round(el[0] * 1e5)},${Math.round(el[1] * 1e5)},${Math.round(el[2] * 1e5)}`; };
      for (let i = 0; i < arr.length; i += 3) {
        const k3 = [key(arr[i]), key(arr[i + 1]), key(arr[i + 2])];
        if (k3[0] === k3[1] || k3[1] === k3[2] || k3[0] === k3[2]) continue;
        const r = k3.indexOf([...k3].sort()[0]), k = [k3[r], k3[(r + 1) % 3], k3[(r + 2) % 3]].join('|');
        if (seen.has(k)) continue; seen.add(k); out.push(arr[i], arr[i + 1], arr[i + 2]);
      }
      idx.setArray(new Uint32Array(out)); compactPrimitive(p); return out.length / 3;
    };
    if (/ACRILICO/.test(name) || (t0 > 20000 && !/BISNAGA|Material\.001/.test(name))) dedupe();
    else if (/^Bolt/i.test(n.getName()) || /Material\.002/.test(name)) dedupe();
    tB += p.getIndices().getCount() / 3;
  }
}
for (const m of doc.getRoot().listMaterials()) if (/ACRILICO/.test(m.getName())) {
  // acrílico cristal: transmissão física (refrata e reflete o ambiente), IOR do PMMA; sem tingir a peça
  for (const e of m.listExtensions()) m.setExtension(e.extensionName, null);
  m.setBaseColorFactor([1, 1, 1, 1]).setAlphaMode('OPAQUE').setRoughnessFactor(0.02).setMetallicFactor(0);
  const tr = doc.createExtension(KHRMaterialsTransmission).createTransmission().setTransmissionFactor(1);
  const ior = doc.createExtension(KHRMaterialsIOR).createIOR().setIOR(1.49);
  m.setExtension('KHR_materials_transmission', tr).setExtension('KHR_materials_ior', ior);
}
await doc.transform(prune());
const after = getBounds(doc.getRoot().listScenes()[0]);
const diff = Math.max(...[0, 1, 2].flatMap((i) => [Math.abs(before.min[i] - after.min[i]), Math.abs(before.max[i] - after.max[i])]));
await io.write(process.argv[3], doc);
console.log(JSON.stringify({ triangulos: [Math.round(tA), Math.round(tB)], diferenca_caixa_mm: +(diff * 1000).toFixed(2) }));
