import { NodeIO, getBounds } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
const io=new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc=await io.read(process.argv[2]);
const scene=doc.getRoot().getDefaultScene()||doc.getRoot().listScenes()[0];
const b=getBounds(scene); console.log('cena', b.min.map(v=>+v.toFixed(2)), b.max.map(v=>+v.toFixed(2)));
scene.traverse(n=>{ if(!n.getMesh())return; const x=getBounds(n); console.log(n.getName(), x.min.map(v=>+v.toFixed(2)), x.max.map(v=>+v.toFixed(2))); });
