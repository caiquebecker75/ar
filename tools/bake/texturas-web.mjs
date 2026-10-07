// Limita as texturas do GLB da página para caber na memória do Safari do iPhone.
// Cada textura 4096 ocupa ~85 MB de memória de vídeo (com mipmaps): 17 atlas do stand Alltak passavam de 1,4 GB
// e o iOS derrubava a aba ("Um problema ocorreu repetidamente"). Cor em 2048, rugosidade em 512.
//   node tools/bake/texturas-web.mjs entrada.glb saida.glb [lado-cor=2048] [lado-rug=512]
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import sharp from 'sharp';
import { statSync } from 'node:fs';
const [inp, out, ladoCor = '2048', ladoRug = '512'] = process.argv.slice(2);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(inp);
let mem = 0;
for (const t of doc.getRoot().listTextures()) {
  const rug = /rug/i.test(t.getName() || '') || doc.getRoot().listMaterials().some((m) => m.getMetallicRoughnessTexture() === t);
  const lado = Number(rug ? ladoRug : ladoCor);
  const img = sharp(Buffer.from(t.getImage())); const meta = await img.metadata();
  const w = Math.min(meta.width, lado), h = Math.min(meta.height, lado);
  if (w < meta.width || h < meta.height) {
    const png = t.getMimeType() === 'image/png';
    const r = img.resize({ width: w, height: h, fit: 'fill' });
    t.setImage(new Uint8Array(await (png ? r.png({ palette: true, quality: 92, effort: 8 }) : r.jpeg({ quality: 88, mozjpeg: true })).toBuffer()));
  }
  mem += w * h * 4 * 4 / 3;
}
await io.write(out, doc);
console.log(JSON.stringify({ saida: out, mb: +(statSync(out).size / 1048576).toFixed(1), memoria_textura_mb: Math.round(mem / 1048576) }));
