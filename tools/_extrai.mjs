// tira as texturas assadas de um GLB de volta para a pasta bake/
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { writeFileSync } from 'node:fs';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(process.argv[2]);
const dir = process.argv[3];
for (const t of doc.getRoot().listTextures()) {
  const nome = t.getName();
  const ext = t.getMimeType() === 'image/png' ? 'png' : 'jpg';
  writeFileSync(`${dir}/${nome}.${ext}`, Buffer.from(t.getImage()));
  console.log(nome + '.' + ext, t.getImage().byteLength);
}
