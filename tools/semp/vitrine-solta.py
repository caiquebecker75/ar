# Gera a versão "solta" do embed.html (arquivo único que roda de qualquer pasta, buscando os modelos no site).
#   python3 tools/semp/vitrine-solta.py [pasta-de-saida]
import os, sys
B = 'https://projetos.75lab.com.br/ar/'
raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) + '/'
s = open(raiz + 'semp-split-hw/embed.html').read()
pares = [
 ('src="../vendor/model-viewer.min.js"', f'src="{B}vendor/model-viewer.min.js"'),
 ('src="../vendor/qrcode.min.js"', f'src="{B}vendor/qrcode.min.js"'),
 ('src="${p.id}.glb?v=1"', 'src="${BASE}${p.id}.glb?v=1"'),
 ('poster="${p.id}-poster.webp', 'poster="${BASE}${p.id}-poster.webp'),
 ('<img src="${p.id}-poster.webp', '<img src="${BASE}${p.id}-poster.webp'),
 ("const AR_URL = (id) => new URL(`./?modelo=${id}`, location.href).href;",
  "const BASE = 'https://projetos.75lab.com.br/ar/semp-split-hw/';\nconst AR_URL = (id) => `${BASE}?modelo=${id}`;"),
 ('<a class="ar" id="ar" href="./"', f'<a class="ar" id="ar" href="{B}semp-split-hw/"'),
]
for a, b in pares:
    assert s.count(a) == 1, a
    s = s.replace(a, b)
ini = s.index('<!--'); fim = s.index('-->', ini) + 3
s = s[:ini] + """<!--
  Vitrine das 15 peças SEMP Split HW em 3D e AR (75 LAB). Arquivo completo: funciona sozinho, com internet
  (os modelos 3D vêm de projetos.75lab.com.br). Ocupa 100% da janela ou do iframe onde for colocado.
  Parâmetros opcionais no endereço: ?peca=portico · ?modo=todas · ?escala=real · ?fundo=transparente
-->""" + s[fim:]
saida = (sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/Downloads/semp-split-hw-apresentacao')) + '/vitrine-pecas-semp.html'
os.makedirs(os.path.dirname(saida), exist_ok=True); open(saida, 'w').write(s)
print('gravado', saida)
