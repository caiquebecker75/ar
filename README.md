# AR 75 LAB

Displays da 75 LAB em realidade aumentada, em tamanho real, direto no celular (sem app).
Publicado no GitHub Pages: `https://projetos.75lab.com.br/ar/<pasta-do-display>/`

| Aparelho | Como abre o AR |
|---|---|
| iPhone (Safari) | AR Quick Look, com o `display.usdz` |
| Android (Chrome) | WebXR no navegador ou Google Scene Viewer, com o `display.glb` |
| Computador | Visualizador 3D + QR code para abrir no celular |

A escala fica travada (`ar-scale="fixed"`): o cliente não consegue aumentar nem diminuir o display.

## Displays

| Pasta | Cliente | Medidas (A × L × P) |
|---|---|---|
| `famosa-display-maromba/` | Agrícola Famosa, Display Maromba M | 137 × 109 × 40 cm |
| `famosa-display-maromba-p/` | Agrícola Famosa, Display Maromba P | 137 × 58 × 40 cm |

## Como publicar um display novo

Pré-requisitos (uma vez): `cd tools && npm install`. O resto já vem no macOS (`usdzip`, `usdchecker`, `swift`) e no Chrome instalado.

1. **Exportar do Blender em .glb**, com a escala em metros (1 unidade = 1 m).
2. **Preparar o modelo** (a frente do display tem de ficar em +Z; teste `--rotate-y=0/90/180/-90`):
   ```bash
   node tools/prepare-glb.mjs "$HOME/Downloads/ARQUIVO.glb" <pasta>/display.glb --rotate-y=90
   ```
   O script mostra as medidas finais. Confira com o projeto antes de seguir.
3. **Subir o servidor local**: `python3 tools/serve.py` (porta 8833).
4. **Gerar o USDZ do iPhone** e validar:
   ```bash
   node tools/run-page.mjs "http://localhost:8833/tools/usdz.html?slug=<pasta>"
   python3 tools/usdz-compact.py <pasta>/display.usdz
   usdchecker --arkit <pasta>/display.usdz
   swift tools/render-usdz.swift <pasta>/display.usdz /tmp/vistas.png   # confere no motor da Apple
   ```
5. **Copiar a página**: `famosa-display-maromba/index.html` → `<pasta>/index.html` e trocar
   cliente, nome, medidas, `og:url`, `og:image` e `<title>`.
6. **Gerar a imagem de carregamento e a miniatura do WhatsApp** (lê os textos da página):
   ```bash
   node tools/run-page.mjs "http://localhost:8833/tools/capture.html?slug=<pasta>"
   ```
7. **QR code para apresentações** (PNG em alta): `node tools/qr-png.mjs <pasta>` → `<pasta>/qr.png`.
8. Commit e push na `main`. O Pages publica em ~1 minuto.

**Atualizando um display que já existe:** repita os passos 2, 4 e 6 e suba o `?v=N` de `display.glb`,
`display.usdz`, `poster.webp` e `og.jpg` no `index.html` — sem isso, celulares que já abriram o link
continuam vendo o modelo antigo por um tempo (cache).

## O que o `prepare-glb.mjs` corrige

- Aplica as transformações dos objetos na geometria (escala negativa do Blender vira geometria espelhada correta).
- "Assa" as transformações de textura (`KHR_texture_transform`) nas UVs, porque o Quick Look interpreta errado.
- Transforma faces de dois lados em geometria real, com o verso recuado 1 mm. O Quick Look não desenha o verso das faces, e lado de fora e lado de dentro coincidentes brigam entre si. Malhas fechadas e opacas (ex.: melões) ficam sem verso, porque o lado de dentro nunca aparece.
- Separa a imagem usada como cor e como mapa técnico ao mesmo tempo.
- Simplifica malhas com mais de 4.000 triângulos (`--max-tri`), com erro máximo de 0,5% do tamanho delas: os melões de 18 mil triângulos viram 4 mil sem diferença visível.
- Põe a origem no centro da base (o display nasce apoiado no chão) e reduz as texturas para JPEG ≤ 2048 px.
