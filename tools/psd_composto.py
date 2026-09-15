# Converte a imagem composta de um PSD/PSB (RGB ou CMYK, 8 bits) em PNG, lendo só as linhas necessárias.
# Serve quando o sips falha (CMYK com canal extra) ou achata o transparente em preto.
#
#   PY=$(ls /Applications/Blender.app/Contents/Resources/*/python/bin/python3.* | head -1)   # tem numpy
#   $PY tools/psd_composto.py arte.psd saida.png [lado_max=4096] [offset_do_psd_embutido]
#
# O offset permite ler um PSD/PSB embutido (objeto inteligente) dentro de outro arquivo.
# CMYK vira RGB pela conta simples (sem perfil ICC): as cores podem sair um pouco diferentes do Photoshop.
import struct, sys, zlib
import numpy as np

def packbits(lin, w):
    out = bytearray(); i = 0; n = len(lin)
    while i < n and len(out) < w:
        b = lin[i]; i += 1
        if b < 128: out += lin[i:i + b + 1]; i += b + 1
        elif b > 128: out += lin[i:i + 1] * (257 - b); i += 1
    return bytes(out[:w]).ljust(w, b'\xff')

def ler(f, base, maxl):
    assert f[base:base + 4] == b'8BPS', 'não é PSD'
    ver, ch, h, w, depth, mode = struct.unpack('>H6xHIIHH', f[base + 4:base + 26])
    assert depth == 8 and mode in (3, 4), f'só RGB/CMYK 8 bits (depth={depth} mode={mode})'
    o = base + 26
    for _ in range(2):
        n = struct.unpack('>I', f[o:o + 4])[0]; o += 4 + n
    L = 8 if ver == 2 else 4
    n = struct.unpack('>Q' if ver == 2 else '>I', f[o:o + L])[0]; o += L + n
    comp = struct.unpack('>H', f[o:o + 2])[0]; o += 2
    passo = max(1, -(-max(w, h) // maxl)); ys = range(0, h, passo); nw = len(range(0, w, passo))
    cores = 3 if mode == 3 else 4
    usar = min(ch, cores + 1)
    if comp == 1:
        tam = 4 if ver == 2 else 2
        cont = np.frombuffer(f[o:o + ch * h * tam], dtype='>u4' if tam == 4 else '>u2').astype(np.int64); o += ch * h * tam
        ini = o + np.concatenate([[0], np.cumsum(cont)])
        linha = lambda c, y: np.frombuffer(packbits(f[ini[c * h + y]:ini[c * h + y + 1]], w), np.uint8)
    elif comp == 0:
        linha = lambda c, y: np.frombuffer(f[o + c * h * w + y * w:o + c * h * w + (y + 1) * w], np.uint8)
    else:
        raise SystemExit(f'compressão {comp} não suportada')
    planos = [np.stack([linha(c, y)[::passo][:nw] for y in ys]).astype(np.float32) for c in range(usar)]
    if mode == 4:   # no PSD o CMYK vem invertido: 255 = sem tinta
        k = planos[3] / 255
        rgb = [planos[i] * k for i in range(3)]
    else:
        rgb = planos[:3]
    img = np.stack(rgb, -1)
    alfa = planos[cores] if usar > cores else None
    if alfa is not None and alfa.min() < 250: img = np.concatenate([img, alfa[..., None]], -1)
    dpi = None; p = base + 26; n = struct.unpack('>I', f[p:p + 4])[0]; p += 4 + n; n = struct.unpack('>I', f[p:p + 4])[0]; p += 4; fim = p + n
    while p < fim - 12 and f[p:p + 4] == b'8BIM':
        rid = struct.unpack('>H', f[p + 4:p + 6])[0]; nl = f[p + 6]; q = p + 7 + nl + ((nl + 1) % 2); sz = struct.unpack('>I', f[q:q + 4])[0]
        if rid == 0x03ED: dpi = struct.unpack('>I', f[q + 4:q + 8])[0] / 65536
        p = q + 4 + sz + (sz & 1)
    return np.clip(img, 0, 255).astype(np.uint8), (w, h, dpi, mode, ch)

def png(caminho, img):
    h, w, c = img.shape
    raw = np.concatenate([np.zeros((h, 1), np.uint8), img.reshape(h, w * c)], 1).tobytes()
    def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
    open(caminho, 'wb').write(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6 if c == 4 else 2, 0, 0, 0))
                              + chunk(b'IDAT', zlib.compress(raw, 6)) + chunk(b'IEND', b''))

f = open(sys.argv[1], 'rb').read()
img, (w, h, dpi, mode, ch) = ler(f, int(sys.argv[4]) if len(sys.argv) > 4 else 0, int(sys.argv[3]) if len(sys.argv) > 3 else 4096)
png(sys.argv[2], img)
print(f'{sys.argv[2]}: original {w}x{h} dpi={dpi} modo={"CMYK" if mode == 4 else "RGB"} canais={ch}',
      f'({w / dpi * 2.54:.1f} × {h / dpi * 2.54:.1f} cm)' if dpi else '', f'→ {img.shape[1]}x{img.shape[0]} {"com alfa" if img.shape[2] == 4 else ""}')
