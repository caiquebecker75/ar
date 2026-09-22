import { NodeIO, getBounds } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(process.argv[2]);
const scene = doc.getRoot().getDefaultScene() || doc.getRoot().listScenes()[0];
scene.traverse((n) => {
  if (!n.getMesh()) return;
  const b = getBounds(n);
  if (b.min[0] < -0.95 || b.max[0] > 0.95 || b.max[2] > 0.6 || b.min[2] < -0.6 || b.max[1] > 1.5) {
    console.log(n.getName(), 'min', b.min.map(v=>+v.toFixed(2)), 'max', b.max.map(v=>+v.toFixed(2)), 'mats', n.getMesh().listPrimitives().map(p=>p.getMaterial()?.getName()));
  }
});
