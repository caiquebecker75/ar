# Exporta um ambiente grande (ex.: stand) do Blender para GLB leve: blender -b arquivo.blend --python tools/blender-export-ambiente.py  → raw.glb ao lado do .blend
import bpy
sc=bpy.context.scene
dg=bpy.context.evaluated_depsgraph_get()
# 1) sem subdivisão nem displace (relevo do couro fica no mapa de bump)
for o in sc.objects:
    for m in o.modifiers:
        if m.type=='SUBSURF': m.levels=0; m.render_levels=0
        if m.type=='DISPLACE': m.show_viewport=False; m.show_render=False
dg=bpy.context.evaluated_depsgraph_get(); dg.update()
# 2) malhas ainda densas ganham Decimate até ~6 mil triângulos
for o in sc.objects:
    if o.type!='MESH' or not o.visible_get(): continue
    ev=o.evaluated_get(dg); me=ev.to_mesh()
    tri=sum(len(p.vertices)-2 for p in me.polygons); ev.to_mesh_clear()
    if tri>6000:
        d=o.modifiers.new("AR_decimate",'DECIMATE'); d.ratio=max(0.05, 6000/tri)
        print(f"decimate {o.name} {tri} -> ~{int(tri*d.ratio)}")
# 3) texturas gigantes -> máx 4096
for img in bpy.data.images:
    if img.size[0]==0: continue
    w,h=img.size; k=4096/max(w,h)
    if k<1: img.scale(int(w*k),int(h*k))
bpy.ops.export_scene.gltf(filepath=bpy.path.abspath("//raw.glb"), export_format='GLB', use_visible=True, use_renderable=True,
    export_apply=True, export_cameras=False, export_lights=False, export_yup=True, export_image_format='AUTO')
print("EXPORT OK")
