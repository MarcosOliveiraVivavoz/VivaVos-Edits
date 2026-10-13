---
description: Etapa 8 — revisão de qualidade do preview
argument-hint: "[pasta do vídeo em EDIÇÕES] [observações opcionais]"
context: fork
agent: revisor
---

Projeto: raiz `1 - VIVA VOZ EDITS`. Leia `CLAUDE.md` só na parte que se aplica à sua etapa.
Pasta do vídeo e observações do usuário: $ARGUMENTS

Rode a etapa 8: renderize `edit/preview.mp4` se não existir (`--preview`) e escreva `edit/verify/relatorio.md`. Marque em `edit/status.md` APROVADO ou CORRIGIR.

Regras de economia: leia só os arquivos necessários para esta etapa (`roteiro.md`, `fontes.md`, `edit/status.md` e as saídas da etapa anterior); não releia transcrições JSON brutas se `edit/takes_packed.md` existir; use `timeline_view.py` só em pontos de dúvida.
