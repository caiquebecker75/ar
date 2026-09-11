// AR 75 LAB — comportamento da página de display (visualizador 3D + botão de AR)
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

// ---------- barra de carregamento ----------
const cta = $('#cta');
const ctaLabel = cta.querySelector('span');
const ctaText = ctaLabel.textContent;
let ready = false;
mv.addEventListener('progress', (e) => {
  const p = e.detail.totalProgress;
  $('.progress i').style.width = `${Math.round(p * 100)}%`;
  if (p >= 1) $('.progress').classList.add('done');
  if (!ready) ctaLabel.textContent = `Carregando ${Math.round(p * 100)}%`;
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

if (!isMobile) {
  show('desktop');
  if (window.qrcode) {
    const qr = qrcode(0, 'M');
    qr.addData(pageUrl);
    qr.make();
    $('#qr').innerHTML = qr.createSvgTag({ cellSize: 4, margin: 0, scalable: true, alt: 'QR code desta página' });
  }
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
mv.addEventListener('ar-status', (e) => {
  if (e.detail.status === 'failed') {
    toast('Não deu para abrir a realidade aumentada neste aparelho. Tente pelo Chrome (Android) ou Safari (iPhone).');
  }
});

$('#copy')?.addEventListener('click', async () => {
  try {
    await navigator.clipboard.writeText(pageUrl);
    toast('Link copiado. Agora cole no Safari ou no Chrome.');
  } catch {
    window.prompt('Copie o link:', pageUrl);
  }
});
