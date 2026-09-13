"""Paleta de cores da marca VLF Advogados, compartilhada entre as janelas do app."""

# Cores de marca/status: mantidas fixas entre os temas (já contrastam bem em fundo
# claro ou escuro). Cores de superfície (fundo, borda, texto suave): tupla
# (claro, escuro) - o CTk troca sozinha quando o modo de aparência muda.
COR_PRIMARIA = "#201747"
COR_PRIMARIA_HOVER = "#342a63"
COR_PRIMARIA_CLARA = ("#efedf7", "#2e2a42")
COR_TEXTO_SUAVE = ("#6c6c78", "#9a99a8")
COR_FUNDO_CARD = ("#f7f7fb", "#26262e")
COR_BORDA_CARD = ("#e1e1ea", "#3a3a44")
COR_HOVER_NEUTRO = ("#e1e1ea", "#33333d")
COR_SUCESSO = "#1f6f4a"
COR_SUCESSO_HOVER = "#175939"
COR_PERIGO = "#b3261e"
COR_PERIGO_HOVER = ("#fbeceb", "#3a2020")
COR_NEUTRO = "#4b4b58"
COR_NEUTRO_HOVER = "#33333d"
COR_HEADER_FUNDO = ("#f6f5fb", "#201d29")
COR_HEADER_BORDA = ("#e4e2ef", "#3a3646")
COR_CARD_RODANDO = ("#e9f2ed", "#1d3327")
COR_CARD_PAUSADO = ("#f5f0e4", "#3a3122")
# Card já lançado: tom "apagado/arquivado". Era branco puro, indistinguível do card normal
# (#f7f7fb) - o sinal forte é a borda verde do card, esta cor só reforça.
COR_CARD_INSERIDO = ("#e4e2ec", "#1b1b21")

# Laranja da marca (extraído de assets/logo_escritorio.png) - acento pontual,
# reservado para destaque (favorito, relógio), não para todo botão de ação.
COR_MARCA_LARANJA = "#F05423"
COR_MARCA_LARANJA_HOVER = "#d1441a"
COR_MARCA_LARANJA_CLARA = ("#fdeee8", "#3d281f")

# Dropdown de busca (Pasta/Descrição): flutua acima do card, então é um passo mais
# claro que ele no tema claro e um passo mais claro que o fundo da janela no escuro.
COR_POPUP_FUNDO = ("#ffffff", "#2f2f38")
COR_POPUP_TEXTO = ("#26262e", "#e6e6ec")
# Borda mais forte que a dos cards: sem sombra, é só ela que separa o popup do que está atrás.
COR_POPUP_BORDA = ("#c9c7d4", "#43434f")

COR_RELOGIO_DIGITO = "#F05423"
COR_RELOGIO_LEGENDA = "#b9b4cf"
COR_ICONE_NEUTRO = "#8c8c98"  # cor de ícone p/ botões neutros - só um hex (ícone é rasterizado, não segue tupla)
COR_TOOLTIP_FUNDO = "#333333"
COR_TOOLTIP_BORDA = "#4f4f59"  # o balão é escuro nos dois temas e some em cima de card escuro
