"""
Tests de integración del demo endpoint.
Valida que los casos del demo ejecutan correctamente el solver y devuelven
datos consistentes para la visualización.

Ejecutar: $env:PYTHONPATH = "src"; python -m pytest tests/test_demo.py -v
"""

import pytest
from fastapi.testclient import TestClient

from vrp_solver.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestDemoHTML:
    """El endpoint /demo devuelve HTML válido."""

    def test_demo_index_returns_html(self, client):
        resp = client.get("/demo")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "leaflet" in resp.text.lower()


class TestDemoCases:
    """Cada caso del demo debe ejecutar sin errores y devolver datos válidos."""

    CASE_IDS = [
        "basic",
        "multi-vehicle",
        "multi-depot",
        "time-windows",
        "backlog",
        "pickup-delivery",
        "skills",
        "breaks",
    ]

    @pytest.mark.parametrize("case_id", CASE_IDS)
    def test_case_returns_valid_json(self, client, case_id):
        """Cada caso debe devolver JSON con las claves esperadas."""
        resp = client.get(f"/demo/{case_id}")
        assert resp.status_code == 200
        data = resp.json()

        # No debe haber errores del solver
        assert data.get("errors") == [], f"Caso {case_id} tiene errores: {data.get('errors')}"

        # Debe tener las claves obligatorias
        assert "case_id" in data
        assert "routes" in data
        assert "statistics" in data
        assert "depots" in data
        assert data["case_id"] == case_id

        # Si hay rutas, deben tener stops y distancia
        for route in data["routes"]:
            assert len(route["stops"]) >= 2, f"Ruta de {case_id} tiene < 2 stops"
            assert route["total_distance"] >= 0

    def test_unknown_case_returns_error(self, client):
        """Caso inexistente debe devolver error."""
        resp = client.get("/demo/nonexistent")
        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data


class TestCostComparison:
    """El caso multi-depot debe incluir comparación de costos."""

    def test_multi_depot_has_cost_comparison(self, client):
        resp = client.get("/demo/multi-depot")
        assert resp.status_code == 200
        data = resp.json()

        # El caso multi-depot usa optimize_by=cost
        assert data.get("cost_comparison") is not None, "multi-depot debe tener cost_comparison"
        cmp = data["cost_comparison"]
        assert "cost_by_distance" in cmp
        assert "cost_by_cost" in cmp
        assert "savings" in cmp
        assert "savings_pct" in cmp

    def test_multi_depot_vehicle_costs_present(self, client):
        """El demo debe incluir configuración de costos por vehículo."""
        resp = client.get("/demo/multi-depot")
        data = resp.json()
        assert "vehicle_costs" in data
        assert len(data["vehicle_costs"]) > 0
        for vc in data["vehicle_costs"]:
            assert "fixed_cost" in vc
            assert "cost_per_km" in vc
            assert "cost_per_hour" in vc
            assert "cost_per_stop" in vc


class TestCostReporting:
    """Las rutas deben incluir desglose de costos cuando hay costos configurados."""

    def test_routes_have_cost_breakdown(self, client):
        """Cada ruta en multi-depot debe tener cost con desglose."""
        resp = client.get("/demo/multi-depot")
        data = resp.json()

        for route in data["routes"]:
            assert route.get("cost") is not None, f"Ruta {route['vehicle_id']} sin cost"
            cost = route["cost"]
            assert "fixed" in cost
            assert "distance" in cost
            assert "time" in cost
            assert "stops" in cost
            assert "total" in cost

    def test_statistics_have_total_cost(self, client):
        """Las estadísticas deben incluir total_cost cuando hay costos."""
        resp = client.get("/demo/multi-depot")
        data = resp.json()
        stats = data.get("statistics")
        assert stats is not None
        assert stats.get("total_cost") is not None
        assert stats["total_cost"] > 0
