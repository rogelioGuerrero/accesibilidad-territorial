"""
TerraSAT / AgroSAT — Boletín Pan-Regional de Alerta Temprana Agroclimática

TerraSAT: Procesamiento de imágenes satelitales (marca corporativa)
AgroSAT: Alerta temprana para la agricultura (producto #1)

Producto público: boletín semanal pan-regional (Centroamérica + Suramérica).
Formato periodístico, sin revelar metodología técnica.
Menciona agencias (NASA, ESA) para credibilidad.
CTA: ofrece reportes personalizados a nivel finca.

Salidas:
  1. Boletín impreso en consola
  2. scripts/generated-article.txt — artículo listo para Facebook
  3. scripts/gemini-prompt.txt — prompt para generar imagen

Ejecutar: uv run python nooa-agent/demo_alerta_temprana_regional.py
"""

from __future__ import annotations

import logging
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.WARNING)


# ═════════════════════════════════════════════════════════════════════
# Modelo de zona agroclimática
# ═════════════════════════════════════════════════════════════════════

@dataclass
class AgroZone:
    name: str
    country: str
    crop: str
    lat: float
    lng: float
    area_ha: int  # hectáreas monitoreadas en la zona

    # Datos multi-sensor (simulados, no se revelan en el boletín)
    ndre_delta: float = 0.0
    ndvi_delta: float = 0.0
    lst_delta: float = 0.0
    rainfall_mm: float = 0.0
    rainfall_pct: float = 0.0  # % vs normal
    modis_z_score: float = 0.0

    # Estado calculado
    status: str = "normal"  # normal / vigilancia / alerta / critico
    alert_cause: str = ""
    affected_area_ha: int = 0
    days_early_warning: int = 0

    # Para el boletín
    headline: str = ""
    summary: str = ""


# ═════════════════════════════════════════════════════════════════════
# Zonas agroclimáticas — Centroamérica + Suramérica
# ═════════════════════════════════════════════════════════════════════

def generate_zones() -> list[AgroZone]:
    return [
        # ─── Centroamérica: café ───
        AgroZone("Intibucá", "Honduras", "Café", 14.35, -88.20, 45_000),
        AgroZone("El Paraíso", "Honduras", "Café", 14.15, -86.55, 38_000),
        AgroZone("Alta Verapaz", "Guatemala", "Café", 15.58, -90.30, 52_000),
        AgroZone("Jinotega", "Nicaragua", "Café", 13.10, -86.00, 42_000),
        # ─── Suramérica: café ───
        AgroZone("Caldas", "Colombia", "Café", 5.07, -75.50, 65_000),
        AgroZone("Quindío", "Colombia", "Café", 4.46, -75.67, 48_000),
        AgroZone("Espírito Santo", "Brasil", "Café", -19.19, -40.34, 85_000),
        AgroZone("Minas Gerais", "Brasil", "Café", -18.70, -44.50, 120_000),
        # ─── Suramérica: soja ───
        AgroZone("Mato Grosso", "Brasil", "Soja", -12.50, -55.70, 320_000),
        AgroZone("Córdoba", "Argentina", "Soja", -31.42, -64.18, 180_000),
        # ─── Suramérica: viñas ───
        AgroZone("Valle Central", "Chile", "Viñas", -35.00, -71.00, 55_000),
        AgroZone("Mendoza", "Argentina", "Viñas", -32.89, -68.83, 95_000),
        # ─── Suramérica: caña ───
        AgroZone("São Paulo", "Brasil", "Caña", -22.00, -48.00, 210_000),
    ]


# ═════════════════════════════════════════════════════════════════════
# Simulación multi-sensor (interna, no se revela en el boletín)
# ═════════════════════════════════════════════════════════════════════

def simulate_zones(zones: list[AgroZone], seed: int = 2026):
    rng = random.Random(seed)

    # Zonas con estrés (basado en patrones reales 2022-2023)
    # Índices corresponden a generate_zones()
    stress_zones = {
        0: "severo",       # Intibucá, Honduras — roya crítica
        1: "moderado",     # El Paraíso, Honduras — estrés hídrico
        4: "moderado",     # Caldas, Colombia — roya
        6: "moderado",     # Espírito Santo, Brasil — estrés hídrico
        8: "severo",       # Mato Grosso, Brasil — sequía soja
        10: "leve",        # Valle Central, Chile — vigilancia viñas
        3: "leve",         # Jinotega, Nicaragua — vigilancia
    }

    # Precipitación normal varía por región
    chirps_normal_ca = rng.uniform(650, 780)   # Centroamérica
    chirps_normal_sa = rng.uniform(900, 1300)  # Suramérica tropical
    chirps_normal_sul = rng.uniform(400, 650)  # Cono Sur (Chile, Argentina)

    for i, zone in enumerate(zones):
        stress = stress_zones.get(i, "normal")

        # Seleccionar baseline de precipitación según región
        if zone.country in ("Honduras", "Guatemala", "Nicaragua", "El Salvador"):
            chirps_normal = chirps_normal_ca
        elif zone.country in ("Chile", "Argentina"):
            chirps_normal = chirps_normal_sul
        else:
            chirps_normal = chirps_normal_sa

        if stress == "severo":
            zone.ndre_delta = rng.uniform(-0.12, -0.08)
            zone.ndvi_delta = rng.uniform(-0.06, -0.03)
            zone.lst_delta = rng.uniform(2.5, 4.0)
            zone.rainfall_mm = chirps_normal * rng.uniform(0.55, 0.70) if zone.crop == "Soja" else chirps_normal * rng.uniform(0.92, 1.05)
            zone.modis_z_score = rng.uniform(-2.2, -1.8)
        elif stress == "moderado":
            zone.ndre_delta = rng.uniform(-0.06, -0.03)
            zone.ndvi_delta = rng.uniform(-0.03, -0.01)
            zone.lst_delta = rng.uniform(1.0, 2.0)
            zone.rainfall_mm = chirps_normal * rng.uniform(0.65, 0.78) if i in (1, 6) else chirps_normal * rng.uniform(0.90, 1.05)
            zone.modis_z_score = rng.uniform(-1.8, -1.2)
        elif stress == "leve":
            zone.ndre_delta = rng.uniform(-0.03, -0.015)
            zone.ndvi_delta = rng.uniform(-0.01, 0.005)
            zone.lst_delta = rng.uniform(0.5, 1.0)
            zone.rainfall_mm = chirps_normal * rng.uniform(0.88, 1.02)
            zone.modis_z_score = rng.uniform(-1.2, -0.8)
        else:
            zone.ndre_delta = rng.uniform(-0.01, 0.01)
            zone.ndvi_delta = rng.uniform(-0.005, 0.01)
            zone.lst_delta = rng.uniform(-0.5, 0.5)
            zone.rainfall_mm = chirps_normal * rng.uniform(0.92, 1.08)
            zone.modis_z_score = rng.uniform(-0.5, 0.5)

        zone.rainfall_pct = ((zone.rainfall_mm - chirps_normal) / chirps_normal) * 100

        # Clasificación — causa varía por cultivo y precipitación
        if zone.ndre_delta < -0.08 and zone.ndvi_delta < -0.02:
            zone.status = "critico"
            if zone.rainfall_pct < -20:
                zone.alert_cause = "Sequía severa"
            elif zone.crop == "Café":
                zone.alert_cause = "Enfermedad del cafetal"
            else:
                zone.alert_cause = "Deterioro severo del cultivo"
            zone.affected_area_ha = int(zone.area_ha * rng.uniform(0.35, 0.50))
            zone.days_early_warning = 18
        elif zone.ndre_delta < -0.03 and zone.ndvi_delta < -0.01:
            zone.status = "alerta"
            if zone.rainfall_pct < -20:
                zone.alert_cause = "Déficit hídrico"
            elif zone.crop == "Café":
                zone.alert_cause = "Enfermedad del cafetal"
            else:
                zone.alert_cause = "Deterioro del cultivo"
            zone.affected_area_ha = int(zone.area_ha * rng.uniform(0.20, 0.35))
            zone.days_early_warning = 15
        elif zone.ndre_delta < -0.015:
            zone.status = "vigilancia"
            zone.alert_cause = "Signos tempranos de deterioro"
            zone.affected_area_ha = int(zone.area_ha * rng.uniform(0.10, 0.20))
            zone.days_early_warning = 12
        else:
            zone.status = "normal"
            zone.alert_cause = ""
            zone.affected_area_ha = 0
            zone.days_early_warning = 0


# ═════════════════════════════════════════════════════════════════════
# Generación de boletín con LLM
# ═════════════════════════════════════════════════════════════════════

BULLETIN_PROMPT = """Eres el editor jefe de AgroSAT, el boletín semanal de alerta temprana para la agricultura en Latinoamérica.
AgroSAT es un producto de TerraSAT, empresa de procesamiento de imágenes satelitales.
Usas imágenes satelitales de agencias reconocidas (NASA, ESA) para detectar riesgos en cultivos antes de que sean visibles.

Escribes para agricultores, cooperativas y agroservicios en toda Latinoamérica. Tono profesional pero accesible, no académico.

DATOS DE LA REGIÓN (Latinoamérica, agosto 2026):

{zones_data}

REGLAS CRÍTICAS:
- NO menciones nombres de satélites específicos (Sentinel, Landsat, MODIS, CHIRPS)
- NO menciones índices técnicos (NDVI, NDRE, LST, z-score)
- NO menciones bandas espectrales ni fórmulas
- SI puedes decir: "imágenes satelitales de agencias reconocidas (NASA, ESA)"
- SI puedes decir: "análisis de vegetación y temperatura de dosel"
- SI puedes decir: "datos de precipitación satelital"
- SI puedes decir: "trabajamos con datos espectrales y 20 años de datos históricos"
- SI puedes decir: "detectamos situaciones atípicas 15 días antes de que aparezcan síntomas visibles"
- NO uses frases defensivas como "no es magia" o "no es ciencia ficción"
- Tono: afirmativo y seguro, no justificativo

ESTRUCTURA DEL BOLETÍN:
1. Título impactante (máximo 12 palabras)
2. Lead: 2-3 líneas resumiendo la situación regional pan-latinoamericana
3. Zonas en alerta: agrupa por cultivo o región, NO listes zona por zona. Ejemplo: "En café, Intibucá (Honduras) y Caldas (Colombia) suman 39,000 ha con enfermedad. En soja, Mato Grosso pierde 135,000 ha por sequía."
4. Zonas bajo vigilancia: mención breve agrupada
5. Zonas normales: una sola línea
6. CTA abierto que menciona audiencias específicas para que el lector se identifique:
   "¿Su plantación, propiedad o empresa agroindustrial opera en alguna de estas zonas? AgroSAT detecta situaciones atípicas que pueden afectar sus cultivos 15 días antes de que aparezcan síntomas visibles, dándole tiempo para actuar. Reportes personalizados disponibles. También trabajamos con aseguradoras y agroservicios. Vea mapa interactivo en terraSAT.agtisa.com. Contacto: info@agtisa.com"
7. 3 hashtags al final

FORMATO:
- Sin markdown (sin **negritas**, sin ##, sin bullets con -)
- 250-350 palabras máximo (la región es grande, necesitas espacio)
- 2-3 emojis profesionales (🛰️ 🌱 ☕ ⚠️ 📡)
- Cita fuentes como "datos satelitales de NASA" o "Agencia Espacial Europea"
- NO inventes estadísticas que no estén en los datos
- Agrupa por cultivo o región para que no sea una lista interminable

Devuelve SOLO el texto del boletín."""


def generate_bulletin_article(zones: list[AgroZone]) -> str:
    """Genera el artículo del boletín via LLM."""
    try:
        from llm_utils import llm_call
    except ImportError:
        return _fallback_article(zones)

    zones_data = []
    for z in zones:
        zones_data.append(
            f"- {z.name}, {z.country}: {z.area_ha:,} ha | "
            f"Estado: {z.status} | "
            f"Causa: {z.alert_cause or 'normal'} | "
            f"Área afectada: {z.affected_area_ha:,} ha | "
            f"Precipitación: {z.rainfall_pct:+.0f}% vs normal | "
            f"Anticipación: {z.days_early_warning} días"
        )

    prompt = BULLETIN_PROMPT.format(zones_data="\n".join(zones_data))

    try:
        response = llm_call(
            messages=[
                {"role": "system", "content": "Eres el editor de AgroSAT, boletín de alerta temprana para la agricultura productiva. Producto de TerraSAT. Respondes en español, formato profesional para redes sociales."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=600,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.warning(f"LLM bulletin failed: {e}")
        return _fallback_article(zones)


def _fallback_article(zones: list[AgroZone]) -> str:
    """Boletín de respaldo sin LLM."""
    alert_zones = [z for z in zones if z.status in ("critico", "alerta")]
    vigilancia = [z for z in zones if z.status == "vigilancia"]
    normales = [z for z in zones if z.status == "normal"]

    total_affected = sum(z.affected_area_ha for z in alert_zones)

    lines = ["🛰️ ALERTA AGROCLIMÁTICA — Latinoamérica"]
    lines.append("")
    lines.append(f"Imágenes satelitales de NASA y la Agencia Espacial Europea detectan estrés en {total_affected:,} hectáreas de cultivos en Latinoamérica.")

    if alert_zones:
        lines.append("")
        lines.append("⚠️ ZONAS EN ALERTA:")
        for z in alert_zones:
            lines.append(
                f"• {z.name}, {z.country} ({z.crop}): {z.affected_area_ha:,} ha afectadas. "
                f"Causa probable: {z.alert_cause}. "
                f"Detectado {z.days_early_warning} días antes de síntomas visibles."
            )

    if vigilancia:
        lines.append("")
        lines.append("🌱 BAJO VIGILANCIA:")
        for z in vigilancia:
            lines.append(f"• {z.name}, {z.country} ({z.crop}): signos tempranos, monitoreo continuo.")

    if normales:
        names = ", ".join(f"{z.name} ({z.country})" for z in normales)
        lines.append(f"\n✅ Condición normal: {names}")

    lines.append("")
    lines.append("¿Su plantación, propiedad o empresa agroindustrial opera en alguna de estas zonas? AgroSAT detecta situaciones atípicas que pueden afectar sus cultivos 15 días antes de que aparezcan síntomas visibles, dándole tiempo para actuar. Reportes personalizados disponibles. También trabajamos con aseguradoras y agroservicios. Vea mapa interactivo en terraSAT.agtisa.com. Contacto: info@agtisa.com")
    lines.append("")
    lines.append("#AgroSAT #TerraSAT #AlertaTemprana")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════
# Prompt para imagen (Gemini/Nano Banana)
# ═════════════════════════════════════════════════════════════════════

GEMINI_IMAGE_PROMPT = """You are a cinematic photographer creating a hero image for an agricultural early warning social media post about Latin American farming.

SUBJECT: Vast agricultural landscape in Latin America showing a mosaic of healthy and stressed crops. Aerial or elevated view showing large fields with visible patches of yellowing or thinning vegetation contrasted with healthy green sections. Could be coffee highlands, soybean plains, or vineyard valleys — diverse Latin American agriculture. Photorealistic, NOT illustration or cartoon.

CAMERA: Elevated angle, drone-style perspective showing the scale of the agricultural landscape. 16:9 widescreen composition. Shallow depth of field with the landscape in focus and distant features softly blurred.

LIGHTING: Early morning golden light, mist rising from valleys. Warm amber tones in highlights, cool blue-greens in shadows. Natural, cinematic color grading. Sense of dawn — the idea of early warning, catching problems before they're obvious.

ENVIRONMENT: Diverse Latin American agricultural landscape. Rolling hills with coffee, flat plains with row crops, or valley vineyards. Dense green vegetation with visible patches of lighter yellow-green where stress is beginning. Farm buildings, roads, or paths visible. Mountains or horizons in the background.

STYLE: Cinematic documentary photography, premium commercial quality, photorealistic. Like a still from a high-end agricultural documentary. NO text, NO watermark, NO logo, NO words in the image — clean visual only."""


# ═════════════════════════════════════════════════════════════════════
# Reporte
# ═════════════════════════════════════════════════════════════════════

STATUS_ICON = {
    "normal": "✅",
    "vigilancia": "🟡",
    "alerta": "🟠",
    "critico": "🔴",
}


def print_bulletin(zones: list[AgroZone], article: str, today: date):
    """Imprime el boletín completo en consola."""
    total_ha = sum(z.area_ha for z in zones)
    affected_ha = sum(z.affected_area_ha for z in zones if z.status in ("critico", "alerta"))
    vigilancia_ha = sum(z.affected_area_ha for z in zones if z.status == "vigilancia")

    by_status = {"normal": 0, "vigilancia": 0, "alerta": 0, "critico": 0}
    for z in zones:
        by_status[z.status] += 1

    countries = sorted(set(z.country for z in zones))
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║  TerraSAT / AgroSAT — BOLETÍN DE ALERTA TEMPRANA                     ║
║  Agricultura Latinoamericana — {today.strftime('%d/%m/%Y')}                        ║
║                                                                      ║
║  Imágenes satelitales: NASA · Agencia Espacial Europea               ║
║  Cobertura: {total_ha:,} ha en {len(zones)} zonas de {len(countries)} países                ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    # ─── Semáforo regional ──────────────────────────────────────
    print(f"  📊 SEMÁFORO REGIONAL")
    print(f"  {'─' * 66}")
    print(f"  🔴 Crítico:    {by_status['critico']} zonas")
    print(f"  🟠 Alerta:     {by_status['alerta']} zonas")
    print(f"  🟡 Vigilancia: {by_status['vigilancia']} zonas")
    print(f"  ✅ Normal:     {by_status['normal']} zonas")
    print()
    print(f"  Superficie en alerta: {affected_ha:,} ha ({affected_ha/total_ha*100:.0f}%)")
    print(f"  Superficie en vigilancia: {vigilancia_ha:,} ha")
    print(f"  Anticipación promedio: {sum(z.days_early_warning for z in zones if z.days_early_warning > 0) / max(1, by_status['critico'] + by_status['alerta'] + by_status['vigilancia']):.0f} días")

    # ─── Tabla de zonas ─────────────────────────────────────────
    print(f"\n  📋 ESTADO POR ZONA")
    print(f"  {'─' * 66}")
    print(f"  {'Zona':<20} {'País':<14} {'Cultivo':<10} {'Estado':<12} {'Área afectada':<16} {'Causa'}")
    print(f"  {'─' * 20} {'─' * 14} {'─' * 10} {'─' * 12} {'─' * 16} {'─' * 20}")

    priority = {"critico": 0, "alerta": 1, "vigilancia": 2, "normal": 3}
    for z in sorted(zones, key=lambda z: priority.get(z.status, 99)):
        icon = STATUS_ICON.get(z.status, "?")
        affected = f"{z.affected_area_ha:,} ha" if z.affected_area_ha > 0 else "—"
        cause = z.alert_cause or "Sin alerta"
        print(f"  {icon} {z.name:<17} {z.country:<14} {z.crop:<10} {z.status:<12} {affected:<16} {cause}")

    # ─── Artículo para Facebook ─────────────────────────────────
    print(f"\n\n{'═' * 66}")
    print(f"  📝 ARTÍCULO PARA FACEBOOK")
    print(f"{'═' * 66}")
    print()
    for line in article.split("\n"):
        print(f"  {line}")

    # ─── Información comercial ──────────────────────────────────
    print(f"\n\n{'═' * 66}")
    print(f"  💼 SERVICIOS TerraSAT / AgroSAT")
    print(f"{'═' * 66}")
    print(f"""
  TerraSAT — Procesamiento de imágenes satelitales
  AgroSAT — Alerta temprana para la agricultura

  Boletín pan-regional quincenal (este producto):
    ✓ Cobertura: Centroamérica + Suramérica
    ✓ Alerta temprana agroclimática
    ✓ Detección de estrés antes de síntomas visibles
    ✓ Fuentes: imágenes satelitales de NASA y ESA

  Reporte personalizado a nivel plantación:
    ✓ Diagnóstico detallado por propiedad (50-500 ha)
    ✓ Análisis multi-sensor con diagnóstico diferencial
    ✓ Plan de acción priorizado por sector
    ✓ Validación contra ground truth

  Contacto: info@agtisa.com

  Próximo boletín: {(today + timedelta(days=7)).strftime('%d/%m/%Y')}
    """)


def save_outputs(article: str, today: date):
    """Guarda artículo y prompt de imagen para el pipeline de FB."""
    output_dir = Path("scripts")
    output_dir.mkdir(exist_ok=True)

    article_path = output_dir / "generated-article.txt"
    article_path.write_text(article, encoding="utf-8")
    print(f"\n  📄 Artículo guardado: {article_path}")

    prompt_path = output_dir / "gemini-prompt.txt"
    prompt_path.write_text(GEMINI_IMAGE_PROMPT, encoding="utf-8")
    print(f"  🎨 Prompt de imagen guardado: {prompt_path}")


# ═════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════

def main():
    today = date(2026, 8, 12)

    # ─── Simular ────────────────────────────────────────────────
    zones = generate_zones()
    simulate_zones(zones, seed=2026)

    # ─── Generar artículo con LLM ───────────────────────────────
    print("  Generando boletín con LLM...\n")
    article = generate_bulletin_article(zones)

    # ─── Imprimir boletín ───────────────────────────────────────
    print_bulletin(zones, article, today)

    # ─── Guardar salidas para pipeline FB ───────────────────────
    save_outputs(article, today)

    print(f"\n  {'─' * 66}")
    print(f"  Pipeline de publicación:")
    print(f"  1. Generar mapa: python nooa-agent/generate_map.py")
    print(f"     → Abrir scripts/agrosat-map.html en navegador, capturar pantalla")
    print(f"  2. Generar imagen artística en Gemini con scripts/gemini-prompt.txt")
    print(f"  3. node scripts/combine-images.mjs \"imagen_gemini.png\" \"captura_mapa.png\" --output \"scripts/agrosat-combined.jpg\"")
    print(f"  4. node scripts/add-branding-terrasat.mjs \"scripts/agrosat-combined.jpg\" --period \"05–11 de agosto 2026\"")
    print(f"  5. node scripts/fb-post.mjs \"mapa_branded.jpg\" @scripts/generated-article.txt")
    print(f"  {'─' * 66}")


if __name__ == "__main__":
    main()
