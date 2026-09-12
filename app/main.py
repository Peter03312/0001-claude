"""FastAPI application exposing the defect clustering service."""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, List

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .clustering import Echo, cluster_echoes
from .models import ClusterOut, ScanRequest, ScanResponse

app = FastAPI(
    title="Coil UT Defect Clustering API",
    version="1.0.0",
    description=(
        "Merges ultrasonic scan echoes on a coil circumference into unique "
        "defect clusters, including clusters split across the zero point."
    ),
)


def _sanitize_non_finite(value: Any) -> Any:
    """Replace non-finite floats with JSON-safe string labels.

    Pydantic error details embed the offending ``input`` value; a raw
    ``NaN``/``Infinity`` there would crash ``JSONResponse``
    (``allow_nan=False``) and turn a clean 422 into a 500.
    """
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, dict):
        return {key: _sanitize_non_finite(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize_non_finite(item) for item in value]
    return value


@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    detail = _sanitize_non_finite(exc.errors())
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(detail)})


def _cross_field_errors(payload: ScanRequest) -> List[dict]:
    """Collect every cross-field violation with a locatable path."""
    errors: List[dict] = []
    if payload.G >= payload.L / 2:
        errors.append(
            {
                "type": "value_error",
                "loc": ("body", "G"),
                "msg": f"G must satisfy 0 <= G < L/2 (got G={payload.G}, L/2={payload.L / 2})",
                "input": payload.G,
            }
        )
    for i, echo in enumerate(payload.echoes):
        if echo.position >= payload.L:
            errors.append(
                {
                    "type": "value_error",
                    "loc": ("body", "echoes", i, "position"),
                    "msg": (
                        f"position must satisfy 0 <= position < L "
                        f"(got position={echo.position}, L={payload.L})"
                    ),
                    "input": echo.position,
                }
            )
    return errors


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/clusters", response_model=ScanResponse)
def clusters(payload: ScanRequest) -> ScanResponse:
    # Any invalid field rejects the whole request; no partial clusters.
    errors = _cross_field_errors(payload)
    if errors:
        raise RequestValidationError(errors)
    echoes = [Echo(position=e.position, amplitude=e.amplitude) for e in payload.echoes]
    result = cluster_echoes(payload.L, payload.G, echoes)
    return ScanResponse(clusters=[ClusterOut(**asdict(c)) for c in result])
