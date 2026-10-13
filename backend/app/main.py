"""Backend HTTP de corte e enquadramento 9:16.

Dois endpoints principais (`/enquadramento`, `/corte`) + um auxiliar best-effort
(`/detectar-silencio`)."""

from __future__ import annotations

import os
import uuid

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app import cut, reframe, silence

app = FastAPI(
    title="VivaVoz Corte Backend",
    description="Corte e enquadramento 9:16 para o pipeline de edição de vídeo.",
    version="0.1.0",
)

# Diretório de saída dos cortes renderizados. Configurável porque o agente
# `cortador` espera a saída final em `edit/corte.mp4` dentro da pasta do vídeo.
_OUT_DIR = os.getenv("VIVAVOZ_OUT_DIR", "/tmp/vivavoz-corte-backend")
os.makedirs(_OUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# /enquadramento
# ---------------------------------------------------------------------------


_FORMATOS = {"9:16": (9, 16), "16:9": (16, 9)}


class EnquadramentoRequest(BaseModel):
    video_path: str
    start: float = 0.0
    end: float | None = None
    formato: str = Field(default="9:16", description="'9:16' (social) ou '16:9' (YouTube)")
    rotacao: int = Field(default=0, description="graus no sentido horário (0/90/180/270) — bruto gravado com a câmera deitada")
    num_falantes: int = Field(default=1, ge=1, description="1 = enquadramento normal no rosto dominante; 2 = bate-volta (as duas pessoas no quadro, só 9:16)")
    posicoes_conhecidas: list[float] | None = None


class EnquadramentoResponse(BaseModel):
    x: int
    y: int
    largura: int
    altura: int


@app.post("/enquadramento", response_model=EnquadramentoResponse)
def enquadramento(req: EnquadramentoRequest) -> EnquadramentoResponse:
    if not os.path.isfile(req.video_path):
        raise HTTPException(status_code=404, detail=f"video_path não encontrado: {req.video_path}")
    if req.formato not in _FORMATOS:
        raise HTTPException(status_code=400, detail=f"formato inválido: {req.formato} (use '9:16' ou '16:9')")
    if req.rotacao not in (0, 90, 180, 270):
        raise HTTPException(status_code=400, detail="rotacao inválida (use 0, 90, 180 ou 270)")
    aspect_w, aspect_h = _FORMATOS[req.formato]

    if req.num_falantes >= 2:
        if req.formato != "9:16":
            raise HTTPException(status_code=400, detail="bate-volta de 2 falantes só suporta formato 9:16 por ora")
        crop = reframe.compute_crop_dois_falantes(
            req.video_path, req.start, req.end or (req.start + 5.0), req.posicoes_conhecidas
        )
        if crop is None:
            # Bate-volta só se o encaixe geométrico permitir; senão cai no
            # enquadramento de 1 pessoa.
            crop = reframe.compute_face_crop(
                req.video_path, req.start, req.end,
                aspect_w=aspect_w, aspect_h=aspect_h, rotacao=req.rotacao,
            )
    else:
        crop = reframe.compute_face_crop(
            req.video_path, req.start, req.end,
            aspect_w=aspect_w, aspect_h=aspect_h, rotacao=req.rotacao,
        )

    if crop is None:
        raise HTTPException(
            status_code=422,
            detail="não foi possível detectar rosto/pessoa nesse trecho — sem enquadramento confiável",
        )
    x, y, w, h = crop
    return EnquadramentoResponse(x=x, y=y, largura=w, altura=h)


class EnquadramentoEstavelRequest(BaseModel):
    video_path: str
    blocos: list[tuple[float, float]] = Field(description="todos os trechos (start, end) que vêm da mesma câmera/tomada — um crop só pra todos, sem tremer a cada corte")
    formato: str = Field(default="9:16", description="'9:16' (social) ou '16:9' (YouTube)")
    rotacao: int = Field(default=0, description="graus no sentido horário (0/90/180/270)")


@app.post("/enquadramento-estavel", response_model=EnquadramentoResponse)
def enquadramento_estavel(req: EnquadramentoEstavelRequest) -> EnquadramentoResponse:
    if not os.path.isfile(req.video_path):
        raise HTTPException(status_code=404, detail=f"video_path não encontrado: {req.video_path}")
    if req.formato not in _FORMATOS:
        raise HTTPException(status_code=400, detail=f"formato inválido: {req.formato} (use '9:16' ou '16:9')")
    if req.rotacao not in (0, 90, 180, 270):
        raise HTTPException(status_code=400, detail="rotacao inválida (use 0, 90, 180 ou 270)")
    if not req.blocos:
        raise HTTPException(status_code=400, detail="lista de blocos vazia")
    aspect_w, aspect_h = _FORMATOS[req.formato]
    crop = reframe.compute_face_crop_agregado(
        req.video_path, req.blocos, aspect_w=aspect_w, aspect_h=aspect_h, rotacao=req.rotacao
    )
    if crop is None:
        raise HTTPException(
            status_code=422,
            detail="não foi possível detectar rosto/pessoa consistente nesses blocos",
        )
    x, y, w, h = crop
    return EnquadramentoResponse(x=x, y=y, largura=w, altura=h)


# ---------------------------------------------------------------------------
# /corte
# ---------------------------------------------------------------------------


class TrechoRequest(BaseModel):
    source: str
    start: float
    end: float
    crop: tuple[int, int, int, int] | None = None
    rotacao: int = Field(default=0, description="graus no sentido horário (0/90/180/270), mesmo valor usado em /enquadramento pra esse source")
    fade_in: bool = True
    fade_out: bool = True
    pad_inicio: float = Field(default=cut.PAD_PADRAO, description="folga (s) antes de start — respiração natural + drift do Scribe. Reduza perto de 0 só se o trecho anterior colar demais nessa borda")
    pad_fim: float = Field(default=cut.PAD_PADRAO, description="folga (s) depois de end")
    remover_ruido: bool = Field(default=False, description="aplica redução de ruído antes do loudnorm — ligue quando não há editado de referência pra comparar")


class CorteRequest(BaseModel):
    trechos: list[TrechoRequest]
    normalizar_audio: bool = True
    lufs: float = Field(default=cut.LUFS_ALVO_PADRAO, description="alvo de loudness integrado (LUFS) — use o valor calibrado no STYLE-GUIDE do cliente, não o padrão genérico")
    tp: float = Field(default=cut.TP_ALVO_PADRAO, description="teto de true peak (dBTP)")
    lra: float = Field(default=cut.LRA_ALVO_PADRAO, description="faixa de loudness alvo (LRA)")
    fade: float = cut.FADE
    out_name: str | None = None


class CorteResponse(BaseModel):
    out_path: str


@app.post("/corte", response_model=CorteResponse)
def corte(req: CorteRequest) -> CorteResponse:
    if not req.trechos:
        raise HTTPException(status_code=400, detail="lista de trechos vazia")
    for t in req.trechos:
        if not os.path.isfile(t.source):
            raise HTTPException(status_code=404, detail=f"source não encontrado: {t.source}")
        if t.end <= t.start:
            raise HTTPException(status_code=400, detail=f"trecho inválido: end <= start ({t.source})")

    out_name = req.out_name or f"corte_{uuid.uuid4().hex[:8]}.mp4"
    out_path = os.path.join(_OUT_DIR, out_name)
    trechos = [
        cut.Trecho(
            source=t.source, start=t.start, end=t.end, crop=t.crop, rotacao=t.rotacao,
            fade_in=t.fade_in, fade_out=t.fade_out,
            pad_inicio=t.pad_inicio, pad_fim=t.pad_fim, remover_ruido=t.remover_ruido,
        )
        for t in req.trechos
    ]
    try:
        cut.cortar_e_concatenar(
            trechos, out_path, fade=req.fade, normalizar_audio=req.normalizar_audio,
            lufs=req.lufs, tp=req.tp, lra=req.lra,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return CorteResponse(out_path=out_path)


# ---------------------------------------------------------------------------
# /medir-audio — mede loudness de um vídeo (editado ou cortado), pro
# normalizador comparar contra o alvo do cliente ou contra uma referência.
# ---------------------------------------------------------------------------


class MedirAudioRequest(BaseModel):
    video_path: str


class MedirAudioResponse(BaseModel):
    lufs_integrado: float
    true_peak_dbtp: float
    lra: float


@app.post("/medir-audio", response_model=MedirAudioResponse)
def medir_audio(req: MedirAudioRequest) -> MedirAudioResponse:
    if not os.path.isfile(req.video_path):
        raise HTTPException(status_code=404, detail=f"video_path não encontrado: {req.video_path}")
    medido = cut.medir_loudness(req.video_path)
    if medido is None:
        raise HTTPException(status_code=422, detail="não foi possível medir o áudio desse arquivo")
    return MedirAudioResponse(
        lufs_integrado=medido["input_i"], true_peak_dbtp=medido["input_tp"], lra=medido["input_lra"]
    )


# ---------------------------------------------------------------------------
# /verificar-audio — checagem objetiva (clipping, pico, silêncio longo), sem
# depender de ouvir o vídeo inteiro. Parte do checklist do revisor.
# ---------------------------------------------------------------------------


class VerificarAudioRequest(BaseModel):
    video_path: str
    silencio_min_seg: float = Field(default=0.6, description="a partir de quantos segundos um silêncio é suspeito (corte errado/engasgo), não pausa natural")


class VerificarAudioResponse(BaseModel):
    pico_db: float | None
    amostras_clipadas: int
    silencios_longos: list[list[float]]


@app.post("/verificar-audio", response_model=VerificarAudioResponse)
def verificar_audio(req: VerificarAudioRequest) -> VerificarAudioResponse:
    if not os.path.isfile(req.video_path):
        raise HTTPException(status_code=404, detail=f"video_path não encontrado: {req.video_path}")
    r = cut.verificar_audio(req.video_path, req.silencio_min_seg)
    return VerificarAudioResponse(**r)


# ---------------------------------------------------------------------------
# /detectar-silencio (auxiliar, best-effort)
# ---------------------------------------------------------------------------


class DetectarSilencioRequest(BaseModel):
    video_path: str
    threshold_db: float = -35.0
    min_duration_sec: float = 0.5


class DetectarSilencioResponse(BaseModel):
    duracao: float
    silencios: list[list[float]]
    trechos_uteis: list[list[float]]


@app.post("/detectar-silencio", response_model=DetectarSilencioResponse)
def detectar_silencio(req: DetectarSilencioRequest) -> DetectarSilencioResponse:
    if not os.path.isfile(req.video_path):
        raise HTTPException(status_code=404, detail=f"video_path não encontrado: {req.video_path}")
    resultado = silence.detectar_silencio(req.video_path, req.threshold_db, req.min_duration_sec)
    uteis = silence.inverter_intervalos(
        [tuple(s) for s in resultado["silencios"]], resultado["duracao"]
    )
    return DetectarSilencioResponse(
        duracao=resultado["duracao"],
        silencios=resultado["silencios"],
        trechos_uteis=[[a, b] for a, b in uteis],
    )


@app.get("/saude")
def saude() -> dict:
    return {"status": "ok"}
