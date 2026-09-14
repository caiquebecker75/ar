// AR 75 LAB — comportamento da página de display (visualizador 3D + botão de AR)
//
// Uma página pode ter vários modelos (ex.: tamanhos M e P do mesmo display). A lista vem
// em <script type="application/json" id="modelos">; os botões [data-modelo] trocam o modelo
// do visualizador e o botão de AR abre o que estiver escolhido. ?modelo=p abre já no P.
// Sem a lista, vale o src escrito no próprio <model-viewer>.
const $ = (s) => document.querySelector(s);
const mv = $('model-viewer');
const ua = navigator.userAgent;
const isIOS = /iPhone|iPad|iPod/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const isMobile = document.documentElement.classList.contains('is-mobile');
const pageUrl = location.origin + location.pathname;

const panels = { ar: $('#panel-ar'), noar: $('#panel-noar'), desktop: $('#panel-desktop'), erro: $('#panel-erro') };
const show = (name) => Object.entries(panels).forEach(([key, el]) => { if (el) el.hidden = key !== name; });

let toastTimer;
function toast(msg) {
  const el = $('.toast');
  el.textContent = msg;
  el.classList.add('on');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('on'), 4200);
}

if (matchMedia('(prefers-reduced-motion: reduce)').matches) mv.removeAttribute('auto-rotate');

const modelos = JSON.parse($('#modelos')?.textContent || '[]');
let atual = null;
const linkAtual = () => (modelos.length > 1 && atual ? `${pageUrl}?modelo=${atual.id}` : pageUrl);

// ---------- barra de carregamento ----------
const cta = $('#cta');
const ctaLabel = cta.querySelector('span');
let ctaText = ctaLabel.textContent;
let ready = false;
const barra = $('.progress');
mv.addEventListener('progress', (e) => {
  const p = e.detail.totalProgress;
  barra.querySelector('i').style.width = `${Math.round(p * 100)}%`;
  barra.classList.toggle('done', p >= 1);
  if (isMobile && !ready) ctaLabel.textContent = `Carregando ${Math.round(p * 100)}%`;
});
mv.addEventListener('error', () => show('erro'));

// ---------- qual painel mostrar ----------
function enableAR() {
  ready = true;
  cta.disabled = false;
  ctaLabel.textContent = ctaText;
  show('ar');
}
// a detecção de suporte do model-viewer é assíncrona: tenta por alguns instantes
function waitForAR(ms) {
  return new Promise((resolve) => {
    const t0 = performance.now();
    (function check() {
      if (mv.canActivateAR) return resolve(true);
      if (performance.now() - t0 > ms) return resolve(false);
      setTimeout(check, 150);
    })();
  });
}

function desenharQR() {
  if (!window.qrcode || !$('#qr')) return;
  const qr = qrcode(0, 'M');
  qr.addData(linkAtual());
  qr.make();
  $('#qr').innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true, alt: 'QR code desta página' });
}

// ---------- escolha do modelo ----------
function escolher(m) {
  if (!m || m === atual) return;
  const troca = atual !== null;
  atual = m;
  mv.setAttribute('poster', m.poster);
  mv.setAttribute('ios-src', m.ios);
  mv.setAttribute('alt', m.alt);
  mv.setAttribute('src', m.src);
  ctaText = `Ver o ${m.nome} no meu espaço`;
  document.querySelectorAll('[data-modelo]').forEach((b) => {
    const on = b.dataset.modelo === m.id;
    b.classList.toggle('on', on);
    b.setAttribute('aria-pressed', String(on));
  });
  if (!troca) return;
  history.replaceState(null, '', linkAtual());
  barra.classList.remove('done');
  barra.querySelector('i').style.width = '0%';
  if (!isMobile) desenharQR();
  else if (isIOS && ready) ctaLabel.textContent = ctaText; // o Quick Look abre o .usdz próprio: não precisa esperar o 3D
  else { ready = false; cta.disabled = true; }                // WebXR precisa do modelo novo carregado
}
document.querySelectorAll('[data-modelo]').forEach((b) =>
  b.addEventListener('click', () => escolher(modelos.find((m) => m.id === b.dataset.modelo))));
escolher(modelos.find((m) => m.id === new URLSearchParams(location.search).get('modelo')) || modelos[0]);

if (!isMobile) {
  show('desktop');
  desenharQR();
} else {
  show('ar');
  cta.disabled = true;
  customElements.whenDefined('model-viewer').then(async () => {
    // iPhone: o Quick Look abre o .usdz próprio, não precisa esperar o 3D da página
    if (isIOS && (await waitForAR(1500))) enableAR();
  });
  mv.addEventListener('load', async () => {
    if (ready) return;
    if (await waitForAR(2500)) enableAR();
    else show('noar');
  });
}

cta.addEventListener('click', () => mv.activateAR());

// modo do AR (ambientes grandes, ex.: stand): tamanho real travado ou maquete que dá para redimensionar
const modos = document.querySelectorAll('[data-ar-scale]');
modos.forEach((btn) => btn.addEventListener('click', () => {
  mv.setAttribute('ar-scale', btn.dataset.arScale);
  modos.forEach((b) => b.setAttribute('aria-pressed', String(b === btn)));
  if (btn.dataset.hint) $('.hint').innerHTML = btn.dataset.hint;
}));
mv.addEventListener('ar-status', (e) => {
  if (e.detail.status === 'failed') {
    toast('Não deu para abrir a realidade aumentada neste aparelho. Tente pelo Chrome (Android) ou Safari (iPhone).');
  }
});

$('#copy')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(linkAtual());
    toast('Link copiado. Agora cole no Safari ou no Chrome.');
  } catch {
    window.prompt('Copie o link:', linkAtual());
  }
});
