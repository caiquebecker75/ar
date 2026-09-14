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
| `savencia-clipstrip-frescatino/` | Savencia, Clip Strip Frescatino | 70 × 10 × 6 cm |
| `codice-displays/` | Códice, oito displays numa página (`?modelo=essencial`, `sense`, `media`, `ilha`, `painel`, `vitrine`, `categoria`, `multiuso`) | medidas de referência, de 195 × 74 × 52 cm a 202 × 104 × 55 cm |

> **Códice:** não havia arquivo 3D dos displays. Os modelos foram montados em three.js a partir dos renders
> do deck comercial, com as texturas desenhadas em canvas (logotipo, painel perfurado, tela do pacote Media).
> Para refazer: `tools/codice/build.html` grava `.work/codice/raw-<id>.glb` → `prepare-glb.mjs` para
> `codice-displays/<id>.glb` → `tools/usdz.html?slug=codice-displays&file=<id>` + `usdz-compact.py` →
> `tools/codice/shots.html` (posters) → `tools/codice/og.html` (miniatura; o `capture.html` com oito modelos
> fica ilegível). As medidas são de referência, não de fabricação.

> **Arquivo do Modo (.lxo), como o clip strip da Savencia:** o Blender não abre `.lxo`. A geometria foi lida
> direto do arquivo (formato IFF parecido com o LWO: `PNTS`, `POLS`, `PTAG`, `VMAP/VMAD`), com o Z invertido,
> e montada no Blender por script. Cuidado: a cena pode trazer malhas escondidas de outros projetos
> (canal `visible` = `allOff`), e texturas com projeção cúbica ignoram o UV (refazer como projeção planar).

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
4. **Modo imersivo** (só o render, sem nada do lugar real): `<pasta>/imersivo.html`, 3D em tela cheia
   com three.js (vendorizado em `vendor/three/`), sem câmera. Olha em volta pelo giroscópio do celular
   (no iPhone a permissão é pedida no toque de "Entrar"), anda com o controle na tela (W A S D no
   computador), colide com o stand por raios curtos. Usa o mesmo `display.glb` da página de AR (cache).

   **Não tente fazer imersão dentro do AR do iPhone.** Em iPhone com LiDAR, o AR Quick Look recorta
   o modelo com a geometria real (paredes, portas, pessoas) e não há parâmetro para desligar. Uma cúpula
   virtual em volta do stand não resolve: as paredes reais estão mais perto que ela e aparecem por cima.
   O parâmetro `&file=` do `usdz.html` ficou dessa tentativa (converte `<file>.glb` → `<file>.usdz`).

## O que o `prepare-glb.mjs` corrige

- Aplica as transformações dos objetos na geometria (escala negativa do Blender vira geometria espelhada correta).
- "Assa" as transformações de textura (`KHR_texture_transform`) nas UVs, porque o Quick Look interpreta errado.
- Transforma faces de dois lados em geometria real, com o verso recuado 1 mm. O Quick Look não desenha o verso das faces, e lado de fora e lado de dentro coincidentes brigam entre si. Malhas fechadas e opacas (ex.: melões) ficam sem verso, porque o lado de dentro nunca aparece.
- Separa a imagem usada como cor e como mapa técnico ao mesmo tempo.
- Simplifica malhas com mais de 4.000 triângulos (`--max-tri`), com erro máximo de 0,5% do tamanho delas: os melões de 18 mil triângulos viram 4 mil sem diferença visível.
- Põe a origem no centro da base (o display nasce apoiado no chão) e reduz as texturas para JPEG ≤ 2048 px.
