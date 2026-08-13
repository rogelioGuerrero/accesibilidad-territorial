/**
 * combine-images.mjs — Combina dos imágenes lado a lado con efecto 3D
 *
 * Uso: node scripts/combine-images.mjs "<imagen_izquierda>" "<imagen_derecha>" [--output "<ruta>"]
 *
 * Efecto: sombra proyectada entre ambas imágenes, línea divisoria sutil,
 * y gradiente de fusión en el borde para dar profundidad 3D.
 */

import sharp from "sharp";
import { existsSync, writeFileSync } from "fs";
import { resolve, dirname, join } from "path";

const args = process.argv.slice(2);

if (args.length < 2 || args[0] === "--help" || args[0] === "-h") {
  console.log('Uso: node scripts/combine-images.mjs "<imagen_izquierda>" "<imagen_derecha>" [--output "<ruta>"]');
  process.exit(0);
}

const leftPath = resolve(args[0]);
const rightPath = resolve(args[1]);
let outputPath = null;

for (let i = 2; i < args.length; i++) {
  if (args[i] === "--output" && args[i + 1]) {
    outputPath = resolve(args[i + 1]);
    i++;
  }
}

if (!existsSync(leftPath)) {
  console.error(`Error: no existe ${leftPath}`);
  process.exit(1);
}
if (!existsSync(rightPath)) {
  console.error(`Error: no existe ${rightPath}`);
  process.exit(1);
}

if (!outputPath) {
  const dir = dirname(leftPath);
  outputPath = join(dir, "combined.jpg");
}

async function combine() {
  const leftMeta = await sharp(leftPath).metadata();
  const rightMeta = await sharp(rightPath).metadata();

  // Altura objetivo: la menor de ambas para no deformar
  const targetHeight = Math.min(leftMeta.height, rightMeta.height);

  // Redimensionar manteniendo proporción
  const leftResized = await sharp(leftPath)
    .resize(null, targetHeight, { fit: "cover" })
    .jpeg({ quality: 95 })
    .toBuffer();
  const rightResized = await sharp(rightPath)
    .resize(null, targetHeight, { fit: "cover" })
    .jpeg({ quality: 95 })
    .toBuffer();

  const leftInfo = await sharp(leftResized).metadata();
  const rightInfo = await sharp(rightResized).metadata();

  // Padding para la sombra 3D
  const shadowWidth = 12;
  const gap = 6; // espacio entre imágenes para la sombra
  const totalWidth = leftInfo.width + gap + rightInfo.width + shadowWidth * 2;
  const totalHeight = targetHeight + shadowWidth * 2;

  // Crear sombra SVG para la imagen derecha (efecto 3D)
  const shadowSvg = `<svg width="${rightInfo.width + shadowWidth * 2}" height="${targetHeight + shadowWidth * 2}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <filter id="dropShadow" x="-20%" y="-20%" width="140%" height="140%">
        <feGaussianBlur in="SourceAlpha" stdDeviation="6"/>
        <feOffset dx="4" dy="4" result="offsetblur"/>
        <feComponentTransfer><feFuncA type="linear" slope="0.5"/></feComponentTransfer>
        <feMerge>
          <feMergeNode/>
          <feMergeNode in="SourceGraphic"/>
        </feMerge>
      </filter>
      <linearGradient id="fusionGrad" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#000000" stop-opacity="0.15"/>
        <stop offset="50%" stop-color="#000000" stop-opacity="0"/>
        <stop offset="100%" stop-color="#000000" stop-opacity="0.15"/>
      </linearGradient>
    </defs>
    <rect x="0" y="0" width="${rightInfo.width + shadowWidth * 2}" height="${targetHeight + shadowWidth * 2}" fill="none"/>
  </svg>`;

  // Gradiente de fusión en el borde
  const fusionWidth = 30;
  const fusionSvg = `<svg width="${fusionWidth}" height="${targetHeight}" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <linearGradient id="fusionL" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#000000" stop-opacity="0"/>
        <stop offset="100%" stop-color="#000000" stop-opacity="0.25"/>
      </linearGradient>
      <linearGradient id="fusionR" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0%" stop-color="#000000" stop-opacity="0.25"/>
        <stop offset="100%" stop-color="#000000" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <rect x="0" y="0" width="${fusionWidth}" height="${targetHeight}" fill="url(#fusionL)"/>
  </svg>`;

  // Línea divisoria sutil
  const dividerSvg = `<svg width="2" height="${targetHeight}" xmlns="http://www.w3.org/2000/svg">
    <rect x="0" y="0" width="1" height="${targetHeight}" fill="#ffffff" opacity="0.3"/>
    <rect x="1" y="0" width="1" height="${targetHeight}" fill="#000000" opacity="0.15"/>
  </svg>`;

  // Componer: fondo blanco + imagen izquierda + sombra + imagen derecha + efectos
  const result = await sharp({
    create: {
      width: totalWidth,
      height: totalHeight,
      channels: 3,
      background: { r: 245, g: 245, b: 248 },
    },
  })
    .composite([
      // Imagen izquierda
      { input: leftResized, top: shadowWidth, left: shadowWidth },
      // Sombra detrás de la imagen derecha (offset)
      {
        input: Buffer.from(
          `<svg width="${rightInfo.width + 8}" height="${targetHeight + 8}" xmlns="http://www.w3.org/2000/svg">
            <rect x="4" y="4" width="${rightInfo.width}" height="${targetHeight}" fill="#000000" opacity="0.3"/>
            <rect x="4" y="4" width="${rightInfo.width}" height="${targetHeight}" fill="#000000" opacity="0.2" filter="blur(4px)"/>
          </svg>`
        ),
        top: shadowWidth - 2,
        left: shadowWidth + leftInfo.width + gap - 4,
      },
      // Imagen derecha
      { input: rightResized, top: shadowWidth, left: shadowWidth + leftInfo.width + gap },
      // Línea divisoria
      {
        input: Buffer.from(dividerSvg),
        top: shadowWidth,
        left: shadowWidth + leftInfo.width + gap - 1,
      },
      // Gradiente de fusión en borde izquierdo del mapa
      {
        input: Buffer.from(fusionSvg),
        top: shadowWidth,
        left: shadowWidth + leftInfo.width + gap,
      },
    ])
    .jpeg({ quality: 90, progressive: true })
    .toBuffer();

  writeFileSync(outputPath, result);
  console.log(`Imagen combinada: ${outputPath}`);
  console.log(`  Dimensiones: ${totalWidth}x${totalHeight}`);
  console.log(`  Izquierda: ${leftPath} (${leftInfo.width}x${leftInfo.height})`);
  console.log(`  Derecha: ${rightPath} (${rightInfo.width}x${rightInfo.height})`);
}

combine().catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
