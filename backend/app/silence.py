"""Detecção de silêncio via ffmpeg: roda o filtro `silencedetect`, faz parse por
regex da saída e inverte os intervalos de silêncio para obter os trechos
"úteis" a manter. Auxiliar/best-effort — o corte principal é guiado por roteiro.
"""

from __future__ import annotations

import re
import subprocess

_TIMEOUT_DETECTAR_SEG = 300

_RE_DURATION = re.compile(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)")
_RE_SILENCE_START = re.compile(r"silence_start:\s*([\d.]+)")
_RE_SILENCE_END = re.compile(r"silence_end:\s*([\d.]+)")

_MIN_SEGMENT = 0.05  # abaixo disso, não vale a pena manter como trecho útil


def detectar_silencio(
    video_path: str,
    threshold_db: float = -35.0,
    min_duration_sec: float = 0.5,
) -> dict:
    """Roda `ffmpeg ... -af silencedetect=noise=<threshold_db>dB:d=<min_duration_sec>`
    e devolve `{"duracao": float, "silencios": [[start, end], ...]}`."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration_sec}",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_DETECTAR_SEG)
    saida = r.stderr

    duracao = 0.0
    m = _RE_DURATION.search(saida)
    if m:
        h, mi, s = m.groups()
        duracao = int(h) * 3600 + int(mi) * 60 + float(s)

    silencios: list[tuple[float, float]] = []
    pending_start: float | None = None
    # Percorre o texto em ORDEM (start sempre vem antes do end correspondente
    # na saída do ffmpeg), pareando por posição.
    eventos = sorted(
        [(m.start(), "start", float(m.group(1))) for m in _RE_SILENCE_START.finditer(saida)]
        + [(m.start(), "end", float(m.group(1))) for m in _RE_SILENCE_END.finditer(saida)]
    )
    for _, tipo, valor in eventos:
        if tipo == "start":
            pending_start = valor
        elif pending_start is not None:
            silencios.append((pending_start, valor))
            pending_start = None

    return {"duracao": duracao, "silencios": [[a, b] for a, b in silencios]}


def inverter_intervalos(silencios: list[tuple[float, float]], duracao: float) -> list[tuple[float, float]]:
    """Trechos ÚTEIS = complemento dos intervalos de silêncio."""
    manter: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in silencios:
        if start - cursor > _MIN_SEGMENT:
            manter.append((cursor, start))
        cursor = end
    if duracao - cursor > _MIN_SEGMENT:
        manter.append((cursor, duracao))
    return manter
