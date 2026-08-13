/**
 * split-analysis.mjs — Efecto mitad natural / mitad análisis satelital
 *
 * Toma una imagen y la divide: izquierda tal cual, derecha con overlay de
 * polígonos de "análisis" (líneas, zonas detectadas, grid sutil).
 *
 * Uso: node scripts/split-analysis.mjs "<imagen>" [--output "<ruta>"]
 */

import sharp from "sharp";
import { existsSync, writeFileSync } from "fs";
import { resolve, dirname, join } from "path";

const args = process.argv.slice(2);

if (!args[0] || args[0] === "--help" || args[0] === "-h") {
  console.log('Uso: node scripts/split-analysis.mjs "<imagen>" [--output "<ruta>"]');
  process.exit(0);
}

const inputPath = resolve(args[0]);
let outputPath = null;

for (let i = 1; i < args.length; i++) {
  if (args[i] === "--output" && args[i + 1]) {
    outputPath = resolve(args[i + 1]);
    i++;
  }
}

if (!existsSync(inputPath)) {
  console.error(`Error: no existe ${inputPath}`);
  process.exit(1);
}

if (!outputPath) {
  const dir = dirname(inputPath);
  const name = inputPath.replace(/\.[^.]+$/, "");
  outputPath = join(dir, `${name.split(/[\\/]/).pop()}_analysis.jpg`);
}

async function processImage() {
  const meta = await sharp(inputPath).metadata();
  const width = meta.width;
  const height = meta.height;
  const halfWidth = Math.floor(width / 2);

  // ── Extraer mitad derecha y aplicar blanco y negro ──
  const rightHalf = await sharp(inputPath)
    .extract({ left: halfWidth, top: 0, width: width - halfWidth, height })
    .grayscale()
    .modulate({ brightness: 0.85, contrast: 1.15 })
    .jpeg({ quality: 95 })
    .toBuffer();

  // ── Overlay SVG para la mitad derecha ──
  // Polígonos irregulares simulando detección de zonas + grid sutil + líneas de escaneo

  // Generar polígonos pseudo-aleatorios pero deterministas
  const polygons = [];
  const zones = [
    { x: 0.15, y: 0.20, w: 0.25, h: 0.15, color: "#dc2626", opacity: 0.25 },
    { x: 0.50, y: 0.10, w: 0.20, h: 0.20, color: "#ea580c", opacity: 0.20 },
    { x: 0.10, y: 0.55, w: 0.30, h: 0.18, color: "#ca8a04", opacity: 0.18 },
    { x: 0.60, y: 0.60, w: 0.25, h: 0.22, color: "#dc2626", opacity: 0.22 },
    { x: 0.35, y: 0.40, w: 0.18, h: 0.12, color: "#ea580c", opacity: 0.15 },
  ];

  // Coordenadas en pixels de la mitad derecha
  const polyShapes = zones.map((z, i) => {
    const x = Math.round(z.x * halfWidth);
    const y = Math.round(z.y * height);
    const w = Math.round(z.w * halfWidth);
    const h = Math.round(z.h * height);
    // Polígono irregular (no rectángulo perfecto)
    const points = [
      `${x},${y}`,
      `${x + w + 5},${y - 3}`,
      `${x + w + 8},${y + h + 4}`,
      `${x - 4},${y + h + 2}`,
    ].join(" ");
    return `<polygon points="${points}" fill="${z.color}" fill-opacity="${z.opacity}" stroke="${z.color}" stroke-width="1.5" stroke-opacity="0.6"/>`;
  }).join("\n    ");

  // Grid sutil
  const gridSize = 40;
  let gridLines = "";
  for (let gx = 0; gx <= halfWidth; gx += gridSize) {
    gridLines += `<line x1="${gx}" y1="0" x2="${gx}" y2="${height}" stroke="#38bdf8" stroke-width="0.5" opacity="0.12"/>`;
  }
  for (let gy = 0; gy <= height; gy += gridSize) {
    gridLines += `<line x1="0" y1="${gy}" x2="${halfWidth}" y2="${gy}" stroke="#38bdf8" stroke-width="0.5" opacity="0.12"/>`;
  }

  // Línea de escaneo vertical (efecto de barrido)
  const scanX = Math.round(halfWidth * 0.35);
  const scanLine = `<line x1="${scanX}" y1="0" x2="${scanX}" y2="${height}" stroke="#38bdf8" stroke-width="2" opacity="0.4"/>
    <line x1="${scanX - 1}" y1="0" x2="${scanX - 1}" y2="${height}" stroke="#38bdf8" stroke-width="1" opacity="0.2"/>`;

  // Puntos de interés (markers)
  const markers = [
    { x: 0.22, y: 0.28, label: "Z1" },
    { x: 0.58, y: 0.18, label: "Z2" },
    { x: 0.18, y: 0.62, label: "Z3" },
    { x: 0.68, y: 0.68, label: "Z4" },
  ].map(m => {
    const px = Math.round(m.x * halfWidth);
    const py = Math.round(m.y * height);
    return `<circle cx="${px}" cy="${py}" r="4" fill="none" stroke="#38bdf8" stroke-width="1.5" opacity="0.8"/>
      <text x="${px + 8}" y="${py + 4}" font-family="monospace" font-size="11" fill="#38bdf8" opacity="0.7">${m.label}</text>`;
  }).join("\n    ");

  // Overlay completo para mitad derecha
  const overlaySvg = `<svg width="${halfWidth}" height="${height}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="scanFade" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#0f172a" stop-opacity="0.15"/>
        <stop offset="50%" stop-color="#0f172a" stop-opacity="0.05"/>
        <stop offset="100%" stop-color="#0f172a" stop-opacity="0.20"/>
      </linearGradient>
    </defs>
    <rect x="0" y="0" width="${halfWidth}" height="${height}" fill="url(#scanFade)"/>
    ${gridLines}
    ${polyShapes}
    ${scanLine}
    ${markers}
    <!-- Línea divisoria central -->
    <line x1="0" y1="0" x2="0" y2="${height}" stroke="#38bdf8" stroke-width="2" opacity="0.6"/>
    <line x1="1" y1="0" x2="1" y2="${height}" stroke="#ffffff" stroke-width="1" opacity="0.3"/>
  </svg>`;

  // Etiquetas superiores
  const labelsSvg = `<svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">
    <text x="20" y="30" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="600" fill="#ffffff" opacity="0.85">Imagen satelital</text>
    <text x="${halfWidth + 20}" y="30" font-family="monospace" font-size="13" font-weight="500" fill="#38bdf8" opacity="0.9">Análisis AgroSAT</text>
  </svg>`;

  // Componer: imagen original + mitad derecha en B/N + overlay + etiquetas
  const result = await sharp(inputPath)
    .composite([
      { input: rightHalf, top: 0, left: halfWidth },
      { input: Buffer.from(overlaySvg), top: 0, left: halfWidth },
      { input: Buffer.from(labelsSvg), top: 0, left: 0 },
    ])
    .jpeg({ quality: 90, progressive: true })
    .toBuffer();

  writeFileSync(outputPath, result);
  console.log(`Imagen procesada: ${outputPath}`);
  console.log(`  Dimensiones: ${width}x${height}`);
  console.log(`  Mitad natural: 0-${halfWidth}px`);
  console.log(`  Mitad análisis: ${halfWidth}-${width}px`);
}

processImage().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
