"""
TerraSAT / AgroSAT — Validación externa opcional del boletín

Busca en la web noticias recientes sobre cada zona en alerta y las presenta
junto a lo que dice el script. El humano decide si publicar o ajustar.

No bloquea la publicación. Solo da contexto.

Uso: uv run python nooa-agent/validate_bulletin.py
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(level=logging.WARNING)

from demo_alerta_temprana_regional import generate_zones, simulate_zones


def validate_with_web(zones) -> list[dict]:
    """Busca en la web noticias recientes por cada zona en alerta."""
    try:
        from llm_utils import llm_call
    except ImportError:
        print("No se pudo importar llm_utils. Validación omitida.")
        return []

    alert_zones = [z for z in zones if z.status in ("critico", "alerta", "vigilancia")]
    results = []

    for z in alert_zones:
        query = (
            f"Busca noticias recientes (2026) sobre {z.alert_cause or 'problemas agrícolas'} "
            f"en {z.name}, {z.country}. Específicamente sobre {z.crop}. "
            f"¿Hay reportes oficiales, noticias, o boletines de ministerios de agricultura "
            f"que confirmen o contradigan esta situación? "
            f"Responde en español, sé conciso (máximo 3 líneas). "
            f"Si no encuentras nada, di 'Sin reportes encontrados'."
        )

        try:
            response = llm_call(
                messages=[
                    {"role": "system", "content": "Eres un asistente de investigación agrícola. Buscas información factual en la web y respondes en español."},
                    {"role": "user", "content": query},
                ],
                temperature=0.3,
                max_tokens=200,
            )
            web_finding = response.choices[0].message.content.strip()
        except Exception as e:
            web_finding = f"Error en búsqueda: {e}"

        results.append({
            "zone": z,
            "web_finding": web_finding,
        })

    return results


def print_validation(results: list[dict], today: date):
    """Imprime el reporte de validación para el humano."""
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║  TerraSAT / AgroSAT — VALIDACIÓN EXTERNA (INTERNA)                   ║
║  {today.strftime('%d/%m/%Y')} — Decisiones del editor                       ║
║                                                                      ║
║  Este reporte NO bloquea la publicación.                             ║
║  Solo presenta contexto para que el humano decida.                   ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
    """)

    if not results:
        print("  No hay zonas en alerta para validar.")
        return

    for r in results:
        z = r["zone"]
        web = r["web_finding"]

        # Determinar si la web confirma, contradice, o es neutral
        web_lower = web.lower()
        if "sin reportes" in web_lower or "no se encontr" in web_lower:
            verdict = "⚪ SIN INFO"
        elif any(w in web_lower for w in ["confirm", "sí", "si hay", "reporte", "según"]):
            verdict = "🟢 CONFIRMA"
        elif any(w in web_lower for w in ["contradic", "no hay", "lluvia", "normal", "sin problema"]):
            verdict = "🔴 CONTRADICE"
        else:
            verdict = "🟡 NEUTRAL"

        print(f"\n  {'─' * 66}")
        print(f"  {verdict}  {z.name}, {z.country} ({z.crop})")
        print(f"  {'─' * 66}")
        print(f"  📡 SCRIPT DICE:")
        print(f"     Estado: {z.status} | {z.affected_area_ha:,} ha | {z.alert_cause}")
        print(f"     Anticipación: {z.days_early_warning} días")
        print(f"  🌐 WEB DICE:")
        for line in web.split("\n"):
            print(f"     {line}")

    print(f"\n  {'═' * 66}")
    print(f"  ⚪ SIN INFO = nadie reporta, pero tu satélite sí ve algo. Publica con confianza.")
    print(f"  🟢 CONFIRMA = fuentes externas validan. Publica sin duda.")
    print(f"  🟡 NEUTRAL = info ambigua. Revisa antes de publicar.")
    print(f"  🔴 CONTRADICE = algo no cuadra. Investiga antes de publicar.")
    print(f"  {'═' * 66}")


def main():
    today = date(2026, 8, 12)

    zones = generate_zones()
    simulate_zones(zones, seed=2026)

    print("  Buscando validación externa en la web...\n")
    results = validate_with_web(zones)

    print_validation(results, today)


if __name__ == "__main__":
    main()
