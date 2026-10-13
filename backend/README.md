# VivaVoz Corte Backend

Backend HTTP de corte e enquadramento 9:16, para o agente `cortador` (etapa 3 do
pipeline VivaVoz/Orquestra) chamar em vez de decidir sozinho na mão.

## Instalar

```bash
cd backend
pip install -e .
# com detecção de microfone (opcional, pesado — ultralytics/YOLO-World):
pip install -e ".[mic]"
```

## Rodar

```bash
uvicorn app.main:app --reload
```

Sobe em `http://localhost:8000` por padrão (o agente `cortador` usa essa URL por
padrão, configurável via `VIVAVOZ_BACKEND_URL`).

## Endpoints

- `POST /enquadramento` — `{video_path, start, end, num_falantes?}` → `{x, y, largura, altura}` (janela de crop 9:16).
- `POST /corte` — `{trechos: [{source, start, end, crop?}], normalizar_audio?}` → `{out_path}` (vídeo cortado/concatenado).
- `POST /detectar-silencio` — `{video_path, threshold_db?, min_duration_sec?}` → intervalos de silêncio + trechos úteis (auxiliar, best-effort).
- `GET /saude` — healthcheck.

## Como funciona cada módulo

- `app/reframe.py` — detecta o rosto dominante por amostragem de frames (MediaPipe,
  fallback Haar para perfil), escolhe quem fala quando há disputa (desempate por
  movimento labial) e calcula a janela de crop 9:16 com zoom, headroom de cabelo
  e ancoragem opcional de microfone (YOLO-World, degrada sem erro se ausente).
- `app/face_detection.py` — detecção de rosto por frame usada pelo `reframe.py`.
- `app/types.py` — tipos de dados compartilhados (`Word`, `FaceObservation`).
- `app/cut.py` — corta cada trecho com fade de áudio e crop opcional, concatena
  e normaliza o áudio (loudnorm, EBU R128).
- `app/silence.py` — detecção de silêncio via filtro `silencedetect` do ffmpeg,
  auxiliar/best-effort (o corte principal é guiado por roteiro, não por silêncio).

`compute_face_crop` identifica o falante só por sinal visual (sem áudio) — mais
simples de operar, suficiente pro caso de uso. `/corte` recebe trechos
explícitos com `crop` opcional por trecho (calculado via `/enquadramento`), sem
decisão automática de corte de câmera ou legenda embutida.

## Validar sem subir o servidor

```bash
python -c "from app.main import app"
```
