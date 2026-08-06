"""
Script para descargar matriz real de ORS y guardarla en JSON.
Uso: uv run python scripts/fetch_ors_matrix.py

Genera:
  tests/fixtures/coords_madrid_15.json   — coordenadas de los puntos
  tests/fixtures/matrix_madrid_15.json   — matriz ORS real (distancias + duraciones)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Asegurar que el paquete es importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
from vrp_solver.matrix import ORSMatrixProvider

load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════
# 15 PUNTOS REALES EN MADRID
# Coords en formato [lat, lng] — el backend las usa así
# ═══════════════════════════════════════════════════════════════════════════

COORDS_MADRID_15 = [
    # Depósito — centro logístico
    (40.4168, -3.7038),   # 0: Puerta del Sol (depósito)

    # Entregas — distribuidas por Madrid
    (40.4470, -3.6700),   # 1: Barrio Salamanca
    (40.4300, -3.7100),   # 2: Gran Vía
    (40.4000, -3.7200),   # 3: Lavapiés
    (40.3800, -3.6700),   # 4: Vallecas
    (40.4500, -3.6900),   # 5: Chamberí
    (40.3900, -3.7400),   # 6: Carabanchel
    (40.4700, -3.6800),   # 7: Tetuán
    (40.4100, -3.6500),   # 8: Retiro
    (40.3700, -3.7100),   # 9: Usera
    (40.4600, -3.7100),   # 10: Moncloa
    (40.3900, -3.6800),   # 11: Embajadores
    (40.4350, -3.7350),   # 12: Malasaña
    (40.4200, -3.6900),   # 13: Atocha
    (40.4400, -3.7300),   # 14: Argüelles
]

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"


def main() -> None:
    api_key = os.getenv("ORS_API_KEY")
    if not api_key:
        print("ERROR: ORS_API_KEY no configurada en .env")
        sys.exit(1)

    print(f"Descargando matriz ORS para {len(COORDS_MADRID_15)} puntos...")

    provider = ORSMatrixProvider(api_key=api_key)
    matrix = provider.compute(COORDS_MADRID_15)

    # Guardar coordenadas
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    coords_path = FIXTURES_DIR / "coords_madrid_15.json"
    with open(coords_path, "w") as f:
        json.dump({
            "description": "15 puntos reales en Madrid (1 depósito + 14 entregas)",
            "coords": COORDS_MADRID_15,
            "coord_format": "[lat, lng]",
        }, f, indent=2)
    print(f"Coordenadas guardadas: {coords_path}")

    # Guardar matriz
    matrix_path = FIXTURES_DIR / "matrix_madrid_15.json"
    with open(matrix_path, "w") as f:
        json.dump({
            "description": "Matriz ORS real (driving-car) para 15 puntos en Madrid",
            "n": matrix.n,
            "distances": matrix.distances,
            "durations": matrix.durations,
            "units": {"distance": "meters", "duration": "seconds"},
        }, f, indent=2)
    print(f"Matriz guardada: {matrix_path}")

    # Resumen
    print(f"\nResumen:")
    print(f"  Puntos: {matrix.n}")
    print(f"  Distancia min: {min(min(row) for row in matrix.distances)} m")
    print(f"  Distancia max: {max(max(row) for row in matrix.distances)} m")
    print(f"  Duración min: {min(min(row) for row in matrix.durations)} s")
    print(f"  Duración max: {max(max(row) for row in matrix.durations)} s")
    print(f"\nListo. Los tests pueden usar CachedMatrixProvider ahora.")


if __name__ == "__main__":
    main()
