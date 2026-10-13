"""Tipos de dados compartilhados entre os módulos deste backend."""

from __future__ import annotations

from dataclasses import dataclass

Crop = tuple[int, int, int, int]


@dataclass(frozen=True)
class Word:
    """Uma palavra transcrita: texto, tempo de início/fim e falante."""

    text: str
    start: float
    end: float
    speaker: str | None = None


@dataclass(frozen=True)
class FaceObservation:
    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2 na fonte
    score: float
    detector: str
    person_supported: bool | None = None

    @property
    def center(self) -> tuple[float, float, float]:
        x1, y1, x2, y2 = self.bbox
        return (x1 + x2) / 2, (y1 + y2) / 2, y2 - y1
