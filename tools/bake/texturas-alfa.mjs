// Texturas com transparência (folhas assadas com recorte) ficam em PNG RGBA 4096 de ~33 MB cada.
// Reduz para PNG com paleta (alfa preservado) e lado máximo N: ~2 a 3 MB, sem franja no recorte.
//   node tools/bake/texturas-alfa.mjs entrada.glb saida.glb [2048]
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import sharp from 'sharp';
import { statSync } from 'node:fs';
const [inp, out, ladoArg] = process.argv.slice(2);
const LADO = Number(ladoArg || 2048);
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(inp);
for (const t of doc.getRoot().listTextures()) {
  if (t.getMimeType() !== 'image/png') continue;
  const antes = t.getImage().byteLength;
  const img = sharp(Buffer.from(t.getImage()));
  const m = await img.metadata();
  const buf = await img.resize({ width: Math.min(m.width, LADO), height: Math.min(m.height, LADO), fit: 'fill' })
    .png({ palette: true, quality: 92, effort: 8, colours: 256, dither: 0.6 }).toBuffer();
  t.setImage(new Uint8Array(buf));
  console.log(t.getName(), `${m.width}px ${Math.round(antes / 1024)}KB -> ${Math.min(m.width, LADO)}px ${Math.round(buf.length / 1024)}KB`);
}
await io.write(out, doc);
console.log(JSON.stringify({ saida: out, mb: +(statSync(out).size / 1048576).toFixed(1) }));
