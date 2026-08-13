"""
Cliente de Copernicus Data Space Ecosystem (CDSE).
Autentica, busca y descarga metadata de Sentinel-1/Sentinel-2.

Filosofia NOOA: clase = cliente, metodos = capabilities.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

from config import AUTH_URL, CATALOGUE_URL

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class SentinelProduct:
    """Metadata de un producto Sentinel."""
    id: str
    name: str
    collection: str  # SENTINEL-1, SENTINEL-2
    product_type: str  # S1GRD, S2MSI1C, etc.
    sensing_date: str
    footprint: str  # WKT polygon
    cloud_cover: Optional[float] = None  # Solo Sentinel-2
    size_mb: Optional[float] = None
    download_url: Optional[str] = None


@dataclass
class SentinelSearchResult:
    """Resultado de busqueda de productos."""
    products: list[SentinelProduct] = field(default_factory=list)
    total_count: int = 0
    query: str = ""
    errors: list[str] = field(default_factory=list)


class SentinelClient:
    """
    Cliente del API de Copernicus Data Space Ecosystem.

    Estado:
        - access_token: token de autenticacion (expira en ~1h)
        - token_expires_at: cuando expira el token
        - session: sesion HTTP autenticada

    Capabilities:
        - authenticate: obtiene token de CDSE
        - search_products: busca productos Sentinel por area y fecha
        - get_product_metadata: obtiene metadata de un producto
        - download_product: descarga un producto (no para PoC)
    """

    def __init__(self, username: str | None = None, password: str | None = None):
        self.username = username or os.getenv("CDSE_USERNAME", "")
        self.password = password or os.getenv("CDSE_PASSWORD", "")
        self.access_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.session: Optional[requests.Session] = None

    def _check_credentials(self) -> bool:
        if not self.username or not self.password:
            return False
        return True

    def authenticate(self) -> bool:
        """Autentica con CDSE y obtiene access_token."""
        if not self._check_credentials():
            logger.warning("Sin credenciales CDSE. Set CDSE_USERNAME y CDSE_PASSWORD en .env")
            return False

        data = {
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
        }

        try:
            response = requests.post(AUTH_URL, data=data, verify=True, allow_redirects=False, timeout=30)
            if response.status_code != 200:
                logger.error(f"CDSE auth fallo: {response.status_code} {response.text[:200]}")
                return False

            token_data = response.json()
            self.access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in - 60)

            self.session = requests.Session()
            self.session.headers["Authorization"] = f"Bearer {self.access_token}"

            logger.info(f"CDSE autenticado. Token expira en {expires_in}s")
            return True

        except Exception as e:
            logger.error(f"CDSE auth error: {e}")
            return False

    def _ensure_authenticated(self) -> bool:
        """Verifica que el token es valido, re-autentica si expiro."""
        if self.access_token is None:
            return self.authenticate()
        if self.token_expires_at and datetime.now(timezone.utc) > self.token_expires_at:
            return self.authenticate()
        return True

    def search_products(
        self,
        collection: str = "SENTINEL-2",
        product_type: str | None = None,
        aoi_wkt: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        max_cloud_cover: float | None = None,
        top: int = 10,
    ) -> SentinelSearchResult:
        """
        Busca productos Sentinel en el catalogo CDSE.

        Args:
            collection: "SENTINEL-1" o "SENTINEL-2"
            product_type: "S2MSI1C", "S1GRD", etc.
            aoi_wkt: Area of Interest en formato WKT (POLYGON((lng lat, ...)))
            start_date: "2024-01-01T00:00:00.000Z"
            end_date: "2024-01-10T00:00:00.000Z"
            max_cloud_cover: 0-100 (solo Sentinel-2)
            top: maximo de resultados
        """
        result = SentinelSearchResult()

        if not self._ensure_authenticated():
            result.errors.append("No se pudo autenticar con CDSE")
            return result

        # Construir filtro OData
        filters = [f"Collection/Name eq '{collection}'"]

        if product_type:
            filters.append(f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq '{product_type}')")

        if aoi_wkt:
            filters.append(f"OData.CSC.Intersects(area=geography'SRID=4326;{aoi_wkt}')")

        if start_date and end_date:
            filters.append(f"ContentDate/Start gt {start_date}")
            filters.append(f"ContentDate/Start lt {end_date}")

        if max_cloud_cover is not None and collection == "SENTINEL-2":
            filters.append(f"Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' and att/OData.CSC.DoubleAttribute/Value le {max_cloud_cover})")

        filter_str = " and ".join(filters)
        from urllib.parse import quote
        url = f"{CATALOGUE_URL}?$filter={quote(filter_str)}&$top={top}"

        result.query = url

        try:
            response = self.session.get(url, timeout=60)
            if response.status_code != 200:
                result.errors.append(f"Busqueda fallo: {response.status_code} {response.text[:200]}")
                return result

            data = response.json()
            result.total_count = data.get("@odata.count", 0)

            for item in data.get("value", []):
                content_date = item.get("ContentDate", {})
                sensing_date = content_date.get("Start", "") if isinstance(content_date, dict) else ""

                product = SentinelProduct(
                    id=item.get("Id", ""),
                    name=item.get("Name", ""),
                    collection=collection,
                    product_type=product_type or "",
                    sensing_date=sensing_date,
                    footprint=item.get("GeoFootprint", {}).get("wkt", "") if isinstance(item.get("GeoFootprint"), dict) else "",
                )

                # Extraer cloud cover de atributos
                for attr in item.get("Attributes", []):
                    if attr.get("Name") == "cloudCover":
                        product.cloud_cover = float(attr.get("Value", 0))
                    if attr.get("Name") == "size":
                        try:
                            product.size_mb = float(attr.get("Value", 0)) / (1024 * 1024)
                        except (ValueError, TypeError):
                            pass

                result.products.append(product)

            logger.info(f"CDSE: {len(result.products)} productos encontrados")
            return result

        except Exception as e:
            result.errors.append(f"Error en busqueda: {e}")
            return result

    def get_latest_image(
        self,
        aoi_wkt: str,
        collection: str = "SENTINEL-2",
        days_back: int = 7,
        max_cloud_cover: float = 20.0,
    ) -> SentinelProduct | None:
        """
        Obtiene la imagen mas reciente de un area.

        Args:
            aoi_wkt: Area of Interest en WKT
            collection: SENTINEL-1 o SENTINEL-2
            days_back: cuantos dias hacia atras buscar
            max_cloud_cover: max nubosidad (Sentinel-2)
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days_back)

        result = self.search_products(
            collection=collection,
            aoi_wkt=aoi_wkt,
            start_date=start.strftime("%Y-%m-%dT00:00:00.000Z"),
            end_date=end.strftime("%Y-%m-%dT23:59:59.000Z"),
            max_cloud_cover=max_cloud_cover if collection == "SENTINEL-2" else None,
            top=5,
        )

        if result.errors or not result.products:
            logger.warning(f"No se encontraron imagenes: {result.errors}")
            return None

        # Retornar la mas reciente
        return result.products[0]

    def is_available(self) -> bool:
        """Verifica si el cliente tiene credenciales y puede autenticar."""
        return self._check_credentials() and self.authenticate()


def bbox_to_wkt(min_lng: float, min_lat: float, max_lng: float, max_lat: float) -> str:
    """Convierte un bounding box a WKT polygon."""
    return f"POLYGON(({min_lng} {min_lat},{max_lng} {min_lat},{max_lng} {max_lat},{min_lng} {max_lat},{min_lng} {min_lat}))"
