/**
 * add-branding-terrasat.mjs — Agrega overlay de branding TerraSAT + período de observación a imágenes
 *
 * Adaptado de add-branding.mjs (BienCuidar / LocalNourse)
 *
 * Uso: node scripts/add-branding-terrasat.mjs "<ruta-imagen>" [--output "<ruta-salida>"] [--period "05–11 ago 2026"]
 *
 * El overlay incluye:
 * - Período de observación en esquina inferior derecha (opcional, --period)
 * - Gradiente oscuro semitransparente en el borde inferior
 * - Icono de satélite + "TerraSAT" en blanco
 * - "agtisa.com" en blanco más pequeño debajo
 */

import sharp from "sharp";
import { readFileSync, writeFileSync, existsSync } from "fs";
import { resolve, dirname, join, basename, extname } from "path";

const args = process.argv.slice(2);
if (!args[0] || args[0] === "--help" || args[0] === "-h") {
  console.log('Uso: node scripts/add-branding-terrasat.mjs "<ruta-imagen>" [--output "<ruta-salida>"] [--period "05–11 ago 2026"]');
  console.log("");
  console.log("Si no se especifica --output, guarda junto al original con sufijo _branded");
  process.exit(0);
}

const inputPath = resolve(args[0]);
let outputPath = null;
let periodStr = null;

for (let i = 1; i < args.length; i++) {
  if (args[i] === "--output" && args[i + 1]) {
    outputPath = resolve(args[i + 1]);
    i++;
  } else if (args[i] === "--period" && args[i + 1]) {
    periodStr = args[i + 1];
    i++;
  }
}

if (!existsSync(inputPath)) {
  console.error(`Error: no existe el archivo ${inputPath}`);
  process.exit(1);
}

if (!outputPath) {
  const dir = dirname(inputPath);
  const name = basename(inputPath, extname(inputPath));
  outputPath = join(dir, `${name}_branded.jpg`);
}

// ── Icono SVG inline (satélite estilizado) ──
// Círculo con gradiente verde-azul + icono de satélite blanco
const ICON_SVG = `
  <defs>
    <linearGradient id="iconBgGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#059669"/>
      <stop offset="100%" stop-color="#0d9488"/>
    </linearGradient>
  </defs>
  <rect width="512" height="512" rx="128" fill="url(#iconBgGrad)"/>
  <g transform="translate(128, 128) scale(10.67)" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M13 7 9 3 5 7l4 4"/>
    <path d="m5 11-1 .5a1 1 0 0 0-.5.5L3 13l.5-.5a1 1 0 0 0 .5-.5L5 11"/>
    <path d="m19 13 .5.5a1 1 0 0 0 .5.5l.5.5-.5-.5a1 1 0 0 0-.5-.5L19 13"/>
    <path d="M14 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/>
    <path d="m9 7 5 5"/>
    <path d="m17 21 4-4-4-4-4 4 4 4Z"/>
    <path d="m14 14-5-5"/>
  </g>
`;

// ── Crear overlay SVG con gradiente + icono + texto ──
function createBrandingOverlay(width, height) {
  const gradientHeight = Math.round(height * 0.22);
  const gradientStart = height - gradientHeight;
  const padding = Math.round(width * 0.035);
  const brandSize = Math.round(width * 0.038);
  const urlSize = Math.round(width * 0.024);
  const urlY = height - padding;
  const brandY = urlY - urlSize + Math.round(width * 0.008);

  const iconSize = Math.round(brandSize * 2.4);
  const iconX = padding;
  const iconY = brandY - Math.round(iconSize * 0.75);
  const textX = padding + iconSize + Math.round(width * 0.02);

  const periodSize = Math.round(width * 0.022);
  const periodY = urlY + urlSize + Math.round(width * 0.012);
  const periodOverlay = periodStr
    ? `<text x="${width - padding}" y="${periodY}" font-family="Arial, Helvetica, sans-serif" font-size="${periodSize}" font-weight="400" fill="#ffffff" text-anchor="end" opacity="0.7">Período de observación: ${periodStr}</text>`
    : '';

  return `<svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="bottomGradient" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#000000" stop-opacity="0"/>
      <stop offset="35%" stop-color="#000000" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="#000000" stop-opacity="0.75"/>
    </linearGradient>
  </defs>
  <rect x="0" y="${gradientStart}" width="${width}" height="${gradientHeight}" fill="url(#bottomGradient)"/>
  <g transform="translate(${iconX}, ${iconY}) scale(${iconSize / 512})">
    ${ICON_SVG}
  </g>
  <text x="${textX}" y="${brandY}" font-family="Arial, Helvetica, sans-serif" font-size="${brandSize}" font-weight="600" fill="#ffffff" letter-spacing="0.5">TerraSAT</text>
  <text x="${textX}" y="${urlY + urlSize}" font-family="Arial, Helvetica, sans-serif" font-size="${urlSize}" font-weight="400" fill="#ffffff" opacity="0.85">agtisa.com</text>
  ${periodOverlay}
</svg>`;
}

async function addBranding() {
  console.log(`Procesando: ${inputPath}`);

  const image = sharp(inputPath);
  const metadata = await image.metadata();
  const width = metadata.width;
  const height = metadata.height;

  console.log(`Dimensiones: ${width}x${height}`);

  const overlaySvg = createBrandingOverlay(width, height);
  const overlayBuffer = Buffer.from(overlaySvg);

  const result = await sharp(inputPath)
    .composite([{ input: overlayBuffer, top: 0, left: 0 }])
    .flatten({ background: "#ffffff" })
    .jpeg({ quality: 85, progressive: true })
    .toBuffer();

  writeFileSync(outputPath, result);

  const inputSize = readFileSync(inputPath).length;
  const outputSize = result.length;
  console.log(`Branding agregado: ${outputPath}`);
  console.log(`Tamaño: ${(inputSize / 1024).toFixed(0)}KB → ${(outputSize / 1024).toFixed(0)}KB`);
}

addBranding().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
