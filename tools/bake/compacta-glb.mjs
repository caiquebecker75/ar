// Compacta GLB de luz assada: simplifica sem mexer nas costuras de UV e (opcional) quantiza.
//   node tools/bake/compacta-glb.mjs entrada.glb saida.glb <razão 0..1, 1 = não simplifica> <erro> [sem-quantizar]
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { simplify, weld, quantize, dedup, prune } from '@gltf-transform/functions';
import { MeshoptSimplifier } from 'meshoptimizer';
import { statSync } from 'node:fs';
const [inp, out, ratio, erro] = process.argv.slice(2);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(inp);
const tri = () => doc.getRoot().listMeshes().flatMap((m) => m.listPrimitives()).reduce((s, p) => s + p.getIndices().getCount() / 3, 0);
const antes = tri();
await MeshoptSimplifier.ready;
// weld só junta vértices idênticos em TODOS os atributos (UV de bake diferente = costura preservada)
if (Number(ratio) < 1) await doc.transform(weld(), simplify({ simplifier: MeshoptSimplifier, ratio: Number(ratio), error: Number(erro), lockBorder: true }));
if (process.argv[6] !== "sem-quantizar") await doc.transform(quantize({ quantizePosition: 14, quantizeTexcoord: 14, quantizeNormal: 10 }));
await doc.transform(dedup(), prune());
await io.write(out, doc);
console.log(JSON.stringify({ saida: out, antes, depois: tri(), mb: +(statSync(out).size / 1048576).toFixed(1) }));
