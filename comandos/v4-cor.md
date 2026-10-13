---
description: Etapa 4 — correção de cor sobre o corte aprovado
argument-hint: "[pasta do vídeo em EDIÇÕES] [observações opcionais]"
context: fork
agent: colorista
---

Projeto: raiz `1 - VIVA VOZ EDITS`. Leia `CLAUDE.md` só na parte que se aplica à sua etapa.
Pasta do vídeo e observações do usuário: $ARGUMENTS

Rode a etapa 4 sobre o `edit/edl.json` existente. Mantenha o recorte do campo `grade` e acrescente a cor depois dele. Re-renderize `edit/corte_cor.mp4` com `--preview --no-subtitles`. Atualize `edit/status.md`.

Regras de economia: leia só os arquivos necessários para esta etapa (`roteiro.md`, `fontes.md`, `edit/status.md` e as saídas da etapa anterior); não releia transcrições JSON brutas se `edit/takes_packed.md` existir; use `timeline_view.py` só em pontos de dúvida.
