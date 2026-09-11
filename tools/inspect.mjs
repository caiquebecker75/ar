// Mostra material → texturas (com texCoord e KHR_texture_transform) e a hierarquia de nós.
import { NodeIO } from '@gltf-transform/core';
import { ALL_EXTENSIONS } from '@gltf-transform/extensions';
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS);
const doc = await io.read(process.argv[2]);
const root = doc.getRoot();
const tname = (t) => t ? t.getName() : '-';
for (const m of root.listMaterials()) {
  console.log(`\nMATERIAL "${m.getName()}" base=${m.getBaseColorFactor().map(v=>v.toFixed(2))} metal=${m.getMetallicFactor()} rough=${m.getRoughnessFactor()} ds=${m.getDoubleSided()}`);
  for (const slot of ['BaseColor','Normal','MetallicRoughness','Occlusion','Emissive']) {
    const tex = m[`get${slot}Texture`]();
    if (!tex) continue;
    const info = m[`get${slot}TextureInfo`]();
    const tr = info.getExtension('KHR_texture_transform');
    console.log(`  ${slot}: ${tname(tex)} texCoord=${info.getTexCoord()} wrap=${info.getWrapS()}/${info.getWrapT()}` + (tr ? ` T{off=${tr.getOffset()} rot=${tr.getRotation()} scale=${tr.getScale()} tc=${tr.getTexCoord()}}` : ''));
  }
  for (const [k,e] of Object.entries(m.listExtensions())) console.log('  ext', e.extensionName);
}
console.log('\nNODES');
const walk = (n, d) => {
  const mesh = n.getMesh();
  console.log(`${'  '.repeat(d)}${n.getName()} T=${n.getTranslation().map(v=>v.toFixed(3))} R=${n.getRotation().map(v=>v.toFixed(3))} S=${n.getScale().map(v=>v.toFixed(3))}` + (mesh ? ` mesh=${mesh.getName()} mats=[${mesh.listPrimitives().map(p=>p.getMaterial()?.getName()).join(', ')}]` : ''));
  n.listChildren().forEach(c => walk(c, d+1));
};
root.listScenes()[0].listChildren().forEach(n => walk(n, 0));
