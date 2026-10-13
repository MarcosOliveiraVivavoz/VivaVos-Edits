"""Corte físico (ffmpeg): extrai cada trecho com fade de áudio e crop 9:16
opcional, concatena e normaliza o áudio (loudnorm). O crop de cada trecho vem
pronto de `POST /enquadramento` (`app/reframe.py`) — este módulo só corta."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_TIMEOUT_RENDER_SEG = 600  # 10 min por segmento/concat
_TIMEOUT_MEDIR_LOUDNESS_SEG = 60

FADE = 0.15  # fade de áudio (s) em cada emenda entre sub-segmentos (método VivaVoz)
PAD_PADRAO = 0.20  # folga (s) antes/depois do timestamp de palavra pedido — absorve o
# drift do Scribe (50-100ms) e preserva a respiração natural antes da fala. Sem isso o
# corte soa "limpo demais", tipo corte de podcast — não é esse o padrão aqui.
PRESET_ENCODE = "fast"
CRF_ENCODE = "18"
AUDIO_BITRATE = "192k"
LUFS_ALVO_PADRAO = -16.0  # EBU R128 genérico (mesmo padrão usado no Desilenciar); cada cliente pode ter o próprio alvo no STYLE-GUIDE
TP_ALVO_PADRAO = -1.5
LRA_ALVO_PADRAO = 11.0
DENOISE = "afftdn=nr=12:nf=-25"  # reduz ruído de fundo (ar-condicionado, ventilador, hiss)
# ANTES do loudnorm — subir o volume de um áudio ruidoso amplifica o ruído junto; limpar
# primeiro e só depois nivelar evita isso.


def _loudnorm_filtro(lufs: float, tp: float, lra: float) -> str:
    return f"loudnorm=I={lufs}:TP={tp}:LRA={lra}"


ALVO_DBFS_SEGMENTO = -20.0  # nível médio alvo por trecho, antes do loudnorm final


TETO_PICO_SEGMENTO_DBFS = -3.0  # nenhum trecho pode ter pico acima disso depois do ganho


def _ganho_estatico_db(source: str, start: float, end: float, alvo_dbfs: float = ALVO_DBFS_SEGMENTO) -> float:
    """Mede o volume médio E o pico (dBFS) de um trecho e devolve o ganho
    estático (dB) pra chegar perto de `alvo_dbfs`, sem deixar o PICO passar de
    `TETO_PICO_SEGMENTO_DBFS`. Usado em vez de `loudnorm` por trecho: o
    `loudnorm` dinâmico precisa de uma janela de análise pra estabilizar, e
    num clipe curto/isolado essa janela pode distorcer o início do áudio
    (achado comparando a confiança da transcrição antes/depois do corte — uma
    palavra que a Scribe reconhecia com certeza no bruto saía irreconhecível
    depois do `loudnorm` por trecho). Um ganho fixo não tem essa janela, não
    distorce — só sobe/desce o volume uniformemente.

    Calcular o ganho só pela MÉDIA estourava trecho com pico isolado alto
    (grito, riso) mesmo com a média baixa: o loudnorm final media o arquivo
    inteiro e abaixa o volume geral, mas o pico já tinha clipado no segmento
    intermediário — a passagem final não desclipa, só abaixa o que já ficou
    distorcido. Por isso o teto de pico manda mais que o alvo de média."""
    cmd = [
        "ffmpeg", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", source,
        "-af", "volumedetect", "-f", "null", "-",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_MEDIR_LOUDNESS_SEG)
        m_mean = re.search(r"mean_volume:\s*(-?[\d.]+) dB", r.stderr)
        m_max = re.search(r"max_volume:\s*(-?[\d.]+) dB", r.stderr)
        if not m_mean:
            return 0.0
        medido = float(m_mean.group(1))
        ganho = alvo_dbfs - medido
        if m_max:
            pico = float(m_max.group(1))
            ganho = min(ganho, TETO_PICO_SEGMENTO_DBFS - pico)  # nunca deixa o pico estourar
        return max(-12.0, min(12.0, ganho))  # clamp: nunca estoura nem silencia
    except Exception:
        log.warning("medição de volume (ganho estático) falhou para %s", source, exc_info=True)
        return 0.0


@dataclass(frozen=True)
class Trecho:
    """Um range a cortar: `source` (caminho do bruto), `start`/`end` em segundos,
    e opcionalmente `crop` (x, y, w, h) já calculado via `POST /enquadramento`."""

    source: str
    start: float
    end: float
    crop: tuple[int, int, int, int] | None = None
    rotacao: int = 0  # graus no sentido horário (0/90/180/270), aplicado antes do crop
    fade_in: bool = True
    fade_out: bool = True
    pad_inicio: float = PAD_PADRAO  # folga antes de `start` (respiração/drift de timestamp)
    pad_fim: float = PAD_PADRAO  # folga depois de `end`
    remover_ruido: bool = False  # aplica DENOISE antes do loudnorm — ligar quando não há
    # editado de referência pra comparar (ex.: cliente sem material aprovado ainda)


def _filtro_loudnorm_2passes(lista_concat: str, lufs: float, tp: float, lra: float) -> str:
    """Mede o loudness real (1º passe) e devolve o filtro `loudnorm` corrigido
    pro 2º passe bater a meta pedida com precisão. Sem medição, cai pro passe único."""
    loudnorm = _loudnorm_filtro(lufs, tp, lra)
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lista_concat,
        "-vn", "-af", f"{loudnorm}:print_format=json", "-f", "null", "-",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_MEDIR_LOUDNESS_SEG)
        inicio = r.stderr.rindex("{")
        fim = r.stderr.rindex("}") + 1
        medido = json.loads(r.stderr[inicio:fim])
        return (
            f"{loudnorm}:measured_I={medido['input_i']}:measured_TP={medido['input_tp']}:"
            f"measured_LRA={medido['input_lra']}:measured_thresh={medido['input_thresh']}:"
            f"offset={medido['target_offset']}:linear=true"
        )
    except Exception:
        log.warning("medição de loudness (2 passes) falhou, usando passe único", exc_info=True)
        return loudnorm


def medir_loudness(video_path: str) -> dict | None:
    """Mede o loudness integrado (LUFS), true peak (dBTP) e LRA de um arquivo,
    sem alterar nada — usado pra comparar um corte contra a referência do
    cliente ou contra o alvo do STYLE-GUIDE."""
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"{_loudnorm_filtro(LUFS_ALVO_PADRAO, TP_ALVO_PADRAO, LRA_ALVO_PADRAO)}:print_format=json",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_MEDIR_LOUDNESS_SEG)
    try:
        inicio = r.stderr.rindex("{")
        fim = r.stderr.rindex("}") + 1
        medido = json.loads(r.stderr[inicio:fim])
        return {
            "input_i": float(medido["input_i"]),
            "input_tp": float(medido["input_tp"]),
            "input_lra": float(medido["input_lra"]),
        }
    except Exception:
        log.warning("medição de loudness falhou para %s", video_path, exc_info=True)
        return None


def verificar_audio(video_path: str, silencio_min_seg: float = 0.6) -> dict:
    """Checagem objetiva, sem depender de ouvido: pico máximo, amostras
    estouradas (clipping) e silêncios longos (>`silencio_min_seg`) que podem
    ser corte errado/engasgo, não pausa intencional. Não altera o arquivo."""
    import re

    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"astats=metadata=0,silencedetect=noise=-50dB:d={silencio_min_seg}",
        "-f", "null", "-",
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_MEDIR_LOUDNESS_SEG)
    saida = r.stderr

    pico = None
    m = re.search(r"Peak level dB:\s*(-?[\d.]+)", saida)
    if m:
        pico = float(m.group(1))

    clipados = 0
    for m in re.finditer(r"Number of clipped samples:\s*(\d+)", saida):
        clipados += int(m.group(1))

    silencios: list[tuple[float, float]] = []
    pending: float | None = None
    eventos = sorted(
        [(mm.start(), "start", float(mm.group(1))) for mm in re.finditer(r"silence_start:\s*([\d.]+)", saida)]
        + [(mm.start(), "end", float(mm.group(1))) for mm in re.finditer(r"silence_end:\s*([\d.]+)", saida)]
    )
    for _, tipo, valor in eventos:
        if tipo == "start":
            pending = valor
        elif pending is not None:
            silencios.append((pending, valor))
            pending = None

    return {
        "pico_db": pico,
        "amostras_clipadas": clipados,
        "silencios_longos": [[a, b] for a, b in silencios],
    }


def _run(cmd: list[str]) -> None:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=_TIMEOUT_RENDER_SEG)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"ffmpeg travou (mais de {_TIMEOUT_RENDER_SEG}s) — segmento pode estar corrompido"
        ) from e
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falhou (rc={r.returncode}): {r.stderr[-400:]}")


_ROTACAO_FFMPEG = {90: "transpose=1", 180: "hflip,vflip", 270: "transpose=2"}


def _extract_cmd(
    source: str,
    start: float,
    end: float,
    out: str,
    fade: float,
    crop: tuple[int, int, int, int] | None,
    fade_in: bool,
    fade_out: bool,
    rotacao: int = 0,
    normalizar_segmento: bool = True,
    remover_ruido: bool = False,
    threads: int = 0,
) -> list[str]:
    """Extrai um sub-segmento com re-encode, fade de áudio, rotação e crop
    opcionais. A rotação (0/90/180/270, sentido horário) é aplicada ANTES do
    crop — as coordenadas de `crop` já vêm calculadas no frame rotacionado
    (mesmo `rotacao` passado a `/enquadramento`). A resolução de saída
    (1080x1920 ou 1920x1080) segue o aspecto do `crop`.

    `normalizar_segmento` nivela CADA trecho com um ganho estático (não
    `loudnorm` — ver `_ganho_estatico_db`) antes de concatenar: sem isso, um
    trecho gravado mais baixo (sussurro, pessoa mais longe do mic) continua
    baixo mesmo depois do loudnorm final, que só ajusta a média do arquivo
    inteiro já montado. `remover_ruido` aplica `DENOISE` antes do ganho —
    subir o volume de um áudio ruidoso amplifica o ruído junto, então limpa
    primeiro."""
    dur = end - start
    # Num trecho curto (ex.: uma interjeição de 0.2s), 2 fades de 150ms cada
    # se sobrepõem e estouram o áudio. Encolhe o fade pra caber: no máximo
    # 1/3 da duração de cada lado, nunca mais que os `fade` pedidos.
    fade = min(fade, dur / 3) if (fade_in or fade_out) else fade
    partes_af = []
    if remover_ruido:
        partes_af.append(DENOISE)
    if normalizar_segmento:
        ganho = _ganho_estatico_db(source, start, end)
        if abs(ganho) > 0.1:
            partes_af.append(f"volume={ganho:.2f}dB")
    if fade_in:
        partes_af.append(f"afade=t=in:st=0:d={fade}")
    if fade_out:
        partes_af.append(f"afade=t=out:st={max(0.0, dur - fade):.3f}:d={fade}")
    af = ",".join(partes_af) if partes_af else None
    partes_vf = []
    if rotacao in _ROTACAO_FFMPEG:
        partes_vf.append(_ROTACAO_FFMPEG[rotacao])
    if crop:
        cw, ch = crop[2], crop[3]
        saida = "1080:1920" if ch >= cw else "1920:1080"
        partes_vf.append(f"crop={cw}:{ch}:{crop[0]}:{crop[1]},scale={saida},setsar=1")
    partes_vf.append("setpts=PTS-STARTPTS")
    vf = ",".join(partes_vf)
    cmd = [
        "ffmpeg", "-y",
        "-threads", str(threads),
        "-filter_threads", str(max(1, threads)),
        "-ss", f"{start:.3f}",
        "-t", f"{dur:.3f}",
        "-i", source,
    ]
    if af:
        cmd += ["-af", af]
    cmd += ["-vf", vf]
    cmd += [
        "-c:v", "libx264", "-preset", PRESET_ENCODE, "-crf", CRF_ENCODE, "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "44100",
    ]
    cmd += [out, "-loglevel", "error"]
    return cmd


def cortar_e_concatenar(
    trechos: list[Trecho],
    out_path: str,
    fade: float = FADE,
    normalizar_audio: bool = True,
    lufs: float = LUFS_ALVO_PADRAO,
    tp: float = TP_ALVO_PADRAO,
    lra: float = LRA_ALVO_PADRAO,
    threads: int = 0,
) -> str:
    """Corta cada trecho (re-encode + fade + crop opcional) e concatena, com
    loudnorm no áudio já montado. `lufs`/`tp`/`lra` vêm do alvo calibrado pro
    cliente (STYLE-GUIDE) — sem isso, cai no padrão genérico de streaming."""
    if not trechos:
        raise ValueError("lista de trechos vazia")
    with tempfile.TemporaryDirectory() as tmp:
        segs: list[str] = []
        for index, trecho in enumerate(trechos):
            seg = os.path.join(tmp, f"seg_{index:03d}.mp4")
            inicio = max(0.0, trecho.start - trecho.pad_inicio)
            fim = trecho.end + trecho.pad_fim
            _run(
                _extract_cmd(
                    trecho.source, inicio, fim, seg, fade,
                    trecho.crop, trecho.fade_in, trecho.fade_out,
                    rotacao=trecho.rotacao, normalizar_segmento=normalizar_audio,
                    remover_ruido=trecho.remover_ruido, threads=threads,
                )
            )
            segs.append(seg)
        lista = os.path.join(tmp, "concat.txt")
        with open(lista, "w") as f:
            f.write("".join(f"file '{p}'\n" for p in segs))
        concat = ["ffmpeg", "-y", "-threads", str(threads), "-f", "concat", "-safe", "0", "-i", lista]
        concat += ["-c:v", "copy", "-c:a", "aac", "-b:a", AUDIO_BITRATE, "-ar", "44100"]
        if normalizar_audio:
            concat += ["-af", _filtro_loudnorm_2passes(lista, lufs, tp, lra)]
        _run([*concat, out_path, "-loglevel", "error"])
    return out_path
