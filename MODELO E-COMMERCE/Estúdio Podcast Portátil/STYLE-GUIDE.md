# STYLE-GUIDE — Estúdio Podcast Portátil / Podcut

⚠️ Sem vídeo editado de referência aprovado ainda — a partir de agora os brutos recebidos já são os vídeos reais do cliente (não tem "o jeito certo" pra comparar visualmente). Até o Marcos aprovar o primeiro lote e virar referência, os alvos abaixo são o padrão genérico calibrado no backend, não calibração específica desse cliente.

## 1. Formato

**16:9 horizontal** (YouTube), não 9:16 — confirmado pelo roteiro ("Vídeo de 10 a 12 minutos... Marcos falando para a câmera"). Cortes pra Reels/Shorts a partir do mesmo material saem em 9:16 à parte, se pedido.

## 2. Estrutura narrativa

Segue o roteiro como GUIA de estrutura e ideias, não como texto pra ler palavra por palavra — o Marcos fala com as próprias palavras, na ordem dele, às vezes pulando ou reordenando pontos do roteiro. O cortador precisa casar o CONTEÚDO (a ideia) com o roteiro, não a fala literal, e reportar como faltando qualquer ponto do roteiro que genuinamente não foi gravado — nunca inventar ou copiar o texto do roteiro por cima da fala real.

Bastidor a cortar sempre (não é conteúdo pro público): checagem de gravação ("tá gravando?"), instrução pra equipe, interrupção de terceiros (família, filhos, pets), comentário sobre a própria gravação ("vou fazer só um finalzinho"), som de beijo/despedida fora de cena.

## 3. Legendas
⚠️ Sem referência.

## 4. Títulos animados
⚠️ Sem referência.

## 5. Cor
⚠️ Sem referência.

## 6. Grafismos
⚠️ Sem referência — o roteiro cita lettering/B-roll pontual (ex.: "[TELA: lettering '1. Autoridade']"), mas sem exemplo aprovado de como fica na prática.

## 7. Áudio

Alvo de loudness: **-16 LUFS integrado, true peak -1.5 dBTP, LRA 11** (padrão genérico do backend, mesmo valor usado no Desilenciar — não calibrado especificamente pra este cliente por falta de referência). Gravação é em ambiente doméstico (sala/sofá, sem tratamento acústico), mas **não ativar `remover_ruido` por padrão** — testado e o filtro de denoise (`afftdn`) introduziu artefato audível (som "estourado"/áspero) nesse material, que não tinha ruído de fundo forte o bastante pra justificar. Só ativar se, ouvindo o corte sem o filtro, o ruído de fundo for realmente perceptível incomodando — e comparar antes/depois pra confirmar que não piorou.

## 8. Anti-lista

- Cortar palavra no meio ou cortar sem a folga de respiração (ver Hard Rules da skill).
- Inventar fala que não existe no bruto pra "completar" o roteiro.
- Normalizar volume sem antes limpar ruído.
- Deixar bastidor/interrupção de terceiros no corte final.
