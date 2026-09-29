#!/usr/bin/env python3
"""Recupera o rotulo plano de um pote cilindrico a partir das fotos de frente e de costas.

Uma foto reta de um cilindro mostra meia volta do rotulo comprimida nas bordas:
    x_foto = cx + R * sin(theta),  theta de -pi/2 a +pi/2
Amostrando a foto nesse x, a arte volta a ficar plana. Frente e costas fecham os 360 graus.

A faixa sai montada como  [metade das costas | FRENTE | metade das costas]  para a emenda
do cilindro cair no centro das costas, onde ninguem olha.

  python3 rotulo.py frente.png costas.png saida.png --json medidas.json

Mede tambem a silhueta e imprime as proporcoes (altura/diametro, onde a tampa termina,
raio da tampa) que o potes.py usa para levantar o solido de revolucao.
"""
import sys, json, argparse
import numpy as np
from PIL import Image

LIMIAR_FUNDO = 244


def silhueta(im):
    """Recorta o objeto por flood fill do fundo a partir da borda.

    O fundo do packshot e branco puro e encosta na moldura; a tampa branca do pote nao.
    Limiar por brilho pegaria a tampa como fundo, por isso o preenchimento.
    """
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    h, w = a.shape[:2]
    claro = a.min(-1) >= LIMIAR_FUNDO
    fundo = np.zeros((h, w), bool)
    # semeia toda a borda clara e espalha em ondas (dilatacao restrita ao que e claro)
    fundo[0][claro[0]] = True; fundo[-1][claro[-1]] = True
    fundo[:, 0][claro[:, 0]] = True; fundo[:, -1][claro[:, -1]] = True
    while True:
        prox = fundo.copy()
        prox[1:] |= fundo[:-1]; prox[:-1] |= fundo[1:]
        prox[:, 1:] |= fundo[:, :-1]; prox[:, :-1] |= fundo[:, 1:]
        prox &= claro
        if prox.sum() == fundo.sum():
            break
        fundo = prox
    m = ~fundo
    for _ in range(2):   # descarta sombra difusa e ruido de borda
        m = m & np.roll(m, 2, 0) & np.roll(m, -2, 0) & np.roll(m, 2, 1) & np.roll(m, -2, 1)
    ys, xs = np.nonzero(m)
    return m, (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def medir(caminho):
    """Silhueta e raio de cada linha do objeto, normalizados."""
    im = Image.open(caminho)
    m, (x0, y0, x1, y1) = silhueta(im)
    alt = y1 - y0
    larg = m[y0:y1].sum(1).astype(float)
    # preenche linhas vazias (topo/base do recorte) com o vizinho
    for i in range(1, len(larg)):
        if larg[i] == 0: larg[i] = larg[i - 1]
    for i in range(len(larg) - 2, -1, -1):
        if larg[i] == 0: larg[i] = larg[i + 1]
    rmax = larg.max() / 2.0
    # centro por linha: o pote pode estar levemente fora de eixo
    cx = np.array([(np.nonzero(m[y])[0].mean() if m[y].any() else 0.0) for y in range(y0, y1)])
    for i in range(1, len(cx)):
        if cx[i] == 0: cx[i] = cx[i - 1]
    raio = larg / 2.0
    return dict(im=im, caixa=(x0, y0, x1, y1), altura=alt, rmax=rmax,
                cx=cx, raio=raio, razao=alt / (2.0 * rmax))


def perfil_normalizado(d, n=256):
    """radius(v) com v de 0 (topo) a 1 (base), em fracao do raio maximo."""
    r = d["raio"] / d["rmax"]
    idx = np.linspace(0, len(r) - 1, n)
    return np.interp(idx, np.arange(len(r)), r)


def desentorta(d, W, H, arco=0.985):
    """Reamostra a meia volta visivel em W x H, usando o raio real de cada linha."""
    a = np.asarray(d["im"].convert("RGB")).astype(np.float32)
    x0, y0, x1, y1 = d["caixa"]
    u = (np.arange(W) + 0.5) / W
    seno = np.sin((u - 0.5) * np.pi * arco)                 # (W,)
    ys = np.linspace(0, d["altura"] - 1, H)
    yi = np.clip(y0 + ys, 0, a.shape[0] - 2)
    y0i = np.floor(yi).astype(int); fy = (yi - y0i)[:, None, None]
    # raio e centro interpolados na mesma grade de linhas
    r = np.interp(ys, np.arange(d["altura"]), d["raio"])[:, None]
    c = np.interp(ys, np.arange(d["altura"]), d["cx"])[:, None]
    xi = np.clip(c + r * seno[None, :], 0, a.shape[1] - 2)   # (H, W)
    x0i = np.floor(xi).astype(int); fx = (xi - x0i)[..., None]
    rows0 = a[y0i]; rows1 = a[y0i + 1]
    ar = np.arange(H)[:, None]
    p00 = rows0[ar, x0i]; p01 = rows0[ar, x0i + 1]
    p10 = rows1[ar, x0i]; p11 = rows1[ar, x0i + 1]
    out = (p00 * (1 - fx) + p01 * fx) * (1 - fy) + (p10 * (1 - fx) + p11 * fx) * fy
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def casa_exposicao(fr, co, faixa=0.14):
    """Iguala o brilho das costas ao da frente pela faixa de topo, comum as duas.

    As duas fotos vem de tomadas diferentes: sem isso a emenda do rotulo aparece
    como uma listra vertical de brilho no pote.
    """
    a = np.asarray(fr).astype(np.float32)
    b = np.asarray(co).astype(np.float32)
    h = max(2, int(a.shape[0] * faixa))
    ma = a[:h].reshape(-1, 3).mean(0)
    mb = b[:h].reshape(-1, 3).mean(0)
    ganho = np.clip(ma / np.maximum(mb, 1.0), 0.75, 1.33)
    return Image.fromarray(np.clip(b * ganho, 0, 255).astype(np.uint8))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frente"); ap.add_argument("costas"); ap.add_argument("saida")
    ap.add_argument("--largura", type=int, default=2048)
    ap.add_argument("--arco", type=float, default=0.985)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()

    f = medir(a.frente); c = medir(a.costas)
    meia = a.largura // 2
    # altura da tira proporcional ao desenvolvimento da circunferencia
    H = int(meia * f["altura"] / (np.pi * f["rmax"]))

    fr = desentorta(f, meia, H, a.arco)
    co = desentorta(c, meia, H, a.arco)
    co = casa_exposicao(fr, co)
    tira = Image.new("RGB", (a.largura, H))
    q = meia // 2
    tira.paste(co.crop((q, 0, meia, H)), (0, 0))      # metade direita das costas
    tira.paste(fr, (q, 0))                             # frente inteira, centrada
    tira.paste(co.crop((0, 0, q, H)), (q + meia, 0))   # metade esquerda das costas
    tira.save(a.saida)

    perf = perfil_normalizado(f)
    info = dict(razao_altura_diametro=round(f["razao"], 4),
                tira=[a.largura, H],
                perfil=[round(float(v), 4) for v in perf])
    print(json.dumps({k: v for k, v in info.items() if k != "perfil"}, indent=1))
    print("perfil: %d amostras, raio %.3f a %.3f" % (len(perf), perf.min(), perf.max()))
    if a.json:
        json.dump(info, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
