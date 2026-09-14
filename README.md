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
| `ngv-stand-conexao-farma/` | NGV Ecossistema, stand Conexão Farma 2027 (Abradilan) | 3 × 8 × 5 m (ambiente inteiro) |

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

## Ambientes grandes (stand inteiro)

O stand da NGV veio do Blender com ~2,7 milhões de triângulos e 170 MB. O que levou a 22 MB / 417 mil:

1. **No Blender, antes de exportar** (`tools/blender-export-ambiente.py`):
   subdivisão (`SUBSURF`) em 0, `DISPLACE` desligado, `DECIMATE` nas malhas acima de 6 mil triângulos,
   imagens acima de 4096 px reduzidas (o `sharp` não abre o piso de 14 × 22 mil px). Coleções excluídas
   da view layer, luzes e câmeras ficam de fora (`use_visible`, `export_lights=False`).
2. **Preparar com limites mais duros**:
   ```bash
   node tools/prepare-glb.mjs raw.glb <pasta>/display.glb --rotate-y=-90 \
     --max-texture=2048 --max-texture-data=1024 --max-tri=1500 --simplify-error=0.02
   ```
   `--max-texture-data` reduz só normal/rugosidade/metal (a arte das paredes continua em 2048).
3. **Escala livre** (`ar-scale="auto"`): abre em tamanho real e a pinça diminui o stand (com `fixed`
   o Quick Look deixa pinçar mas volta sozinho para 100%).
4. **Modo imersivo** (o lugar real some, fica só o stand): versão com piso e cúpula virtuais em volta,
   faces para dentro e cor só emissiva. O stand recua para a pessoa começar de frente para a entrada.
   ```bash
   node tools/imersivo-glb.mjs <pasta>/display.glb <pasta>/imersivo.glb   # --raio=15 --recuo=auto
   node tools/run-page.mjs "http://localhost:8833/tools/usdz.html?slug=<pasta>&file=imersivo"
   python3 tools/usdz-compact.py <pasta>/imersivo.usdz && usdchecker --arkit <pasta>/imersivo.usdz
   ```
   O botão "Modo imersivo" (script na própria página) abre direto o AR nativo com escala travada:
   iPhone por `<a rel="ar" href="imersivo.usdz#allowsContentScaling=0">`, Android por intent do
   Scene Viewer com `resizable=false` e `disable_occlusion=true`.

## O que o `prepare-glb.mjs` corrige

- Aplica as transformações dos objetos na geometria (escala negativa do Blender vira geometria espelhada correta).
- "Assa" as transformações de textura (`KHR_texture_transform`) nas UVs, porque o Quick Look interpreta errado.
- Transforma faces de dois lados em geometria real, com o verso recuado 1 mm. O Quick Look não desenha o verso das faces, e lado de fora e lado de dentro coincidentes brigam entre si. Malhas fechadas e opacas (ex.: melões) ficam sem verso, porque o lado de dentro nunca aparece.
- Separa a imagem usada como cor e como mapa técnico ao mesmo tempo.
- Simplifica malhas com mais de 4.000 triângulos (`--max-tri`), com erro máximo de 0,5% do tamanho delas: os melões de 18 mil triângulos viram 4 mil sem diferença visível.
- Põe a origem no centro da base (o display nasce apoiado no chão) e reduz as texturas para JPEG ≤ 2048 px.
