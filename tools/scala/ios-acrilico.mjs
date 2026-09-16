// Variante para o iPhone: o Quick Look não entende transmissão, então o acrílico vira superfície
// quase invisível (opacidade 6%), lisa, para manter o reflexo sem véu sobre a arte.
//   node tools/scala/ios-acrilico.mjs entrada-pre.glb saida-ios-pre.glb
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(process.argv[2]);
for (const m of doc.getRoot().listMaterials()) if (/ACRILICO/.test(m.getName())) {
  for (const e of m.listExtensions()) m.setExtension(e.extensionName, null);
  m.setBaseColorFactor([1, 1, 1, 0.06]).setAlphaMode('BLEND').setRoughnessFactor(0.05).setMetallicFactor(0);
}
await io.write(process.argv[3], doc);
