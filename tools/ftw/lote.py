#!/usr/bin/env python3
"""Roda rotulo.py, potes.py e prepare-glb.mjs para todos os potes da vitrine FTW.

  python3 tools/ftw/lote.py --pack <pasta com os packshots> [--so creatina,whey]

Cada item da tabela abaixo diz de qual foto sai a frente e de qual saem as costas
(o padrao do site e 2 e 3, mas alguns produtos foram fotografados em outra ordem),
e o diametro de referencia do pote em metros.
"""
import argparse, json, os, subprocess, sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
W = os.path.join(RAIZ, '.work', 'ftw')
BLENDER = '/Applications/Blender.app/Contents/MacOS/Blender'

POTES = [
    # id           frente costas  diametro (m)
    ('creatina',    2, 3, 0.095),
    ('whey',        2, 3, 0.118),
    ('preworkout',  2, 3, 0.095),
    ('delicious',   3, 4, 0.095),
    ('wheynerd',    2, 3, 0.095),
    ('bcaa',        2, 3, 0.095),
    ('glutamina',   2, 3, 0.095),
    ('thermo',      2, 3, 0.095),
    ('multivit',    2, 3, 0.055),
    ('joint',       2, 3, 0.058),
    ('carnitina',   2, 3, 0.058),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pack', required=True)
    ap.add_argument('--so', default=None)
    a = ap.parse_args()
    filtro = set(a.so.split(',')) if a.so else None

    for d in ('med', 'tex', 'build'):
        os.makedirs(os.path.join(W, d), exist_ok=True)

    cfg = {}
    for pid, fi, bi, diam in POTES:
        if filtro and pid not in filtro:
            continue
        frente = os.path.join(a.pack, f'{pid}-{fi}.png')
        costas = os.path.join(a.pack, f'{pid}-{bi}.png')
        if not (os.path.exists(frente) and os.path.exists(costas)):
            print(f'  [pulado] {pid}: falta frente ou costas'); continue
        med = os.path.join(W, 'med', f'{pid}.json')
        tex = os.path.join(W, 'tex', f'{pid}.png')
        r = subprocess.run([sys.executable, os.path.join(RAIZ, 'tools/ftw/rotulo.py'),
                            frente, costas, tex, '--json', med], capture_output=True, text=True)
        if r.returncode:
            print(f'  [erro] rotulo {pid}: {r.stderr.strip()[-200:]}'); continue
        cfg[pid] = dict(perfil=f'med/{pid}.json', tira=f'tex/{pid}.png',
                        diametro=diam, saida=f'build/{pid}/raw.glb', segmentos=96)

    json.dump(cfg, open(os.path.join(W, 'potes.json'), 'w'), indent=1)

    for pid in cfg:
        env = dict(os.environ, CFG=os.path.join(W, 'potes.json'), PECA=pid)
        r = subprocess.run([BLENDER, '-b', '-P', 'tools/ftw/potes.py'],
                           cwd=RAIZ, env=env, capture_output=True, text=True)
        linha = [l for l in r.stdout.splitlines() if l.startswith('OK ')]
        if not linha:
            print(f'  [erro] blender {pid}: {r.stdout.strip()[-300:]}'); continue
        raw = os.path.join(W, 'build', pid, 'raw.glb')
        web = os.path.join(W, 'build', pid, 'web.glb')
        p = subprocess.run(['node', 'tools/prepare-glb.mjs', raw, web,
                            '--max-texture=2048', '--max-tri=9000'],
                           cwd=RAIZ, capture_output=True, text=True)
        kb = os.path.getsize(web) // 1024 if os.path.exists(web) else 0
        print(f'  {linha[0]}  ->  web.glb {kb} KB')


if __name__ == '__main__':
    main()
