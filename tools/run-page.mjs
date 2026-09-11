// Roda uma das páginas de ferramenta (usdz.html, capture.html) no Chrome headless,
// com perfil temporário, e espera ela escrever PRONTO (ou ERRO).
// Precisa do servidor local no ar: python3 tools/serve.py
//
//   node tools/run-page.mjs "http://localhost:8833/tools/capture.html?slug=<pasta>"
import puppeteer from 'puppeteer-core';

const url = process.argv[2];
const browser = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new',
  args: ['--use-angle=metal', '--enable-unsafe-swiftshader'],
});
try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 1000, deviceScaleFactor: 2 });
  page.on('pageerror', (e) => console.error('pageerror:', e.message));
  await page.goto(url, { waitUntil: 'load' });
  await page.waitForFunction(() => /PRONTO|ERRO/.test(document.getElementById('log')?.textContent || ''), { timeout: 120000 });
  console.log(await page.$eval('#log', (el) => el.textContent));
} finally {
  await browser.close();
}
