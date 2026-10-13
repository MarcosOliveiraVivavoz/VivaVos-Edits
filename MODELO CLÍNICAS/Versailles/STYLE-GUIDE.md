# STYLE-GUIDE — Clínica Versailles

Extraído de 4 vídeos aprovados (out/2026). Quadros de referência em `REFERÊNCIAS/frames/` — **olhe os quadros antes de criar qualquer grafismo**.

⚠️ Fontes e medidas são aproximações feitas a partir dos quadros. Calibre no primeiro preview e, se a agência tiver as fontes originais, coloque em `assets/fontes/` e atualize este arquivo.

## 1. Formato

- Vertical 9:16. Entrega em 1080×1920, 30 fps, H.264 + AAC.
- Duração alvo: **20 a 40 s**.
- Quem fala olha para a câmera, enquadramento de cintura para cima, centralizado.
- Cortes secos entre tomadas e cenários diferentes são bem-vindos (troca de ambiente renova a atenção). Ritmo: uma troca de plano ou de grafismo a cada 3–6 s.

## 2. Estrutura narrativa

1. **Gancho (0–3 s):** pergunta ou afirmação forte com título animado (seção 4) ou caixa de pergunta (seção 6.2).
2. **Desenvolvimento:** explicação curta, palavras-chave em destaque.
3. **Prova:** fotos de antes e depois, demonstração em close ou depoimento de paciente.
4. **Fecho/CTA (últimos 2–3 s):** frase de chamada. CTA padrão: "Pode te ajudar! **marque agora!**"

## 3. Legendas (palavra por palavra)

- 1 a 3 palavras por vez, **caixa normal** (não usar maiúsculas), pontuação mantida.
- Branco, sem contorno, sombra suave escura. Tamanho pequeno e elegante — nunca o estilo "Hormozi" grande.
- Posição: **meio do quadro, na altura do peito** (cerca de 58–62% da altura, de cima para baixo).
- Fonte padrão: sans geométrica regular (aprox. **Poppins Regular**). Variante elegante (quadro 07): serifada regular (aprox. **Cormorant Garamond**). Use uma só por vídeo.
- Legenda **some** enquanto um título ou palavra-chave grande estiver na tela.
- Estilo inicial para o video-use (calibrar no preview):
  `FontName=Poppins,Fontsize=11,PrimaryColour=&H00FFFFFF,BorderStyle=1,Outline=0,Shadow=1,BackColour=&H80000000,Alignment=2,MarginV=110`

## 4. Títulos animados (gancho e palavras-chave)

Sistema de tipografia mista — é a assinatura da marca (quadros 01, 05, 10, 12, 14, 17):

- Palavra comum: sans regular ou light (aprox. Poppins Light/Regular).
- Palavra de ênfase: **sans extra-bold itálico** (aprox. Poppins ExtraBold Italic). Ex.: "A ***verdade***", "***para você***".
- Linha de respiro: sans light com **espaçamento largo entre letras** (ex.: "n e m  t o d o").
- Palavra emocional/técnica: **serifada itálica** (aprox. Playfair Display Italic). Ex.: "*preenchimento*".
- Cor: branco com sombra suave. Alinhamento centralizado. Largura máx. 80% do quadro. Posição: 55–65% da altura.
- Entrada: palavra por palavra, sincronizada com a fala; cada palavra entra com fade + subida de ~12 px + leve desfoque saindo (≈250 ms, easing cúbico). Saída: fade de 200 ms.
- Números em destaque podem ser grandes e à esquerda (quadro 14: "**1**ml Será que…").

## 5. Cor

- Look natural, claro e limpo; pele bonita e fiel. Ambiente da clínica em tons neutros e quentes.
- Começar com `none`. Usar `warm_cinematic` só se o bruto vier frio. Nunca saturar a pele.

## 6. Grafismos

### 6.1 Cards de antes e depois (quadros 02, 06)
- 1 a 4 fotos reais de `assets/antes-depois/`, em cartões com **cantos bem arredondados** (raio ≈ 6% da largura do cartão), sem borda, sombra suave.
- Cada cartão ≈ 28–32% da largura do quadro. Lado a lado ou empilhados, sobre o torso, sem cobrir o rosto de quem fala.
- Entrada: sobe + fade (250 ms), leve escala 0,95→1. Permanece enquanto o assunto é falado (3–6 s). Saída: fade.

### 6.2 Caixa de pergunta estilo Instagram (quadro 08)
- Cabeçalho preto arredondado com "Faça uma pergunta." em branco; corpo branco com a pergunta em preto (sans, centralizado).
- Topo do quadro (≈ 4–10% da altura), largura ≈ 70%. Entra com "pop" (escala 0,9→1, 200 ms) no início e fica durante o gancho.

### 6.3 Selo / pílula (quadro 11)
- Pílula branca, cantos totalmente arredondados, texto preto sans medium, 1–2 linhas. Ex.: "Protocolo totalmente personalizado."
- Perto do quadril/terço inferior. Entrada com pop; 2–4 s na tela.

### 6.4 Marcação em imagem de apoio (quadro 15)
- Em close de produto/procedimento: círculo de traço escuro fino desenhado em volta do detalhe (animação de "desenhar", ≈ 600 ms) + rótulo grande branco bold (ex.: "1ml") com linha guia.

### 6.5 Transições (quadros 04, 09, 16)
- **Clarão de cor** entre tomadas: sobreposição quente (laranja/amarelo) ou rosa, 6–10 frames.
- Ocasional: tela cheia de gradiente rosa-claro com uma palavra da legenda (quadro 09), ≤ 0,5 s.
- Nada de transições "PowerPoint" (giro, cubo, cortina).

### 6.6 CTA final (quadro 03)
- Duas linhas no terço inferior: "Pode te ajudar!" (sans bold) + "**marque agora!**" (sans extra-bold itálico). Últimos 2–3 s.

## 6.7 Logo e identidade visual
- Arquivos em `assets/identidade-visual/` (logos em `logos/`, de preferência PNG com fundo transparente ou SVG; manual da marca e paleta, se houver).
- Os vídeos de referência **não usam logo na tela**. Padrão: sem logo durante o vídeo. ⚠️ Aguardando definição do usuário se entra logo no cartão final do CTA.
- Cores de grafismos (pílula, caixa de pergunta, transições) devem respeitar a paleta do manual quando ele estiver na pasta; se houver conflito com este guia, perguntar.

## 7. Áudio

Alvo de loudness: **-16 LUFS integrado, true peak -1.5 dBTP, LRA 11** — mesmo padrão já usado no Desilenciar (`loudnorm=I=-16:TP=-1.5:LRA=11`). Calibrado medindo `Versailles Vídeo 1` (editado aprovado): -16.03 LUFS, bate quase exato. ⚠️ `IMG_0652.MOV` (outra referência recebida) mediu -26.86 LUFS — bem fora do padrão; tratado como outlier (provável prévia sem masterização final) até o cliente confirmar. Voz limpa em primeiro plano, sem cortar respiração no meio de palavra, música opcional bem baixa (−20 a −24 dB sob a voz).

## 8. Anti-lista

- Legenda grande, amarela, em maiúsculas ou com contorno grosso.
- Emojis, setas de "meme", efeitos sonoros caricatos.
- Fotos de antes e depois que não vieram da clínica.
- Cobrir o rosto de quem fala com qualquer grafismo.
