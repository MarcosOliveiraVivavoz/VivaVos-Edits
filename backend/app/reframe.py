"""Enquadramento 9:16 — detecta o rosto dominante por amostragem de frames
(MediaPipe, com fallback Haar para rosto de perfil), escolhe a pessoa que fala
(desempate por movimento labial quando há disputa) e calcula a janela de crop
com zoom, headroom de cabelo e ancoragem opcional de microfone (YOLO-World,
degrada sem erro se não disponível). Identificação de falante é só visual
(sem áudio) — suficiente pro caso de uso, mais simples de operar.
"""

from __future__ import annotations

import logging
import math
import os
import threading
from functools import lru_cache

from app.face_detection import detect_frame

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes calibradas por teste visual — não mudar sem validar contra cortes reais.
# ---------------------------------------------------------------------------

FACE_FRAC = 0.14  # rosto ~14% da altura (enquadramento de corte de podcast, não close no rosto)
FACE_POS_Y = 0.32  # centro do rosto a ~32% do topo (headroom em cima)
FACE_POS_X = 0.50  # centralizado — deslocar fixo pra um lado sobrava vazio do outro lado
ZOOM_MAX = 1.35  # zoom máximo sobre o rosto

_ROSTO_LARGURA_FRAC = 0.85  # largura aproximada do rosto como fração da altura detectada

_MARGEM_CABELO_FRAC = 0.35  # reserva extra acima da caixa de rosto do mediapipe (cabelo/
# acessório de cabeça, que o mediapipe não mede), proporcional à altura do rosto

_MIC_FOLGA_PX = 2  # px de folga entre a ponta do microfone e a borda do crop (medido em
# cortes de referência aprovados: o mic fica quase grudado na borda, sem sobra)

_MIC_LARGURA_MAX_FRAC_CW = 0.45  # mic mais largo que isso (fração da largura do CROP) não
# ancora — vira elemento dominante do quadro em vez de apoio ao lado do rosto

_MIC_DESLOCAMENTO_MAX_FRAC_CW = 0.15  # composição nunca afasta a pessoa do centro por um mic

_DETECCAO_LARGURA_MAX = 480  # roda a detecção numa cópia menor do frame (mais rápido em CPU)

_ALTURA_MIN_ROSTO_FRAC = 0.08  # rosto menor que isso costuma ser gente numa TV/monitor ao
# fundo, não o host/convidado

_COBERTURA_MIN_FRAC = 0.35  # fração mínima das amostras com algum rosto pra confiar no crop

_PARTICIPACAO_MIN_INICIO = 0.25  # fração mínima de frames em que a pessoa é detectada
_DISPUTA_RAZAO_MIN = 0.6  # só tenta desempate se o segundo tiver >=60% do suporte do maior

_BOCA_N_PONTOS = 6
_BOCA_DELTA_SEG = 0.15
_BOCA_VANTAGEM_MIN = 1.3

_PROMPT_MIC = "podcast microphone on stand"
_MODELO_MIC = os.getenv("MIC_MODEL_PATH", "yolov8m-world.pt")
_MIC_N_SAMPLES = 3
_modelo_mic = None
_lock_modelo_mic = threading.Lock()
_MIC_CONF_MIN = 0.10

_BATE_VOLTA_ZOOM = 1.15
_BATE_VOLTA_POS_Y = 0.38
_POSICAO_PESSOA_MIN_FRAC = 0.08

_cascade_perfil = None


# ---------------------------------------------------------------------------
# Janela de crop 9:16
# ---------------------------------------------------------------------------


def _crop_window(
    w: int,
    h: int,
    face_cx: float,
    face_cy: float | None = None,
    face_h: float | None = None,
    mic_cx: float | None = None,
    mic_largura: float = 0.0,
    aspect_w: int = 9,
    aspect_h: int = 16,
) -> tuple[int, int, int, int]:
    """Janela (x, y, cw, ch) dentro da fonte, no aspecto `aspect_w:aspect_h`
    (9:16 pra social, 16:9 pra YouTube), com prioridade no rosto."""
    if face_h and face_cy is not None:
        ch_natural = round(face_h / FACE_FRAC)
        ch = max(round(h / ZOOM_MAX), min(ch_natural, h))
        if ch_natural < h:
            cabe_em_cima = face_cy / FACE_POS_Y
            cabe_embaixo = (h - face_cy) / (1 - FACE_POS_Y)
            ch = max(round(h / ZOOM_MAX), min(ch, round(min(cabe_em_cima, cabe_embaixo))))
    else:
        ch = h
    cw = round(ch * aspect_w / aspect_h)
    if cw > w:
        cw, ch = w, min(h, round(w * aspect_h / aspect_w))
    x_frac = FACE_POS_X if face_cy is not None else 0.5
    x = int(min(max(face_cx - cw * x_frac, 0), w - cw))
    if mic_cx is not None and face_cy is not None and mic_largura <= cw * _MIC_LARGURA_MAX_FRAC_CW:
        meia_mic = mic_largura / 2
        folga = _MIC_FOLGA_PX
        lo, hi = mic_cx - meia_mic, mic_cx + meia_mic
        meia_rosto = face_h * _ROSTO_LARGURA_FRAC / 2 if face_h else 0.0
        vao = max(hi, face_cx + meia_rosto) - min(lo, face_cx - meia_rosto)
        if vao <= cw:
            if mic_cx >= face_cx:
                x_ancorado = math.ceil(hi + folga - cw)
            else:
                x_ancorado = math.floor(lo - folga)
            x_ancorado = min(max(x_ancorado, 0), w - cw)
            if (
                abs(x_ancorado - x) <= cw * _MIC_DESLOCAMENTO_MAX_FRAC_CW
                and x_ancorado <= face_cx - meia_rosto
                and face_cx + meia_rosto <= x_ancorado + cw
            ):
                x = int(x_ancorado)
    yc = face_cy if face_cy is not None else h / 2
    y = int(min(max(yc - ch * FACE_POS_Y, 0), h - ch))
    if face_h and face_cy is not None:
        topo_com_margem = face_cy - face_h / 2 - face_h * _MARGEM_CABELO_FRAC
        y = int(min(y, max(0, topo_com_margem)))
        y = max(0, min(y, h - ch))
    return x, y, cw, ch


# ---------------------------------------------------------------------------
# Detecção de rosto (fallback de perfil via Haar) + amostragem por clipe
# ---------------------------------------------------------------------------


def _detectar_rostos_perfil(frame_bgr) -> list[tuple[float, float, float]]:
    """Fallback Haar cascade de rosto de perfil, pra quando o MediaPipe não acha nada.
    Degrada pra lista vazia se o cascade não estiver disponível no pacote opencv
    instalado (alguns builds de `opencv-python-headless` não trazem os XML de dados)."""
    global _cascade_perfil
    import cv2

    if _cascade_perfil is None:
        caminho = cv2.data.haarcascades + "haarcascade_profileface.xml"
        cascade = cv2.CascadeClassifier(caminho)
        _cascade_perfil = cascade if not cascade.empty() else False
    if _cascade_perfil is False:
        return []
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    largura = gray.shape[1]
    achados: list[tuple[float, float, float]] = []
    for x, y, bw, bh in _cascade_perfil.detectMultiScale(
        gray, scaleFactor=1.05, minNeighbors=6, minSize=(20, 20)
    ):
        achados.append((x + bw / 2, y + bh / 2, bh))
    for x, y, bw, bh in _cascade_perfil.detectMultiScale(
        cv2.flip(gray, 1), scaleFactor=1.05, minNeighbors=6, minSize=(20, 20)
    ):
        achados.append((largura - (x + bw / 2), y + bh / 2, bh))
    return achados


_ROTACAO_CV2 = {
    90: "ROTATE_90_CLOCKWISE",
    180: "ROTATE_180",
    270: "ROTATE_90_COUNTERCLOCKWISE",
}


@lru_cache(maxsize=256)
def _detect_face_centers(
    clip_path: str,
    n_samples: int = 8,
    start: float = 0.0,
    end: float | None = None,
    rotacao: int = 0,
) -> tuple[list[list[tuple[float, float, float]]], int, int]:
    """Amostra frames e devolve TODOS os rostos detectados por frame, como
    (cx, cy, altura) em px, + WxH (já no sentido de `rotacao`)."""
    amostras, w, h = _detect_face_observations(clip_path, n_samples, start, end, rotacao)
    return [[face.center for face in faces] for _, faces in amostras if faces], w, h


@lru_cache(maxsize=256)
def _detect_face_observations(clip_path, n_samples=8, start=0.0, end=None, rotacao=0):
    """Caixas/confiança e timestamp por amostra, incluindo frames sem detecção.

    `rotacao` (graus, sentido horário: 0/90/180/270) corrige brutos gravados com
    a câmera deitada — sem isso a detecção de rosto roda no frame torto."""
    import cv2
    import mediapipe as mp

    cap = cv2.VideoCapture(clip_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1
    if rotacao in (90, 270):
        w, h = h, w
    flag = getattr(cv2, _ROTACAO_CV2[rotacao], None) if rotacao in _ROTACAO_CV2 else None
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    first = max(0, int(start * fps))
    last = min(total, int(end * fps)) if end is not None else total
    if n_samples <= 0 or last <= first:
        cap.release()
        return [], w, h
    indices = dict.fromkeys(
        first + int((last - first) * (i + 0.5) / n_samples) for i in range(n_samples)
    )
    samples = []
    try:
        with (
            mp.solutions.face_detection.FaceDetection(
                model_selection=1, min_detection_confidence=0.5
            ) as long_range,
            mp.solutions.face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=0.5
            ) as short_range,
        ):
            for idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ok, frame = cap.read()
                if ok and flag is not None:
                    frame = cv2.rotate(frame, flag)
                faces = (
                    detect_frame(frame, long_range, short_range, _detectar_rostos_perfil)
                    if ok
                    else []
                )
                samples.append((idx / fps, faces))
    finally:
        cap.release()
    return samples, w, h


def _mediana_pessoa(pessoa: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Mediana de cx, cy e fh, cada eixo calculado independentemente."""
    cxs = sorted(f[0] for f in pessoa)
    cys = sorted(f[1] for f in pessoa)
    fhs = sorted(f[2] for f in pessoa)
    meio = len(pessoa) // 2
    return cxs[meio], cys[meio], fhs[meio]


def _rostos_sem_duplicatas(
    rostos: list[tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    """Suprime caixas quase idênticas do mesmo frame."""
    unicos: list[tuple[float, float, float]] = []
    for cx, cy, fh in rostos:
        if fh <= 0:
            continue
        fw = fh * _ROSTO_LARGURA_FRAC
        for i, (px, py, ph) in enumerate(unicos):
            if max(fh, ph) > min(fh, ph) * 1.5:
                continue
            pw = ph * _ROSTO_LARGURA_FRAC
            iw = max(0.0, min(cx + fw / 2, px + pw / 2) - max(cx - fw / 2, px - pw / 2))
            ih = max(0.0, min(cy + fh / 2, py + ph / 2) - max(cy - fh / 2, py - ph / 2))
            intersecao = iw * ih
            uniao = fw * fh + pw * ph - intersecao
            if intersecao / uniao >= 0.7:
                if fh > ph:
                    unicos[i] = (cx, cy, fh)
                break
        else:
            unicos.append((cx, cy, fh))
    return unicos


def _agrupar_rostos_por_frame(
    por_frame: list[list[tuple[float, float, float]]],
    w: float,
) -> list[list[tuple[float, float, float]]]:
    """Associa rostos entre frames, um-para-um."""
    limiar_x = max(1.0, w * 0.15)
    clusters: list[list[tuple[float, float, float]]] = []
    for rostos in por_frame:
        rostos = _rostos_sem_duplicatas(rostos)
        candidatos: list[tuple[float, int, int]] = []
        centros = [_mediana_pessoa(c) for c in clusters]
        for i_rosto, (cx, cy, fh) in enumerate(rostos):
            for i_cluster, (px, py, ph) in enumerate(centros):
                if fh <= 0 or ph <= 0 or max(fh, ph) > min(fh, ph) * 2:
                    continue
                limiar_y = max(fh, ph)
                dx, dy = abs(cx - px), abs(cy - py)
                if dx <= limiar_x and dy <= limiar_y:
                    distancia = math.hypot(dx / limiar_x, dy / limiar_y)
                    distancia += abs(math.log(fh / ph))
                    candidatos.append((distancia, i_cluster, i_rosto))
        usados: set[int] = set()
        associados: set[int] = set()
        for _, i_cluster, i_rosto in sorted(candidatos):
            if i_cluster in usados or i_rosto in associados:
                continue
            clusters[i_cluster].append(rostos[i_rosto])
            usados.add(i_cluster)
            associados.add(i_rosto)
        for i_rosto, rosto in enumerate(rostos):
            if i_rosto not in associados:
                clusters.append([rosto])
    return clusters


def _falante_por_movimento_boca(
    clip_path: str,
    start: float,
    end: float,
    disputados: list[list[tuple[float, float, float]]],
    w: float,
) -> list[tuple[float, float, float]] | None:
    """Desempate por movimento labial entre clusters em disputa."""
    import cv2
    import mediapipe as mp

    cap = cv2.VideoCapture(clip_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    idx_ini = max(0, int(start * fps))
    idx_fim = min(total, int(end * fps))
    if idx_fim <= idx_ini:
        cap.release()
        return None

    delta_frames = max(1, round(_BOCA_DELTA_SEG * fps))
    pontos = [
        idx_ini + int((idx_fim - idx_ini) * (i + 0.5) / _BOCA_N_PONTOS)
        for i in range(_BOCA_N_PONTOS)
    ]
    centros = {id(c): sum(r[0] for r in c) / len(c) for c in disputados}
    pontuacao = dict.fromkeys((id(c) for c in disputados), 0.0)

    with mp.solutions.face_detection.FaceDetection(
        model_selection=1, min_detection_confidence=0.5
    ) as fd:
        for idx in pontos:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok1, f1 = cap.read()
            cap.set(cv2.CAP_PROP_POS_FRAMES, min(idx + delta_frames, idx_fim - 1))
            ok2, f2 = cap.read()
            if not ok1 or not ok2:
                continue
            fh, fw = f1.shape[:2]
            res = fd.process(cv2.cvtColor(f1, cv2.COLOR_BGR2RGB))
            for d in res.detections or []:
                bb = d.location_data.relative_bounding_box
                x, y = int(bb.xmin * fw), int(bb.ymin * fh)
                bw, bh = int(bb.width * fw), int(bb.height * fh)
                if bw <= 0 or bh <= 0:
                    continue
                cx = x + bw / 2
                alvo = min(disputados, key=lambda c: abs(centros[id(c)] - cx))
                if abs(centros[id(alvo)] - cx) > w * 0.15:
                    continue
                my0, my1 = max(0, y + round(bh * 0.65)), min(fh, y + bh)
                mx0, mx1 = max(0, x), min(fw, x + bw)
                if my1 <= my0 or mx1 <= mx0:
                    continue
                r1 = cv2.cvtColor(f1[my0:my1, mx0:mx1], cv2.COLOR_BGR2GRAY)
                r2 = cv2.cvtColor(f2[my0:my1, mx0:mx1], cv2.COLOR_BGR2GRAY)
                if r1.shape != r2.shape or r1.size == 0:
                    continue
                pontuacao[id(alvo)] += float(cv2.absdiff(r1, r2).mean())
    cap.release()

    valores = sorted(pontuacao.values(), reverse=True)
    if not valores or valores[0] <= 0:
        return None
    if len(valores) >= 2 and valores[0] < valores[1] * _BOCA_VANTAGEM_MIN:
        return None
    vencedor_id = max(pontuacao, key=lambda k: pontuacao[k])
    return next(c for c in disputados if id(c) == vencedor_id)


def _pessoa_dominante(
    por_frame: list[list[tuple[float, float, float]]],
    w: float,
    clip_path: str | None = None,
    start: float = 0.0,
    end: float | None = None,
    pista_posicao_falante: float | None = None,
) -> list[tuple[float, float, float]]:
    """Escolhe uma track consistente de rosto ao longo do trecho."""
    clusters = _agrupar_rostos_por_frame(por_frame, w)
    cluster_inicial = clusters[0] if por_frame and por_frame[0] else None

    if not clusters:
        return []
    total_frames = len(por_frame)
    candidatos_reais = [c for c in clusters if len(c) / total_frames >= _PARTICIPACAO_MIN_INICIO]
    disputados = candidatos_reais
    if len(disputados) >= 2:
        maior, segundo = sorted((len(c) for c in disputados), reverse=True)[:2]
        if segundo < maior * _DISPUTA_RAZAO_MIN:
            disputados = []
    if len(disputados) >= 2:
        if pista_posicao_falante is not None:
            mais_perto = min(
                disputados,
                key=lambda c: abs((sum(r[0] for r in c) / len(c)) - pista_posicao_falante),
            )
            if abs(_mediana_pessoa(mais_perto)[0] - pista_posicao_falante) <= w * 0.15:
                return mais_perto
        if clip_path is not None:
            fim = end if end is not None else start + 5.0
            pela_boca = _falante_por_movimento_boca(clip_path, start, fim, disputados, w)
            if pela_boca is not None:
                return pela_boca
    if (
        cluster_inicial is not None
        and len(cluster_inicial) / total_frames >= _PARTICIPACAO_MIN_INICIO
    ):
        return cluster_inicial
    return max(clusters, key=len)


# ---------------------------------------------------------------------------
# Microfone (opcional — YOLO-World)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=256)
def _detectar_mic_candidatos(
    clip_path: str, start: float, end: float
) -> tuple[tuple[float, float], ...]:
    """Amostra frames e roda YOLO-World pra achar candidatos a microfone. Degrada
    graciosamente (devolve `()`) se `ultralytics` não estiver instalado ou o
    modelo não estiver disponível no disco."""
    global _modelo_mic
    try:
        import cv2

        with _lock_modelo_mic:
            if _modelo_mic is None:
                from ultralytics import YOLOWorld

                if not os.path.isfile(_MODELO_MIC):
                    return ()
                _modelo_mic = YOLOWorld(_MODELO_MIC)
                if _PROMPT_MIC not in _modelo_mic.names.values():
                    _modelo_mic = None
                    return ()
    except Exception as e:
        log.warning("detecção de microfone indisponível (%s) — segue só com o rosto", e)
        return ()

    cap = cv2.VideoCapture(clip_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    idx_ini = max(0, int(start * fps))
    idx_fim = min(total, int(end * fps))
    if idx_fim <= idx_ini:
        idx_ini, idx_fim = 0, total
    idxs = [
        idx_ini + int((idx_fim - idx_ini) * (i + 0.5) / _MIC_N_SAMPLES)
        for i in range(_MIC_N_SAMPLES)
    ]
    candidatos: list[tuple[float, float]] = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok:
            continue
        try:
            with _lock_modelo_mic:
                res = _modelo_mic.predict(frame, verbose=False, imgsz=640, conf=_MIC_CONF_MIN)[0]
        except Exception:
            continue
        for box in res.boxes:
            x1, _, x2, _ = box.xyxy[0].tolist()
            candidatos.append(((x1 + x2) / 2, x2 - x1))
    cap.release()
    return tuple(candidatos)


def _detectar_mic_x(
    clip_path: str, start: float, end: float, face_cx: float
) -> tuple[float, float] | None:
    """Acha o microfone mais perto do rosto dominante."""
    candidatos = _detectar_mic_candidatos(clip_path, start, end)
    if not candidatos:
        return None
    return min(candidatos, key=lambda c: abs(c[0] - face_cx))


# ---------------------------------------------------------------------------
# API pública deste módulo
# ---------------------------------------------------------------------------


def compute_face_crop(
    clip_path: str,
    start: float = 0.0,
    end: float | None = None,
    pista_posicao_falante: float | None = None,
    aspect_w: int = 9,
    aspect_h: int = 16,
    rotacao: int = 0,
) -> tuple[int, int, int, int] | None:
    """Detecta o rosto dominante e retorna o retângulo de crop (x, y, w, h) no
    aspecto pedido (9:16 pra social, 16:9 pra YouTube), já considerando
    `rotacao` (0/90/180/270 — bruto gravado com a câmera deitada). Usa a
    **mediana** dos rostos da pessoa mais consistente e enquadra com
    zoom/headroom. Sem rosto detectado no trecho → devolve `None` (quem chama
    decide o fallback)."""
    duration = (end - start) if end is not None else 5.0
    count = max(8, min(40, round(duration * 2)))
    por_frame, w, h = _detect_face_centers(
        clip_path, n_samples=count, start=start, end=end, rotacao=rotacao
    )
    if len(por_frame) / count < _COBERTURA_MIN_FRAC:
        return None
    pessoa = _pessoa_dominante(
        por_frame, w, clip_path=clip_path, start=start, end=end,
        pista_posicao_falante=pista_posicao_falante,
    )
    if not pessoa:
        return None
    cx, cy, fh = _mediana_pessoa(pessoa)
    return _crop_window(w, h, cx, cy, fh, aspect_w=aspect_w, aspect_h=aspect_h)


def mapear_posicoes_das_pessoas(clip_path: str, blocos: list[list[float]]) -> list[float]:
    """Amostra TODOS os blocos e devolve o centro X de cada pessoa distinta
    consistente."""
    amostras: list[list[tuple[float, float, float]]] = []
    w: float | None = None
    for start, end in blocos:
        duracao = end - start
        n_samples = max(10, min(60, round(duracao * 4)))
        por_frame, w, _h = _detect_face_centers(
            clip_path, n_samples=n_samples, start=float(start), end=float(end)
        )
        amostras.extend(por_frame)
    if w is None or not amostras:
        return []
    clusters = _agrupar_rostos_por_frame(amostras, w)
    total = sum(len(c) for c in clusters)
    if total == 0:
        return []
    relevantes = [c for c in clusters if len(c) / total >= _POSICAO_PESSOA_MIN_FRAC]
    return sorted(sum(r[0] for r in c) / len(c) for c in relevantes)


def compute_crop_dois_falantes(
    clip_path: str,
    start: float,
    end: float,
    posicoes_conhecidas: list[float] | None = None,
) -> tuple[int, int, int, int] | None:
    """Enquadramento aberto pra um bate-volta (as duas pessoas no quadro, sem
    zoom)."""
    por_frame, w, h = _detect_face_centers(clip_path, n_samples=10, start=start, end=end)
    if len(por_frame) / 10 < _COBERTURA_MIN_FRAC:
        return None
    limiar = w * 0.15
    clusters = _agrupar_rostos_por_frame(por_frame, w)
    relevantes = [c for c in clusters if len(c) >= 1]
    if len(relevantes) < 2:
        return None
    duas = sorted(relevantes, key=len, reverse=True)[:2]
    pessoas = [_mediana_pessoa(p) for p in duas]
    pessoas.sort(key=lambda p: p[0])
    (cx_a, cy_a, fh_a), (cx_b, cy_b, fh_b) = pessoas

    if posicoes_conhecidas:
        margem = limiar
        tem_terceira_no_meio = any(cx_a + margem < p < cx_b - margem for p in posicoes_conhecidas)
        if tem_terceira_no_meio:
            return None

    fh_menor = min(fh_a, fh_b)
    ch_rosto = round(fh_menor / _BATE_VOLTA_ZOOM)
    folga = max(fh_a, fh_b) * 0.1
    esquerda = max(0.0, min(cx - fh * _ROSTO_LARGURA_FRAC / 2 for cx, _, fh in pessoas) - folga)
    direita = min(float(w), max(cx + fh * _ROSTO_LARGURA_FRAC / 2 for cx, _, fh in pessoas) + folga)
    topo = max(0.0, min(cy - fh * (0.5 + _MARGEM_CABELO_FRAC) for _, cy, fh in pessoas))
    base = min(float(h), max(cy + fh / 2 for _, cy, fh in pessoas))
    cw_encaixe = math.ceil(direita) - math.floor(esquerda)
    ch_encaixe = max(math.ceil(cw_encaixe * 16 / 9), math.ceil(base) - math.floor(topo))
    ch = min(h, max(ch_rosto, ch_encaixe))
    cw = round(ch * 9 / 16)
    if cw > w:
        cw, ch = w, min(h, round(w * 16 / 9))

    x_min, x_max = max(0, math.ceil(direita - cw)), min(w - cw, math.floor(esquerda))
    y_min, y_max = max(0, math.ceil(base - ch)), min(h - ch, math.floor(topo))
    if x_min > x_max or y_min > y_max:
        return None
    meio = (cx_a + cx_b) / 2
    x = int(min(max(meio - cw / 2, x_min), x_max))
    yc = (cy_a + cy_b) / 2
    y = int(min(max(yc - ch * _BATE_VOLTA_POS_Y, y_min), y_max))
    if not (x <= esquerda and direita <= x + cw and y <= topo and base <= y + ch):
        return None
    return x, y, cw, ch


def _pessoa_dominante_agregada(
    por_frame: list[list[tuple[float, float, float]]],
    w: float,
) -> list[tuple[float, float, float]]:
    """Escolhe a track mais frequente entre vários blocos não contíguos
    ."""
    clusters = _agrupar_rostos_por_frame(por_frame, w)
    return max(clusters, key=len, default=[])


def compute_face_crop_agregado(
    clip_path: str,
    blocos: list[tuple[float, float]],
    aspect_w: int = 9,
    aspect_h: int = 16,
    rotacao: int = 0,
) -> tuple[int, int, int, int] | None:
    """Como `compute_face_crop`, mas agrega as amostras de TODOS os `blocos`
    informados antes de decidir a pessoa dominante — um crop ESTÁVEL pra vários
    trechos da mesma câmera/tomada, em vez de recalcular (e tremer) a cada
    trecho isolado."""
    todas_amostras: list[list[tuple[float, float, float]]] = []
    w = h = None
    n_samples_total = 0
    for start, end in blocos:
        duracao = end - start
        n_samples = max(8, min(40, round(duracao * 2)))
        n_samples_total += n_samples
        por_frame, w, h = _detect_face_centers(
            clip_path, n_samples=n_samples, start=start, end=end, rotacao=rotacao
        )
        todas_amostras.extend(por_frame)
    cobertura = len(todas_amostras) / n_samples_total if n_samples_total else 0
    if w is None or n_samples_total == 0 or cobertura < _COBERTURA_MIN_FRAC:
        return None
    pessoa = _pessoa_dominante_agregada(todas_amostras, w)
    if not pessoa:
        return None
    cx, cy, fh = _mediana_pessoa(pessoa)
    return _crop_window(w, h, cx, cy, fh, aspect_w=aspect_w, aspect_h=aspect_h)
