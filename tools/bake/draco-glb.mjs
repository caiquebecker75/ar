// Compressão Draco da geometria (ambiente grande: 900 mil triângulos viram ~10 MB em vez de ~30 MB).
// O model-viewer decodifica com o decodificador oficial do Google (gstatic) e o Scene Viewer do Android lê Draco.
// O modo imersivo (three.js) usa vendor/three/examples/jsm/loaders/DRACOLoader.js com o mesmo decodificador.
//   node tools/bake/draco-glb.mjs entrada.glb saida.glb
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { draco, dedup, prune } from '@gltf-transform/functions';
import draco3d from 'draco3dgltf';
import { statSync } from 'node:fs';
const [inp, out] = process.argv.slice(2);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({
  'draco3d.encoder': await draco3d.createEncoderModule(),
  'draco3d.decoder': await draco3d.createDecoderModule(),
});
const doc = await io.read(inp);
await doc.transform(dedup(), prune(), draco({ method: 'edgebreaker', encodeSpeed: 3, decodeSpeed: 5,
  quantizePosition: 14, quantizeTexcoord: 14, quantizeNormal: 10 }));
await io.write(out, doc);
console.log(JSON.stringify({ saida: out, mb: +(statSync(out).size / 1048576).toFixed(1) }));
