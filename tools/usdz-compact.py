"""Compacta o display.usdz gerado pelo tools/usdz.html.

O exportador do three.js grava todas as texturas em PNG e a geometria em texto
(.usda). Aqui as texturas viram JPEG (todas são opacas), a cena é achatada em
binário (.usdc) e o pacote é refeito com o usdzip do macOS, no modo ARKit.

Uso: python3 tools/usdz-compact.py <pasta-do-display>/display.usdz
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from PIL import Image

src = os.path.abspath(sys.argv[1])
work = tempfile.mkdtemp(prefix="usdz-")
zipfile.ZipFile(src).extractall(work)

before = os.path.getsize(src)
tex_dir = os.path.join(work, "textures")
for name in sorted(os.listdir(tex_dir)):
    if not name.lower().endswith(".png"):
        continue
    png = os.path.join(tex_dir, name)
    Image.open(png).convert("RGB").save(png[:-4] + ".jpg", quality=88, optimize=True)
    os.remove(png)

# mapas técnicos (normal, rugosidade...) têm de ser lidos como dados, não como cor
DATA_TEXTURE = re.compile(
    r'(def Shader "Texture_[^"]*_(?:normal|roughness|metallic|occlusion|clearcoat|clearcoatRoughness)"\s*\{)(.*?)(\n\s*\})',
    re.S)

for dirpath, _, files in os.walk(work):
    for name in files:
        if name.endswith(".usda"):
            path = os.path.join(dirpath, name)
            with open(path, encoding="utf-8") as f:
                text = f.read().replace(".png@", ".jpg@")
            text = DATA_TEXTURE.sub(
                lambda m: m.group(1) + m.group(2).replace('sourceColorSpace = "sRGB"', 'sourceColorSpace = "raw"') + m.group(3),
                text)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)

# modo ARKit: achata a cena em um único .usdc binário e embute as texturas
out = src[:-5] + ".tmp.usdz"  # o usdzip exige a extensão .usdz
subprocess.run(["usdzip", "--arkitAsset", "model.usda", out], cwd=work, check=True)
os.replace(out, src)
shutil.rmtree(work)
print(f"{before / 1048576:.1f} MB -> {os.path.getsize(src) / 1048576:.1f} MB  ({src})")
