"""Cliente mínimo de la API de Aurora."""

import httpx


def crear_factura(token: str, datos: dict) -> str:
    r = httpx.post(
        "https://api.aurora.example/v2/invoices",
        json=datos,
        headers={"Authorization": f"Bearer {token}"},
    )
    return r.json()["invoice_id"]
