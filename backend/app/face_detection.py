"""Detecção de rosto por frame: MediaPipe long-range com tiles, fallback
short-range espelhado, fallback Haar de perfil, dedupe por IoU e supressão de
rosto-em-tela (TV/monitor ao fundo) via YOLO-World opcional."""

from __future__ import annotations

import logging
import math
import os
import threading
from dataclasses import replace
from functools import lru_cache

from app.types import FaceObservation

log = logging.getLogger(__name__)
_scene_lock = threading.Lock()


@lru_cache(maxsize=2)
def _scene_model(path, modified_ns):
    from ultralytics import YOLOWorld

    # O checkpoint já contém embeddings COCO de person/tv/laptop. set_classes
    # carregaria outro modelo textual; nunca é necessário neste caminho offline.
    model = YOLOWorld(path)
    if not {"person", "tv", "laptop"}.issubset(set(model.names.values())):
        raise ValueError("modelo de cena sem as classes embutidas necessárias")
    return model


def scene_objects(frame):
    """Caixas de corpo/tela locais; None distingue indisponibilidade de vazio."""
    path = os.getenv("VIVAVOZ_SCENE_MODEL_PATH") or os.getenv("MIC_MODEL_PATH", "yolov8m-world.pt")
    if not os.path.isfile(path):
        return None
    try:
        with _scene_lock:
            model = _scene_model(path, os.stat(path).st_mtime_ns)
            classes = [i for i, name in model.names.items() if name in {"person", "tv", "laptop"}]
            prediction = model.predict(
                frame, imgsz=640, classes=classes, conf=0.2, verbose=False, device="cpu"
            )[0]
            return [
                (
                    model.names[int(box.cls[0])],
                    float(box.conf[0]),
                    tuple(float(v) for v in box.xyxy[0].tolist()),
                )
                for box in prediction.boxes
            ]
    except Exception as exc:
        log.warning("detecção de corpo/tela indisponível: %s", exc)
        return None


def supported_faces(faces, objects):
    """Um rosto em tela nunca é promovido a pessoa, mesmo com corpo na tela."""
    if objects is None:
        return faces
    result = []
    for face in faces:
        cx, cy, fh = face.center
        screens = [
            bbox for name, score, bbox in objects if name in {"tv", "laptop"} and score >= 0.2
        ]
        if any(a <= cx <= c and b <= cy <= d for a, b, c, d in screens):
            continue
        supported = any(
            name == "person"
            and score >= 0.2
            and a <= cx <= c
            and b <= cy <= b + (d - b) * 0.65
            and d - b >= fh * 1.5
            for name, score, (a, b, c, d) in objects
        )
        result.append(replace(face, person_supported=supported))
    return result


def deduplicate(faces: list[FaceObservation]) -> list[FaceObservation]:
    result: list[FaceObservation] = []
    for face in sorted(faces, key=lambda f: -f.score):
        x1, y1, x2, y2 = face.bbox
        if not all(math.isfinite(v) for v in face.bbox) or x2 <= x1 or y2 <= y1:
            continue
        for other in result:
            a, b, c, d = other.bbox
            intersection = max(0, min(x2, c) - max(x1, a)) * max(0, min(y2, d) - max(y1, b))
            union = (x2 - x1) * (y2 - y1) + (c - a) * (d - b) - intersection
            if union and intersection / union >= 0.6:
                break
        else:
            result.append(face)
    return result


def detect_frame(frame, long_range, short_range, profile_detector) -> list[FaceObservation]:
    """Suplementa plano aberto com duas regiões sobrepostas; não baixa confiança.

    O resize global não amplia o rosto relativo à entrada interna do MediaPipe.
    Tiles recuperam perfis pequenos. Short-range espelhado é último recurso,
    pois o ensaio real mostrou falsos em torso quando usado indiscriminadamente.
    """
    import cv2

    height, width = frame.shape[:2]

    def infer(image, detector, name, x_offset=0, mirrored=False):
        ih, iw = image.shape[:2]
        if mirrored:
            image = cv2.flip(image, 1)
        if iw > 640:
            image = cv2.resize(image, (640, max(1, round(ih * 640 / iw))))
        detections = detector.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)).detections or []
        found = []
        for detection in detections:
            bb = detection.location_data.relative_bounding_box
            xa, xb = bb.xmin * iw, (bb.xmin + bb.width) * iw
            if mirrored:
                xa, xb = iw - xb, iw - xa
            bbox = (
                max(0.0, xa + x_offset),
                max(0.0, bb.ymin * ih),
                min(float(width), xb + x_offset),
                min(float(height), (bb.ymin + bb.height) * ih),
            )
            if bbox[3] - bbox[1] >= height * 0.06:
                found.append(FaceObservation(bbox, float(detection.score[0]), name))
        return found

    # Um global fraco não basta para promover roupa/objeto a uma pessoa.
    global_faces = [f for f in infer(frame, long_range, "mp-global") if f.score >= 0.75]
    candidates = list(global_faces)
    if width >= height * 1.25:
        tile_width = math.ceil(width * 0.55)
        for offset in (0, width - tile_width):
            candidates.extend(
                infer(frame[:, offset : offset + tile_width], long_range, "mp-tile", offset)
            )
    candidates = deduplicate(candidates)
    if not candidates:
        candidates = infer(frame, short_range, "mp-profile-mirrored", mirrored=True)
    if not candidates:
        ratio = min(1.0, 640 / width)
        small = cv2.resize(frame, (round(width * ratio), round(height * ratio)))
        for cx, cy, fh in profile_detector(small):
            cx, cy, fh = cx / ratio, cy / ratio, fh / ratio
            if fh >= height * 0.08:
                half_width = fh * 0.85 / 2
                candidates.append(
                    FaceObservation(
                        (cx - half_width, cy - fh / 2, cx + half_width, cy + fh / 2),
                        0.5,
                        "haar-profile",
                    )
                )
    return supported_faces(deduplicate(candidates), scene_objects(frame))
