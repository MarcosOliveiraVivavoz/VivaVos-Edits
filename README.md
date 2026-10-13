# Edição de vídeo por agentes

Projeto para editar vídeos curtos de clientes no VS Code com o Claude Code + skill **video-use**.
Cada etapa (roteiro, cortes, cor, títulos, grafismos, legendas, revisão) tem um agente próprio em `.claude/agents/`. O passo a passo que o Claude segue está em `CLAUDE.md`.

## Antes da primeira vez (5 min)

1. Confira se a skill está instalada: no Terminal, `ls ~/.claude/skills/video-use` precisa listar arquivos (`SKILL.md`, `helpers/`…).
2. A chave da ElevenLabs fica no `.env` **dentro da pasta do video-use**, não aqui.
3. **Ative os agentes** (uma vez só): no terminal do VS Code (**Ctrl + `**), rode
   `sh ativar.sh`
   Sempre que algo em `agentes/` ou `comandos/` mudar, rode de novo.
4. Instale as fontes aproximadas do guia (Google Fonts, gratuitas): Poppins, Playfair Display e Cormorant Garamond. Se a agência tiver as fontes originais, coloque em `MODELO CLÍNICAS/Versailles/assets/fontes/`.

## Para editar um vídeo

1. **Brutos do dia** vão em `MODELO CLÍNICAS/Versailles/VIDEOS BRUTOS/CRIATIVO N - DD-MM-AA/`, do jeito que saíram da câmera.
2. **Roteiros** vão em `Versailles/ROTEIROS/` (um `.md` por roteiro; modelo em `ROTEIRO-PADRAO.md`).
3. **Um vídeo final = uma pasta** em `Versailles/EDIÇÕES/<AAAA-MM-DD-rNN-tema>/` com:
   - `roteiro.md` (cópia do roteiro desse vídeo)
   - `fontes.md` (quais brutos usar e o que falta)
   - atalhos para os brutos (não ocupam espaço). Peça ao Claude: *"cria a pasta de edição do roteiro NN da gravação DD-MM-AA"*.
4. Imagens de apoio em `Versailles/assets/cenas de complemento/`; fotos de antes e depois em `assets/antes-depois/` (só reais e autorizadas).
5. No Claude Code (✳ → New session), mande:

> Edita o vídeo `MODELO CLÍNICAS/Versailles/EDIÇÕES/2026-10-08-r05-o-detalhe-que-faz-diferenca`. Segue as etapas do CLAUDE.md.

6. Ele para duas vezes para você aprovar: no **plano de cenas** e no **preview**. O vídeo final sai em `.../edit/final.mp4`.

## Uma etapa por vez (recomendado)

No Claude Code, digite `/v` e escolha a etapa, seguida da pasta. Ex.:
```
/v2-roteiro MODELO CLÍNICAS/Versailles/EDIÇÕES/2026-10-08-r05-o-detalhe-que-faz-diferenca
/v3-corte   MODELO CLÍNICAS/Versailles/EDIÇÕES/2026-10-08-r05-o-detalhe-que-faz-diferenca  manter "só que ainda mais confiante"
```
Lista completa no `CLAUDE.md` (seção "Comandos por etapa").

## Pedir correções

Fale o que mudar e em que segundo. Ex.: "aos 12 s troca a palavra-chave para *sem exageros*" ou "legenda um pouco menor". Só a etapa afetada é refeita.

## Cliente novo

Copie `_modelo-cliente/` para dentro do segmento certo (ex.: `MODELO ESCOLAS/<nome>/`), preencha `brief.md` e `STYLE-GUIDE.md` e coloque quadros de 3–4 vídeos aprovados em `REFERÊNCIAS/frames/`.

## Git

Vídeos e a pasta `edit/` ficam fora do Git (`.gitignore`). Versione só guias, agentes e briefs.
