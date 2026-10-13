---
description: Etapa 3.5 — limpa ruído e calibra o loudness do corte contra o alvo do STYLE-GUIDE do cliente
argument-hint: "[pasta do vídeo em EDIÇÕES] [observações opcionais]"
context: fork
agent: engenheiro-de-audio
---

Projeto: raiz `1 - VIVA VOZ EDITS`. Leia `CLAUDE.md` só na parte que se aplica à sua etapa.
Pasta do vídeo e observações do usuário: $ARGUMENTS

Rode a etapa 3.5 em `edit/corte.mp4`: meça o loudness, compare com o alvo de LUFS da seção "Áudio" do STYLE-GUIDE do cliente e, se estiver fora, recorrija chamando o backend de novo. Registre o resultado em `edit/verify/audio.md`. Responda com LUFS medido, alvo e se aprovou ou corrigiu.

Regras de economia: leia só `edit/corte.mp4`, `edit/edl.json` e a seção "Áudio" do STYLE-GUIDE — não releia transcrições nem o plano.
