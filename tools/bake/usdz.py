# GLB com verso (saída do prepare-glb sem --no-verso) -> USDZ pelo exportador nativo do Blender.
# Binário, JPEG mantido, sem normais (material só emissivo não usa). Para cenas grandes o usdz.html
# (three.js no navegador) não aguenta: grava tudo em texto e PNG.
#   blender -b --python tools/bake/usdz.py -- --glb=_usdz.glb --usdz=display.usdz
import bpy, os, sys
_args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
_opt = lambda k: next(a.split("=", 1)[1] for a in _args if a.startswith(f"--{k}="))
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.abspath(_opt("glb")))
for m in bpy.data.materials:
    if m.use_nodes: m.use_backface_culling = True   # o verso já é geometria real

saida = os.path.abspath(_opt("usdz"))
import tempfile, shutil
tmp = tempfile.mkdtemp(prefix="usdz-bake-")
usdc = os.path.join(tmp, "modelo.usdc")
bpy.ops.wm.usd_export(filepath=usdc, selected_objects_only=False, export_materials=True,
    generate_preview_surface=True, export_textures_mode='NEW', convert_orientation=True,
    export_global_forward_selection='NEGATIVE_Z', export_global_up_selection='Y',
    export_animation=False, export_uvmaps=True, export_normals=False)

# Ajustes que o exportador do Blender não faz:
# - sem brilho especular (material só emissivo; o brilho padrão do USD estoura em branco nas superfícies de lado)
# - acrílico com transparência (o exportador grava opacidade 1)
from pxr import Usd, UsdShade, UsdUtils, Sdf
st = Usd.Stage.Open(usdc)
for prim in st.Traverse():
    sh = UsdShade.Shader(prim)
    if not sh or sh.GetIdAttr().Get() != "UsdPreviewSurface": continue
    sh.CreateInput("useSpecularWorkflow", Sdf.ValueTypeNames.Int).Set(1)
    sh.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set((0.0, 0.0, 0.0))
    sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(1.0)
    if "ACRILICO" in str(prim.GetPath()):
        sh.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(0.22)
        sh.CreateInput("specularColor", Sdf.ValueTypeNames.Color3f).Set((0.3, 0.3, 0.3))
        sh.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.1)
st.GetRootLayer().Save()
if os.path.exists(saida): os.remove(saida)
ok = UsdUtils.CreateNewARKitUsdzPackage(Sdf.AssetPath(usdc), saida)
shutil.rmtree(tmp)
print("USDZ", ok, os.path.getsize(saida) // 1048576, "MB")
