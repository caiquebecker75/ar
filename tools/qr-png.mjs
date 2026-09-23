// QR code em PNG para colocar em apresentações e propostas:
//   node tools/qr-png.mjs <pasta-do-display>   →  <pasta>/qr.png
import qrcode from 'qrcode-generator';
import sharp from 'sharp';
import { fileURLToPath } from 'node:url';   // o caminho do repo pode ter espaços (HD externo)
const slug = process.argv[2];
const url = `https://projetos.75lab.com.br/ar/${slug}/`;
const qr = qrcode(0, 'M');
qr.addData(url);
qr.make();
const svg = qr.createSvgTag({ cellSize: 20, margin: 4 });
await sharp(Buffer.from(svg)).png().toFile(fileURLToPath(new URL(`../${slug}/qr.png`, import.meta.url)));
console.log('qr.png →', url);
