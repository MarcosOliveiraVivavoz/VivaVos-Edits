# Edição de vídeo por agentes — Orquestra / Viva Voz

Este projeto edita vídeos curtos verticais de clientes usando a skill **video-use** como motor de edição.
O trabalho é dividido em etapas, e cada etapa tem um agente especialista em `.claude/agents/` (fonte editável em `agentes/` e `comandos/`; para ativar, o usuário roda `sh ativar.sh`).

## Regra de ouro

- **Roteiro é lei.** Em edição de roteiro, os agentes só localizam e cortam as falas escritas, na ordem escrita. Ninguém escolhe gancho, cria bloco, improvisa ou reordena. Fala que não existe na gravação é reportada como FALTANDO, nunca substituída.

0. Use **somente a skill `video-use-vivavoz-edits`** (instalada em `.claude/skills/video-use-vivavoz-edits/`, exclusiva deste projeto). **Nunca** use a skill global `video-use`: ela pertence ao fluxo de cortes de podcast. Se `video-use-vivavoz-edits` não aparecer, pare e avise.
1. A skill **video-use-vivavoz-edits** manda no motor: siga o `SKILL.md` dela e as 12 Hard Rules (legenda por último, nunca cortar no meio de palavra, fade de 30 ms em todo corte etc.). Os agentes deste projeto especializam etapas, não substituem regras dela.
2. O **STYLE-GUIDE.md do cliente** manda no visual. Nada de estilo inventado: se algo não estiver no guia, pergunte.
3. Toda resposta ao usuário em **português do Brasil**, direta, sem enfeite.

## Estrutura

Dividido por segmento (estilo de vídeo). Regras e agentes ficam na raiz e valem para todos.

```
agentes/                    → fonte editável dos agentes (copiar para .claude/agents/)
_modelo-cliente/            → copiar para dentro do segmento ao criar um cliente novo
MODELO CLÍNICAS/            → segmento (ex.: Versailles/)
MODELO E-COMMERCE/
MODELO ESCOLAS/
<SEGMENTO>/
  <cliente>/
    STYLE-GUIDE.md          → padrão visual do cliente (fonte da verdade)
    brief.md                → quem fala, público, tom, CTA padrão
    REFERÊNCIAS/frames/     → quadros de vídeos aprovados (olhe antes de criar grafismos)
    assets/antes-depois/    → fotos reais e autorizadas fornecidas pela clínica
    assets/identidade-visual/ → logos (PNG transparente/SVG em logos/), manual da marca, paleta
    assets/fontes/          → fontes da marca (.ttf/.otf)
    assets/cenas de complemento/ → imagens de apoio (procedimento, clínica, produtos)
    ROTEIRO-PADRAO.md       → estrutura que todos os roteiros do cliente seguem
    ROTEIROS/               → biblioteca de roteiros (um .md por vídeo; imagens originais em subpastas por data)
    VIDEOS BRUTOS/CRIATIVO N - DD-MM-AA/   → material gravado, agrupado por criativo (pode ter vários roteiros no mesmo arquivo). Nunca editar aqui
    EDIÇÕES/<AAAA-MM-DD-rNN-tema>/ → UMA pasta por vídeo final: roteiro.md + fontes.md + atalhos para os brutos usados. O video-use trabalha aqui e cria edit/ dentro
```

## Comandos por etapa (rodar UMA etapa por vez)

Cada etapa é um comando que roda o agente dela isolado (contexto próprio, modelo mais barato que resolve). Uso: `/vN-nome <pasta do vídeo> [observações]`.

| Comando | Agente (modelo) | Faz | Para e espera você? |
|---|---|---|---|
| `/v1-transcrever` | transcritor (haiku) | transcrição + takes_packed.md (reaproveita cache) | não |
| `/v2-roteiro` | roteirista (sonnet) | plano de trechos seguindo o roteiro, sem grafismos | **sim** |
| `/v3-corte` | cortador (sonnet) | cortes, limpeza de erros, recorte 9:16 → `corte.mp4` | **sim** (assista) |
| `/v3b-audio` | engenheiro-de-audio (sonnet) | limpa ruído e calibra loudness do corte contra o alvo do STYLE-GUIDE | sim |
| `/v4-cor` | colorista (sonnet) | cor → `corte_cor.mp4` | sim |
| `/v5-titulos` | tipografo (sonnet) | títulos e palavras-chave | sim |
| `/v6-grafismos` | grafismos (sonnet) | selo, pergunta, antes/depois, CTA, transições | sim |
| `/v7-legenda` | legendador (haiku) | legendas palavra por palavra | sim |
| `/v8-revisao` | revisor (sonnet) | relatório de qualidade | sim |
| `/v9-final` | finalizador (haiku) | render `final.mp4` | — |

- O progresso de cada vídeo fica em `edit/status.md`.
- Para economizar: **nova sessão (ou `/clear`) entre vídeos**; dentro do mesmo vídeo pode seguir na mesma sessão, pois cada etapa roda isolada.
- Etapas 4–7 são opcionais: um vídeo pode parar no corte.

## Modos de edição (o usuário escolhe; se não disser, pergunte)

- **Modo CORTE** ("só cortes", "limpeza", "corte bruto"): rode só as etapas 1, 2 e 3. O roteirista escolhe as tomadas seguindo o roteiro; o cortador limpa erros, repetições, pausas e falsos começos. Render em 9:16 (recorte centrado na pessoa) **sem cor, títulos, grafismos, B-roll, música ou legenda**. Saída: `edit/corte.mp4`. No plano, **não** proponha grafismos nem B-roll e não faça perguntas sobre eles.
- **Modo COMPLETO**: todas as etapas. Se já existir um corte aprovado, parta dele sem refazer os cortes.

## Fluxo por etapas (com portões de aprovação)

Ao receber "edita o vídeo X do cliente Y", leia o `roteiro.md` e o `fontes.md` da pasta do vídeo em `EDIÇÕES/` (se não houver, procure o roteiro do mesmo tema em `<SEGMENTO>/Y/ROTEIROS/` e confirme com o usuário qual usar; se não existir roteiro, avise e siga só pela transcrição), `<SEGMENTO>/Y/ROTEIRO-PADRAO.md`, `<SEGMENTO>/Y/STYLE-GUIDE.md`, `<SEGMENTO>/Y/brief.md` e, se existir, `EDIÇÕES/X/edit/project.md`. Depois:

| # | Etapa | Agente | Saída | Portão |
|---|-------|--------|-------|--------|
| 1 | Inventário e transcrição | (video-use direto) | `edit/takes_packed.md` | — |
| 2 | Roteiro e plano de cenas | `roteirista` | `edit/plano.md` | **Aprovação do usuário** |
| 3 | Cortes | `cortador` | `edit/edl.json` (ranges) | — |
| 3.5 | Áudio (ruído + loudness) | `engenheiro-de-audio` | `edit/verify/audio.md` | — |
| 4 | Cor | `colorista` | campo `grade` do EDL | — |
| 5 | Títulos e palavras-chave | `tipografo` | `edit/animations/slot_*` | — |
| 6 | Grafismos (antes/depois, pergunta, selo, marcação, CTA, transições) | `grafismos` | `edit/animations/slot_*` | — |
| 7 | Legendas (sempre por último) | `legendador` | `edit/master.srt` + estilo | — |
| 8 | Preview e revisão | `revisor` | `edit/verify/relatorio.md` | **Aprovação do usuário** |
| 9 | Render final | (video-use direto) | `edit/final.mp4` | — |

- Etapas 4, 5 e 6 podem rodar **em paralelo** (subagentes simultâneos), depois que o plano (2) e os cortes (3) existirem.
- Nunca pule o portão da etapa 2: nada é cortado antes do plano aprovado.
- Correção pedida pelo usuário volta só para a etapa afetada; não retranscreva.
- Ao fim de cada sessão, atualize `edit/project.md` (data, decisões, pendências).

## Como falar com cada agente

Todo briefing de subagente precisa ser autocontido: caminho de saída, trecho exato do STYLE-GUIDE que se aplica, tempos no timeline de saída, o que NÃO fazer e checklist de entrega. Subagente não faz perguntas: se faltar algo, ele devolve a dúvida para o orquestrador.

## Proibido

- Inventar fotos de antes e depois, depoimentos ou números. Só material real em `assets/`.
- Usar fonte, cor ou animação fora do STYLE-GUIDE sem aprovação.
- Entregar `final.mp4` sem o relatório do `revisor` aprovado.
