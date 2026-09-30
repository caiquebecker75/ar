// QR de uma URL qualquer:  node tools/_qr-url.mjs <url> <saida.png>
import qrcode from 'qrcode-generator';
import sharp from 'sharp';
const [url, out] = process.argv.slice(2);
const qr = qrcode(0, 'M');
qr.addData(url); qr.make();
await sharp(Buffer.from(qr.createSvgTag({ cellSize: 20, margin: 4 }))).png().toFile(out);
console.log('qr ->', out, url);
