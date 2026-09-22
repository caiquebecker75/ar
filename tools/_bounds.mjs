import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
import { getBounds } from '@gltf-transform/core';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(process.argv[2]);
const scene = doc.getRoot().getDefaultScene() || doc.getRoot().listScenes()[0];
const lista = [];
scene.traverse((n) => {
  if (!n.getMesh()) return;
  const b = getBounds(n);
  lista.push({ nome: n.getName(), L: +(b.max[0]-b.min[0]).toFixed(2), A: +(b.max[1]-b.min[1]).toFixed(2), P: +(b.max[2]-b.min[2]).toFixed(2), min: b.min.map(v=>+v.toFixed(2)), max: b.max.map(v=>+v.toFixed(2)) });
});
lista.sort((a,b)=> (b.L+b.A+b.P)-(a.L+a.A+a.P));
console.log(lista.slice(0,12));
console.log("cena", getBounds(scene));
