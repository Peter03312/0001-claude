"""Pydantic request/response models for the clustering API."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat


class EchoIn(BaseModel):
    """Single ultrasonic echo, millimetre units."""

    model_config = ConfigDict(extra="forbid")

    position: FiniteFloat = Field(
        ge=0,
        description="Echo position along the circumference in mm; must satisfy 0 <= position < L.",
    )
    amplitude: FiniteFloat = Field(description="Echo amplitude; any finite number.")


class ScanRequest(BaseModel):
    """One circumference scan: geometry plus at least one echo."""

    model_config = ConfigDict(extra="forbid")

    L: FiniteFloat = Field(gt=0, description="Circumference in mm; must be > 0.")
    G: FiniteFloat = Field(ge=0, description="Merge distance in mm; must satisfy 0 <= G < L/2.")
    echoes: List[EchoIn] = Field(min_length=1, description="At least one echo is required.")


class ClusterOut(BaseModel):
    """One unique defect cluster."""

    start: float = Field(description="Cluster start position in mm.")
    length: float = Field(description="Arc length in mm from start to last point, positive direction.")
    echo_count: int = Field(description="Number of echoes in the cluster after de-duplication.")
    peak_amplitude: float = Field(description="Largest amplitude in the cluster.")
    peak_position: float = Field(description="Position of the peak; smallest position on amplitude ties.")


class ScanResponse(BaseModel):
    """All clusters of one scan, sorted by start ascending."""

    clusters: List[ClusterOut]
