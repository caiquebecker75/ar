# Recupera a arte plana de um banner a partir de um render (a peça é um quadrilátero sobre fundo branco).
#   $PY tools/semp/desentortar.py render.png|render.bmp saida.png largura_px altura_px   (PNG com filtro Paeth é lento: converta antes com sips -s format bmp)
import struct, sys, zlib
import numpy as np
def ler_png(c):
    d = open(c, 'rb').read(); o = 8; idat = b''
    while o < len(d):
        n, t = struct.unpack('>I4s', d[o:o + 8]); b = d[o + 8:o + 8 + n]; o += 12 + n
        if t == b'IHDR': w, h, bd, ct = struct.unpack('>IIBB', b[:10])
        elif t == b'IDAT': idat += b
    ch = {2: 3, 6: 4}[ct]; raw = zlib.decompress(idat); img = np.zeros((h, w, ch), np.uint8); st = w * ch + 1
    prev = np.zeros(w * ch, np.int32)
    for y in range(h):
        f = raw[y * st]; lin = np.frombuffer(raw[y * st + 1:(y + 1) * st], np.uint8).astype(np.int32)
        if f == 0: cur = lin
        elif f == 2: cur = (lin + prev) & 255
        else:   # filtros 1, 3, 4 precisam de laço por pixel
            cur = np.zeros_like(lin)
            for x in range(w * ch):
                a = cur[x - ch] if x >= ch else 0; b_ = prev[x]; c_ = prev[x - ch] if x >= ch else 0
                if f == 1: cur[x] = (lin[x] + a) & 255
                elif f == 3: cur[x] = (lin[x] + (a + b_) // 2) & 255
                else:
                    p = a + b_ - c_; pa, pb, pc = abs(p - a), abs(p - b_), abs(p - c_)
                    cur[x] = (lin[x] + (a if pa <= pb and pa <= pc else b_ if pb <= pc else c_)) & 255
        img[y] = cur.reshape(w, ch); prev = cur
    return img
src, dst, W, H = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
def ler_bmp(c):   # sips -s format bmp: 24/32 bits, linhas de baixo para cima, BGR
    d = open(c, 'rb').read(); off = struct.unpack('<I', d[10:14])[0]; w, h = struct.unpack('<ii', d[18:26]); bpp = struct.unpack('<H', d[28:30])[0]
    ch = bpp // 8; st = ((w * ch + 3) // 4) * 4; a = np.frombuffer(d[off:off + st * abs(h)], np.uint8).reshape(abs(h), st)[:, :w * ch].reshape(abs(h), w, ch)
    a = a[::-1] if h > 0 else a
    return a[..., [2, 1, 0]]
img = (ler_bmp(src) if src.lower().endswith('.bmp') else ler_png(src)).astype(np.float32); h, w = img.shape[:2]
lum = img[..., :3].mean(-1); m = lum < 235
for _ in range(4):   # tira os cabos finos: só fica o que tem vizinho dos quatro lados
    m = m & np.roll(m, 3, 0) & np.roll(m, -3, 0) & np.roll(m, 3, 1) & np.roll(m, -3, 1)
ys, xs = np.nonzero(m)
tl = (xs[np.argmin(xs + ys)], ys[np.argmin(xs + ys)]); br = (xs[np.argmax(xs + ys)], ys[np.argmax(xs + ys)])
tr = (xs[np.argmax(xs - ys)], ys[np.argmax(xs - ys)]); bl = (xs[np.argmin(xs - ys)], ys[np.argmin(xs - ys)])
print('cantos', tl, tr, br, bl)
A = []; B = []
for (u, v), (x, y) in zip([(0, 0), (W, 0), (W, H), (0, H)], [tl, tr, br, bl]):
    A += [[u, v, 1, 0, 0, 0, -u * x, -v * x], [0, 0, 0, u, v, 1, -u * y, -v * y]]; B += [x, y]
hm = np.append(np.linalg.solve(np.array(A, float), np.array(B, float)), 1).reshape(3, 3)
uu, vv = np.meshgrid(np.arange(W) + .5, np.arange(H) + .5)
den = hm[2, 0] * uu + hm[2, 1] * vv + 1
sx = (hm[0, 0] * uu + hm[0, 1] * vv + hm[0, 2]) / den; sy = (hm[1, 0] * uu + hm[1, 1] * vv + hm[1, 2]) / den
x0 = np.clip(np.floor(sx).astype(int), 0, w - 2); y0 = np.clip(np.floor(sy).astype(int), 0, h - 2); fx = (sx - x0)[..., None]; fy = (sy - y0)[..., None]
out = img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x0 + 1] * fx * (1 - fy) + img[y0 + 1, x0] * (1 - fx) * fy + img[y0 + 1, x0 + 1] * fx * fy
out = np.clip(out[..., :3], 0, 255).astype(np.uint8)
raw = np.concatenate([np.zeros((H, 1), np.uint8), out.reshape(H, W * 3)], 1).tobytes()
ck = lambda t, d: struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t + d) & 0xffffffff)
open(dst, 'wb').write(b'\x89PNG\r\n\x1a\n' + ck(b'IHDR', struct.pack('>IIBBBBB', W, H, 8, 2, 0, 0, 0)) + ck(b'IDAT', zlib.compress(raw, 6)) + ck(b'IEND', b''))
print('gravado', dst)
