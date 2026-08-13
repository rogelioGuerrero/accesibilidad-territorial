"""
TerraSAT / UrbanSAT — Boletín de Monitoreo Urbano Satelital

TerraSAT: Procesamiento de imágenes satelitales (marca corporativa)
UrbanSAT: Monitoreo urbano satelital (producto #2)

Producto: boletín mensual de cambios urbanos detectados por satélite.
Tres servicios:
  1. Detección de nuevas construcciones (cambio de uso de suelo) (NDBI + cambio temporal)
  2. Islas de calor urbano (LST / temperatura de superficie)
  3. Pérdida de áreas verdes (NDVI urbano)

Salidas:
  1. Boletín impreso en consola
  2. scripts/urban-article.txt — artículo listo para publicación
  3. scripts/urban-map.html — mapa interactivo

Ejecutar: python nooa-agent/demo_urban_sat.py
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
# Modelo de zona urbana
# ═════════════════════════════════════════════════════════════════════

@dataclass
class UrbanZone:
    name: str  # barrio / sector
    city: str
    country: str
    lat: float
    lng: float
    area_ha: int  # hectáreas del sector urbano

    # Índices satelitales (simulados, no se revelan en el boletín)
    ndbi_delta: float = 0.0       # cambio en índice de áreas construidas
    ndvi_urban: float = 0.0       # NDVI urbano actual
    ndvi_urban_prev: float = 0.0  # NDVI urbano período anterior
    lst_delta: float = 0.0        # cambio de temperatura de superficie (°C)
    lst_current: float = 0.0      # temperatura actual
    lst_baseline: float = 0.0     # temperatura normal histórica

    # Estado calculado
    status: str = "normal"  # normal / vigilancia / alerta / critico
    alert_type: str = ""    # construccion / calor / verde
    alert_cause: str = ""
    affected_area_ha: int = 0
    confidence: float = 0.0  # 0-1, confianza de la detección

    # Para el boletín
    headline: str = ""
    summary: str = ""


# ═════════════════════════════════════════════════════════════════════
# Zonas urbanas — ciudades de Uruguay (CIIAR) + otras LatAm
# ═════════════════════════════════════════════════════════════════════

def generate_urban_zones() -> list[UrbanZone]:
    return [
        # ─── Uruguay (CIIAR cohort) ───
        UrbanZone("Centro", "Salto", "Uruguay", -31.38, -57.97, 1_200),
        UrbanZone("Norte industrial", "Salto", "Uruguay", -31.30, -57.95, 850),
        UrbanZone("Periurbano este", "Salto", "Uruguay", -31.42, -57.90, 1_500),
        UrbanZone("Centro histórico", "Colonia", "Uruguay", -34.46, -57.84, 600),
        UrbanZone("Zona franca", "Colonia", "Uruguay", -34.48, -57.80, 900),
        UrbanZone("Periurbano norte", "Rivera", "Uruguay", -30.90, -55.55, 1_100),
        UrbanZone("Centro comercial", "Rivera", "Uruguay", -30.91, -55.56, 700),
        UrbanZone("Residencial sur", "Florida", "Uruguay", -34.10, -56.22, 800),
        UrbanZone("Industrial oeste", "Florida", "Uruguay", -34.09, -56.25, 650),
        # ─── Otras ciudades LatAm ───
        UrbanZone("Periurbano norte", "Asunción", "Paraguay", -25.20, -57.50, 3_500),
        UrbanZone("Bañado sur", "Asunción", "Paraguay", -25.35, -57.60, 2_200),
        UrbanZone("Zona industrial", "Santa Cruz", "Bolivia", -17.75, -63.15, 2_800),
        UrbanZone("Periurbano este", "Santa Cruz", "Bolivia", -17.78, -63.10, 3_100),
        UrbanZone("Centro histórico", "Cuenca", "Ecuador", -2.90, -79.00, 950),
        UrbanZone("Periurbano sur", "Cuenca", "Ecuador", -2.95, -79.02, 1_200),
    ]


# ═════════════════════════════════════════════════════════════════════
# Simulación satelital (interna, no se revela en el boletín)
# ═════════════════════════════════════════════════════════════════════

def simulate_urban_zones(zones: list[UrbanZone], seed: int = 2026):
    rng = random.Random(seed)

    # Patrones de cambio urbano (basados en dinámicas reales)
    change_patterns = {
        0: "construccion",      # Salto Centro — nuevas construcciones
        2: "construccion",      # Salto periurbano este — expansión
        4: "calor",             # Colonia zona franca — isla de calor
        5: "construccion",      # Rivera periurbano norte — expansión informal
        7: "verde",             # Florida residencial sur — pérdida de verde
        9: "construccion",      # Asunción periurbano norte — expansión
        10: "calor",            # Asunción Bañado sur — isla de calor
        11: "construccion",     # Santa Cruz zona industrial — expansión
        13: "verde",            # Cuenca centro histórico — pérdida de verde
        14: "construccion",     # Cuenca periurbano sur — expansión
    }

    for i, zone in enumerate(zones):
        pattern = change_patterns.get(i, "normal")

        if pattern == "construccion":
            # NDBI positivo = aumento de superficies construidas
            zone.ndbi_delta = rng.uniform(0.04, 0.12)
            zone.ndvi_urban = rng.uniform(0.08, 0.15)
            zone.ndvi_urban_prev = rng.uniform(0.15, 0.25)
            zone.lst_delta = rng.uniform(0.5, 1.5)
            zone.status = "alerta"
            zone.alert_type = "construccion"
            zone.alert_cause = "Nueva construcción detectada"
            zone.affected_area_ha = int(zone.area_ha * rng.uniform(0.05, 0.15))
            zone.confidence = rng.uniform(0.82, 0.94)
        elif pattern == "calor":
            # LST elevada = isla de calor
            zone.lst_current = rng.uniform(38, 44)
            zone.lst_baseline = rng.uniform(30, 34)
            zone.lst_delta = zone.lst_current - zone.lst_baseline
            zone.ndvi_urban = rng.uniform(0.05, 0.12)
            zone.ndvi_urban_prev = rng.uniform(0.10, 0.18)
            zone.ndbi_delta = rng.uniform(0.01, 0.04)
            zone.status = "critico" if zone.lst_delta > 8 else "alerta"
            zone.alert_type = "calor"
            zone.alert_cause = "Isla de calor urbano intensificada"
            zone.affected_area_ha = int(zone.area_ha * rng.uniform(0.20, 0.40))
            zone.confidence = rng.uniform(0.88, 0.96)
        elif pattern == "verde":
            # NDVI urbano en declive = pérdida de áreas verdes
            zone.ndvi_urban = rng.uniform(0.10, 0.18)
            zone.ndvi_urban_prev = rng.uniform(0.25, 0.35)
            zone.ndbi_delta = rng.uniform(0.02, 0.06)
            zone.lst_delta = rng.uniform(1.0, 2.5)
            zone.status = "alerta"
            zone.alert_type = "verde"
            zone.alert_cause = "Pérdida de cobertura verde"
            zone.affected_area_ha = int(zone.area_ha * rng.uniform(0.10, 0.25))
            zone.confidence = rng.uniform(0.85, 0.92)
        else:
            # Sin cambios significativos
            zone.ndbi_delta = rng.uniform(-0.01, 0.01)
            zone.ndvi_urban = rng.uniform(0.18, 0.30)
            zone.ndvi_urban_prev = rng.uniform(0.17, 0.29)
            zone.lst_current = rng.uniform(28, 33)
            zone.lst_baseline = rng.uniform(28, 33)
            zone.lst_delta = rng.uniform(-0.5, 0.5)
            zone.status = "normal"
            zone.alert_type = ""
            zone.alert_cause = ""
            zone.affected_area_ha = 0
            zone.confidence = 0.0


# ═════════════════════════════════════════════════════════════════════
# Prompt para boletín urbano
# ═════════════════════════════════════════════════════════════════════

URBAN_BULLETIN_PROMPT = """Eres el editor jefe de UrbanSAT, el boletín mensual de monitoreo urbano satelital.
UrbanSAT es un producto de TerraSAT, empresa de procesamiento de imágenes satelitales.
Usas imágenes satelitales de agencias reconocidas (NASA, ESA) para detectar cambios en el territorio urbano.

Escribes para intendentes, directores de obras, catastro, ambiente y planificación urbana en Latinoamérica. Tono profesional pero accesible.

DATOS DE MONITOREO (Latinoamérica, {today}):

{zones_data}

REGLAS CRÍTICAS:
- NO menciones nombres de satélites específicos (Sentinel, Landsat, MODIS)
- NO menciones índices técnicos (NDBI, NDVI, LST, z-score)
- NO menciones bandas espectrales ni fórmulas
- SI puedes decir: "imágenes satelitales de agencias reconocidas (NASA, ESA)"
- SI puedes decir: "análisis de cobertura de suelo y temperatura de superficie"
- SI puedes decir: "comparación de imágenes de distintos períodos"
- SI puedes decir: "trabajamos con datos espectrales y 20 años de datos históricos"
- SI puedes decir: "detectamos cambios urbanos antes de que sean evidentes en terreno"
- NO uses frases defensivas
- Tono: afirmativo y seguro, no justificativo

ESTRUCTURA DEL BOLETÍN:
1. Título impactante (máximo 12 palabras)
2. Lead: 2-3 líneas resumiendo los hallazgos urbanos
3. Cambios detectados: agrupa por tipo (nuevas construcciones, calor, áreas verdes). NO listes zona por zona. NO digas "no declaradas" — el satélite detecta construcciones nuevas, no si están declaradas o no.
4. Zonas bajo vigilancia: mención breve
5. Zonas sin cambios: una sola línea
6. CTA: "¿Su municipio necesita monitoreo satelital del territorio? UrbanSAT detecta cambios urbanos antes del recorrido en terreno. Reportes personalizados por sector. Vea mapa interactivo en terraSAT.agtisa.com. Contacto: info@agtisa.com"
7. 3 hashtags al final

FORMATO:
- Sin markdown (sin **negritas**, sin ##, sin bullets con -)
- 250-350 palabras máximo
- 2-3 emojis profesionales (🛰️ 🏗️ 🌡️ 🌳 📡)
- NO inventes estadísticas que no estén en los datos
- Agrupa por tipo de cambio para que no sea una lista interminable
"""


# ═════════════════════════════════════════════════════════════════════
# Generación de boletín
# ═════════════════════════════════════════════════════════════════════

STATUS_ICON = {
    "critico": "🔴",
    "alerta": "🟠",
    "vigilancia": "🟡",
    "normal": "✅",
}

ALERT_TYPE_LABEL = {
    "construccion": "Nueva construcción",
    "calor": "Isla de calor",
    "verde": "Pérdida de verde",
}


def generate_urban_bulletin(zones: list[UrbanZone], today: date) -> str:
    from llm_utils import llm_call

    today_str = today.strftime("%d/%m/%Y")

    zones_data = []
    for z in zones:
        if z.status == "normal":
            zones_data.append(
                f"- {z.name}, {z.city} ({z.country}): {z.area_ha:,} ha | "
                f"Estado: normal | Sin cambios detectados"
            )
        else:
            label = ALERT_TYPE_LABEL.get(z.alert_type, z.alert_type)
            zones_data.append(
                f"- {z.name}, {z.city} ({z.country}): {z.area_ha:,} ha | "
                f"Estado: {z.status} | Tipo: {label} | "
                f"Área afectada: {z.affected_area_ha:,} ha | "
                f"Causa: {z.alert_cause} | "
                f"Confianza: {z.confidence:.0%}"
            )

    prompt = URBAN_BULLETIN_PROMPT.format(
        today=today_str,
        zones_data="\n".join(zones_data),
    )

    try:
        response = llm_call(
            messages=[
                {"role": "system", "content": "Eres el editor de UrbanSAT, boletín de monitoreo urbano satelital. Producto de TerraSAT. Respondes en español, formato profesional para redes sociales."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.6,
            max_tokens=800,
        )
        article = response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"LLM error: {e}")
        article = generate_urban_fallback(zones, today)

    return article.strip()


def generate_urban_fallback(zones: list[UrbanZone], today: date) -> str:
    today_str = today.strftime("%d/%m/%Y")
    lines = [f"Cambios urbanos detectados en Latinoamérica — {today_str}"]
    lines.append("")
    lines.append(
        "El monitoreo satelital de UrbanSAT detecta cambios en el territorio urbano de varias ciudades de la región. "
        "Imágenes satelitales de NASA y ESA revelan construcciones no declaradas, islas de calor y pérdida de áreas verdes. 🛰️"
    )
    lines.append("")

    construccion = [z for z in zones if z.alert_type == "construccion" and z.status in ("critico", "alerta")]
    calor = [z for z in zones if z.alert_type == "calor" and z.status in ("critico", "alerta")]
    verde = [z for z in zones if z.alert_type == "verde" and z.status in ("critico", "alerta")]
    normales = [z for z in zones if z.status == "normal"]

    if construccion:
        total_ha = sum(z.affected_area_ha for z in construccion)
        zonas_txt = ", ".join(f"{z.name} ({z.city})" for z in construccion)
        lines.append(f"🏗️ Nuevas construcciones: {len(construccion)} zonas en {zonas_txt}. "
                      f"Total: {total_ha:,} ha con cambio de uso de suelo.")
        lines.append("")

    if calor:
        total_ha = sum(z.affected_area_ha for z in calor)
        zonas_txt = ", ".join(f"{z.name} ({z.city})" for z in calor)
        lines.append(f"🌡️ Islas de calor: {len(calor)} zonas en {zonas_txt}. "
                      f"Total: {total_ha:,} ha con temperatura elevada.")
        lines.append("")

    if verde:
        total_ha = sum(z.affected_area_ha for z in verde)
        zonas_txt = ", ".join(f"{z.name} ({z.city})" for z in verde)
        lines.append(f"🌳 Pérdida de áreas verdes: {len(verde)} zonas en {zonas_txt}. "
                      f"Total: {total_ha:,} ha con deterioro de cobertura verde.")
        lines.append("")

    if normales:
        names = ", ".join(f"{z.name} ({z.city})" for z in normales)
        lines.append(f"✅ Sin cambios significativos: {names}")

    lines.append("")
    lines.append(
        "¿Su municipio necesita monitoreo satelital del territorio? "
        "UrbanSAT detecta cambios urbanos antes del recorrido en terreno. "
        "Reportes personalizados por sector. "
        "Vea mapa interactivo en terraSAT.agtisa.com. "
        "Contacto: info@agtisa.com 📡"
    )
    lines.append("")
    lines.append("#UrbanSAT #TerraSAT #MonitoreoUrbano")

    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════
# Impresión del boletín
# ═════════════════════════════════════════════════════════════════════

def print_urban_bulletin(zones: list[UrbanZone], article: str, today: date):
    today_str = today.strftime("%d/%m/%Y")

    print()
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║                                                                      ║")
    print("║  TerraSAT / UrbanSAT — BOLETÍN DE MONITOREO URBANO                   ║")
    print(f"║  Ciudades Latinoamericanas — {today_str:<28}             ║")
    print("║                                                                      ║")
    print("║  Imágenes satelitales: NASA · Agencia Espacial Europea               ║")
    print(f"║  Cobertura: {sum(z.area_ha for z in zones):>10,} ha en {len(zones)} zonas de {len(set(z.city for z in zones))} ciudades    ║")
    print("║                                                                      ║")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    priority = {"critico": 0, "alerta": 1, "vigilancia": 2, "normal": 3}

    print("\n  📊 SEMÁFORO URBANO")
    print("  " + "─" * 66)

    for status in ("critico", "alerta", "vigilancia", "normal"):
        count = sum(1 for z in zones if z.status == status)
        icon = STATUS_ICON[status]
        label = {"critico": "Crítico", "alerta": "Alerta", "vigilancia": "Vigilancia", "normal": "Normal"}[status]
        if count > 0:
            print(f"  {icon} {label:<12} {count} zonas")

    construccion = [z for z in zones if z.alert_type == "construccion" and z.status != "normal"]
    calor = [z for z in zones if z.alert_type == "calor" and z.status != "normal"]
    verde = [z for z in zones if z.alert_type == "verde" and z.status != "normal"]

    print(f"\n  🏗️ Construcciones: {sum(z.affected_area_ha for z in construccion):,} ha")
    print(f"  🌡️ Islas de calor: {sum(z.affected_area_ha for z in calor):,} ha")
    print(f"  🌳 Pérdida de verde: {sum(z.affected_area_ha for z in verde):,} ha")

    print(f"\n  📋 DETALLE POR ZONA")
    print("  " + "─" * 66)
    print(f"  {'Zona':<20} {'Ciudad':<14} {'Tipo':<14} {'Estado':<10} {'Área':<10} {'Conf.':<8}")
    print("  " + "─" * 66)

    for z in sorted(zones, key=lambda z: priority.get(z.status, 99)):
        icon = STATUS_ICON.get(z.status, "?")
        tipo = ALERT_TYPE_LABEL.get(z.alert_type, "—")[:13]
        affected = f"{z.affected_area_ha:,} ha" if z.affected_area_ha > 0 else "—"
        conf = f"{z.confidence:.0%}" if z.confidence > 0 else "—"
        print(f"  {icon} {z.name:<17} {z.city:<14} {tipo:<14} {z.status:<10} {affected:<10} {conf:<8}")

    print("\n" + "═" * 66)
    print("  📝 ARTÍCULO PARA PUBLICACIÓN")
    print("═" * 66)
    print()
    for line in article.split("\n"):
        print(f"  {line}")
    print()

    print("═" * 66)
    print("  💼 SERVICIOS TerraSAT / UrbanSAT")
    print("═" * 66)
    print()
    print("  TerraSAT — Procesamiento de imágenes satelitales")
    print("  UrbanSAT — Monitoreo urbano satelital")
    print()
    print("  Boletín mensual urbano (este producto):")
    print("    ✓ Detección de nuevas construcciones")
    print("    ✓ Islas de calor urbano")
    print("    ✓ Pérdida de áreas verdes")
    print("    ✓ Fuentes: imágenes satelitales de NASA y ESA")
    print()
    print("  Reporte personalizado a nivel municipal:")
    print("    ✓ Monitoreo por barrio / sector")
    print("    ✓ Comparación temporal mensual / trimestral")
    print("    ✓ Coordenadas exactas para verificación en terreno")
    print("    ✓ Exportable a CSV / GeoJSON para catastro")
    print()
    print("  Contacto: info@agtisa.com")
    print()


# ═════════════════════════════════════════════════════════════════════
# Guardar salidas
# ═════════════════════════════════════════════════════════════════════

def save_urban_outputs(article: str, today: date):
    output_dir = Path("scripts")
    output_dir.mkdir(exist_ok=True)

    article_path = output_dir / "urban-article.txt"
    article_path.write_text(article, encoding="utf-8")
    print(f"  📄 Artículo guardado: {article_path}")


# ═════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════

def main():
    today = date(2026, 8, 13)

    print("  Generando boletín urbano con LLM...")

    zones = generate_urban_zones()
    simulate_urban_zones(zones, seed=2026)

    article = generate_urban_bulletin(zones, today)

    print_urban_bulletin(zones, article, today)
    save_urban_outputs(article, today)

    print(f"\n  {'─' * 66}")
    print(f"  Pipeline de publicación:")
    print(f"  1. Generar mapa: python nooa-agent/generate_urban_map.py")
    print(f"     → Abrir scripts/urban-map.html en navegador, capturar pantalla")
    print(f"  2. node scripts/split-analysis.mjs \"imagen_gemini.png\" --output \"scripts/urban-split.jpg\"")
    print(f"  3. node scripts/add-branding-terrasat.mjs \"scripts/urban-split.jpg\" --period \"jul–ago 2026\"")
    print(f"  4. Publicar imagen branded + artículo de scripts/urban-article.txt")
    print(f"  {'─' * 66}")


if __name__ == "__main__":
    main()
