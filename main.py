"""App de ficha de tempo: múltiplos cronômetros -> linhas na planilha diária do AdvWin."""
import ctypes
import math
import threading
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

import advwin
import atualizador
import estado
import favoritos
import icones
import modelos
import planilha
import retro_preview
from caminhos import pasta_recursos
from widgets import BuscaCombobox, DescricaoModeloEntry, Tooltip

PASTA_ASSETS = pasta_recursos() / "assets"

# Cores de marca/status: mantidas fixas entre os temas (já contrastam bem em fundo
# claro ou escuro). Cores de superfície (fundo, borda, texto suave): tupla
# (claro, escuro) - o CTk troca sozinha quando o modo de aparência muda.
COR_PRIMARIA = "#201747"
COR_PRIMARIA_HOVER = "#342a63"
COR_PRIMARIA_CLARA = ("#efedf7", "#2e2a42")
COR_TEXTO_SUAVE = ("#6c6c78", "#9a99a8")
COR_FUNDO_CARD = ("#f7f7fb", "#26262e")
COR_BORDA_CARD = ("#e1e1ea", "#3a3a44")
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
COR_CARD_INSERIDO = ("#ffffff", "#1f1f26")
COR_DOURADO = "#b8860b"
COR_RELOGIO_DIGITO = "#7cffc4"
COR_RELOGIO_LEGENDA = "#a79cd1"
COR_ICONE_NEUTRO = "#8c8c98"  # cor de ícone p/ botões neutros - só um hex (ícone é rasterizado, não segue tupla)

LIMITE_INATIVIDADE_S = 10 * 60
LARGURA_MIN_CARD = 300

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _segundos_sem_atividade() -> float:
    """Tempo sem mexer o mouse/teclado em todo o sistema (Win32 GetLastInputInfo)."""
    info = _LASTINPUTINFO()
    info.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info))
    ociosidade_ms = ctypes.windll.kernel32.GetTickCount() - info.dwTime
    return ociosidade_ms / 1000


def _bloco(master, rotulo: str) -> ctk.CTkFrame:
    """Frame com um rótulo pequeno em cima, para o campo ser empacotado dentro."""
    frame = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkLabel(frame, text=rotulo, font=ctk.CTkFont(size=11),
                 text_color=COR_TEXTO_SUAVE, anchor="w").pack(anchor="w")
    return frame


def _legenda_cor(master, cor: str, texto: str) -> ctk.CTkFrame:
    """Item de legenda: quadradinho colorido + texto, para explicar as cores dos cards."""
    item = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkFrame(item, fg_color=cor, border_width=1, border_color=COR_BORDA_CARD,
                 width=14, height=14, corner_radius=3).pack(side="left")
    ctk.CTkLabel(item, text=texto, font=ctk.CTkFont(size=11), text_color=COR_TEXTO_SUAVE).pack(side="left", padx=(5, 0))
    return item


def _minutos_cobraveis(elapso_s: float) -> int:
    """Arredonda sempre para cima, em múltiplos de 5 minutos."""
    minutos = elapso_s / 60
    return math.ceil(minutos / 5) * 5


def _fmt_horas_cobraveis(minutos: int) -> str:
    return f"{minutos // 60}:{minutos % 60:02d}"


def _fmt_relogio_total(segundos: float) -> str:
    total_min = int(segundos) // 60
    return f"{total_min // 60}:{total_min % 60:02d}"


def _normalizar_horas_texto(texto: str) -> str:
    """Dígitos puros viram "h:mm" (últimos 2 dígitos = minutos). Ex.: "0035" -> "0:35"."""
    texto = texto.strip()
    if not texto or ":" in texto or not texto.isdigit():
        return texto
    if len(texto) <= 2:
        horas, minutos = 0, int(texto)
    else:
        horas, minutos = int(texto[:-2]), int(texto[-2:])
    return f"{horas}:{minutos:02d}"


class _BarraFluida(ctk.CTkFrame):
    """Frame cujos filhos (adicionados via `adicionar`) quebram em novas linhas quando não
    cabem mais na largura disponível - o reflow roda de novo a cada redimensionamento da
    janela (com debounce, mesmo padrão da grade de cards)."""

    def __init__(self, master, espaco_x: int = 8, espaco_y: int = 6, **kw):
        super().__init__(master, fg_color="transparent", **kw)
        self._espaco_x = espaco_x
        self._espaco_y = espaco_y
        self._itens: list[ctk.CTkBaseClass] = []
        self._job: str | None = None
        self.bind("<Configure>", self._ao_redimensionar)

    def adicionar(self, widget: ctk.CTkBaseClass) -> None:
        self._itens.append(widget)
        self._relayout()

    def _ao_redimensionar(self, event) -> None:
        if self._job is not None:
            self.after_cancel(self._job)
        self._job = self.after(100, self._relayout)

    def _relayout(self) -> None:
        self._job = None
        largura_disponivel = self.winfo_width()
        if largura_disponivel <= 1:  # ainda não desenhado - não quebra linha à toa
            largura_disponivel = 10_000
        x, linha, coluna = 0, 0, 0
        for widget in self._itens:
            largura = widget.winfo_reqwidth() + self._espaco_x
            if coluna > 0 and x + largura > largura_disponivel:
                linha += 1
                coluna = 0
                x = 0
            widget.grid(row=linha, column=coluna, sticky="w", padx=(0, self._espaco_x), pady=(0, self._espaco_y))
            x += largura
            coluna += 1


class TimerCard(ctk.CTkFrame):
    def __init__(self, master, app: "App", timer: estado.Timer):
        super().__init__(master, corner_radius=12, border_width=1,
                          border_color=COR_BORDA_CARD, fg_color=COR_FUNDO_CARD)
        self.app = app
        self.timer = timer

        linha1 = ctk.CTkFrame(self, fg_color="transparent")
        linha1.pack(fill="x", padx=12, pady=(12, 4))

        bloco_data = _bloco(linha1, "Data")
        bloco_data.pack(side="left", padx=(0, 6))
        self.entry_data = ctk.CTkEntry(bloco_data, width=90, placeholder_text="dd/mm/aaaa")
        self.entry_data.insert(0, timer.data or datetime.now().strftime("%d/%m/%Y"))
        self.entry_data.pack()

        self.btn_fixar = ctk.CTkButton(linha1, text="", image=icones.icone("fixar", cor=COR_PERIGO), width=36,
                                        fg_color="transparent", border_width=1, border_color=COR_PERIGO,
                                        hover_color=COR_PERIGO_HOVER, command=self._alternar_fixar)
        self.btn_fixar.pack(side="right", anchor="n")
        Tooltip(self.btn_fixar,
                "Fixar: impede que este card seja apagado por \"Remover\", \"Limpar tudo\" ou \"Excluir tudo\".\n\n"
                "Ao reabrir o app em um novo dia, o cronômetro é zerado (tempo, status e o \"inserido\"), "
                "mas Pasta e Descrição são mantidos.")

        linha2 = ctk.CTkFrame(self, fg_color="transparent")
        linha2.pack(fill="x", padx=12, pady=4)

        bloco_pasta = _bloco(linha2, "Pasta")
        bloco_pasta.pack(fill="x")
        linha_pasta = ctk.CTkFrame(bloco_pasta, fg_color="transparent")
        linha_pasta.pack(fill="x")
        self.cb_pasta = BuscaCombobox(linha_pasta, app.pastas_favoritas, estrito=False, placeholder_text="Pasta",
                                       command=self._atualizar_estrela_pasta)
        self.cb_pasta.set(timer.pasta)
        self.cb_pasta.pack(side="left", fill="x", expand=True)
        self.btn_favoritar_pasta = ctk.CTkButton(linha_pasta, text="", image=icones.icone("estrela", cor=COR_DOURADO),
                                                   width=30, fg_color="transparent", border_width=1,
                                                   border_color=COR_DOURADO, hover_color=COR_CARD_PAUSADO,
                                                   command=self._alternar_favorito_pasta)
        self.btn_favoritar_pasta.pack(side="left", padx=(4, 0))

        linha3 = ctk.CTkFrame(self, fg_color="transparent")
        linha3.pack(fill="x", padx=12, pady=4)

        bloco_descricao = _bloco(linha3, "Descrição")
        bloco_descricao.pack(fill="x")
        linha_descricao = ctk.CTkFrame(bloco_descricao, fg_color="transparent")
        linha_descricao.pack(fill="x")
        self.entry_descricao = DescricaoModeloEntry(linha_descricao, app.modelos_descricao,
                                                      placeholder_text='Descrição (aperte "/" para ver modelos salvos)')
        self.entry_descricao.set(timer.descricao)
        self.entry_descricao.pack(side="left", fill="x", expand=True)
        self.btn_salvar_modelo = ctk.CTkButton(linha_descricao, text="", image=icones.icone("salvar", cor=COR_SUCESSO),
                                                width=30, fg_color="transparent", border_width=1,
                                                border_color=COR_SUCESSO, hover_color=COR_CARD_RODANDO,
                                                command=self._salvar_modelo_descricao)
        self.btn_salvar_modelo.pack(side="left", padx=(4, 0))

        linha4 = ctk.CTkFrame(self, fg_color="transparent")
        linha4.pack(fill="x", padx=12, pady=4)

        bloco_hc = _bloco(linha4, "Horas")
        bloco_hc.pack(side="left", padx=(0, 12))
        self.entry_horas_cobraveis = ctk.CTkEntry(bloco_hc, width=80, placeholder_text="0:00")
        self.entry_horas_cobraveis.insert(0, timer.horas_cobraveis_texto)
        self.entry_horas_cobraveis.pack()
        self.entry_horas_cobraveis.bind("<FocusOut>", self._normalizar_horas_cobraveis)
        self.entry_horas_cobraveis.bind("<Return>", self._normalizar_horas_cobraveis)

        bloco_tempo = _bloco(linha4, "Tempo decorrido")
        bloco_tempo.pack(side="left")
        self.label_tempo = ctk.CTkLabel(bloco_tempo, text=timer.elapso_fmt(),
                                         font=ctk.CTkFont(size=22, weight="bold"), text_color=COR_PRIMARIA)
        self.label_tempo.pack(anchor="w")

        linha5 = ctk.CTkFrame(self, fg_color="transparent")
        linha5.pack(fill="x", padx=12, pady=(4, 12))

        self.btn_iniciar = ctk.CTkButton(linha5, text="", image=icones.icone("play", cor="white"), width=36,
                                          fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HOVER, command=self._iniciar)
        self.btn_iniciar.pack(side="left", padx=2)
        Tooltip(self.btn_iniciar, "Iniciar (Ctrl+Espaço)")
        self.btn_pausar = ctk.CTkButton(linha5, text="", image=icones.icone("pause", cor=COR_PRIMARIA), width=36,
                                         fg_color="transparent", border_width=1, border_color=COR_PRIMARIA,
                                         hover_color=COR_PRIMARIA_CLARA, command=self._pausar)
        self.btn_pausar.pack(side="left", padx=2)
        Tooltip(self.btn_pausar, "Pausar (Ctrl+Espaço)")
        self.btn_parar = ctk.CTkButton(linha5, text="", image=icones.icone("stop", cor="white"), width=36,
                                        fg_color=COR_NEUTRO, hover_color=COR_NEUTRO_HOVER, command=self._parar)
        self.btn_parar.pack(side="left", padx=2)
        Tooltip(self.btn_parar, "Parar")
        self.btn_inserir = ctk.CTkButton(linha5, text="", image=icones.icone("inserir", cor="white"), width=36,
                                          fg_color=COR_SUCESSO, hover_color=COR_SUCESSO_HOVER, command=self._inserir)
        self.btn_inserir.pack(side="left", padx=2)
        Tooltip(self.btn_inserir, "Inserir na planilha")
        self.btn_remover = ctk.CTkButton(linha5, text="", image=icones.icone("remover", cor=COR_PERIGO), width=36,
                                          fg_color="transparent", border_width=1, border_color=COR_PERIGO,
                                          hover_color=COR_PERIGO_HOVER, command=self._remover)
        self.btn_remover.pack(side="left", padx=2)
        Tooltip(self.btn_remover, "Remover")

        if timer.inserido:
            self.btn_inserir.configure(text="✓", image=None, state="disabled", fg_color=COR_SUCESSO_HOVER)
            self._definir_campos_travados(True)
        self._atualizar_aparencia_fixar()
        self._atualizar_cor_card()
        self._atualizar_estrela_pasta()

    def _atualizar_cor_card(self) -> None:
        if self.timer.inserido:
            cor = COR_CARD_INSERIDO
        elif self.timer.status == "rodando":
            cor = COR_CARD_RODANDO
        elif self.timer.status == "pausado":
            cor = COR_CARD_PAUSADO
        else:
            cor = COR_FUNDO_CARD
        self.configure(fg_color=cor)

    def _definir_campos_travados(self, travado: bool) -> None:
        """Bloqueia os campos do card enquanto o lançamento no AdvWin está em voo (evita
        editar pasta/descrição sem saber se o valor enviado já mudou) - também usada para
        manter travado um card que já foi inserido."""
        estado_campo = "disabled" if travado else "normal"
        self.entry_data.configure(state=estado_campo)
        self.cb_pasta.entry.configure(state=estado_campo)
        self.cb_pasta.btn_seta.configure(state=estado_campo)
        self.btn_favoritar_pasta.configure(state=estado_campo)
        self.entry_descricao.entry.configure(state=estado_campo)
        self.btn_salvar_modelo.configure(state=estado_campo)
        self.entry_horas_cobraveis.configure(state=estado_campo)

    def _salvar_modelo_descricao(self) -> None:
        texto = self.entry_descricao.get()
        if not texto or texto.startswith("/"):
            return
        self.app.modelos_descricao[:] = modelos.adicionar_modelo(texto)
        self.btn_salvar_modelo.configure(text="✓", image=None)
        self.after(900, lambda: self.btn_salvar_modelo.configure(
            text="", image=icones.icone("salvar", cor=COR_SUCESSO)))

    def _estilizar_estrela(self, botao: ctk.CTkButton, ativo: bool) -> None:
        if ativo:
            botao.configure(fg_color=COR_DOURADO, border_width=0, image=icones.icone("estrela", cor="white"))
        else:
            botao.configure(fg_color="transparent", border_width=1, border_color=COR_DOURADO,
                             image=icones.icone("estrela", cor=COR_DOURADO))

    def _atualizar_estrela_pasta(self) -> None:
        self._estilizar_estrela(self.btn_favoritar_pasta, self.cb_pasta.get() in self.app.pastas_favoritas)

    def _alternar_favorito_pasta(self) -> None:
        valor = self.cb_pasta.get()
        if not valor:
            return
        self.app.pastas_favoritas[:] = favoritos.alternar_pasta(valor)
        self._atualizar_estrela_pasta()

    def _normalizar_horas_cobraveis(self, event=None) -> None:
        texto = _normalizar_horas_texto(self.entry_horas_cobraveis.get())
        self.entry_horas_cobraveis.delete(0, "end")
        self.entry_horas_cobraveis.insert(0, texto)

    def _coletar_campos(self) -> None:
        t = self.timer
        t.data = self.entry_data.get().strip()
        t.advogado = self.app.advogado_atual
        t.pasta = self.cb_pasta.get()
        t.descricao = self.entry_descricao.get()
        t.horas_cobraveis_texto = self.entry_horas_cobraveis.get().strip()

    def _atualizar_horas_cobraveis_auto(self) -> None:
        texto = _fmt_horas_cobraveis(_minutos_cobraveis(self.timer.elapso_s()))
        self.entry_horas_cobraveis.delete(0, "end")
        self.entry_horas_cobraveis.insert(0, texto)

    def _iniciar(self) -> None:
        self.timer.iniciar()
        self._atualizar_cor_card()
        self.app.salvar()

    def _pausar(self) -> None:
        self.timer.pausar()
        self._atualizar_horas_cobraveis_auto()
        self._atualizar_cor_card()
        self.app.salvar()

    def _parar(self) -> None:
        self.timer.parar()
        self.label_tempo.configure(text=self.timer.elapso_fmt())
        self._atualizar_horas_cobraveis_auto()
        self._atualizar_cor_card()
        self.app.salvar()

    def _inserir(self, ao_concluir=None) -> None:
        """Lança este card no AdvWin (numa fila em segundo plano - a sessão do navegador
        é compartilhada entre cards) e, se der certo, registra a linha no log local.
        `ao_concluir`, se passado, roda ao final (sucesso ou erro) - usado por "Lançar
        todas" para acompanhar o progresso do lote."""
        if not self.app.advogado_valido():
            if ao_concluir:
                ao_concluir()
            return

        self._coletar_campos()
        t = self.timer
        try:
            datetime.strptime(t.data, "%d/%m/%Y")
        except ValueError:
            messagebox.showwarning("Data inválida", 'A data deve estar no formato dd/mm/aaaa (ex.: "14/08/2026").')
            if ao_concluir:
                ao_concluir()
            return
        if not t.pasta:
            messagebox.showwarning("Pasta obrigatória", "Preencha a Pasta antes de lançar no AdvWin.")
            if ao_concluir:
                ao_concluir()
            return

        if t.status != "parado":
            t.parar()
        self.label_tempo.configure(text=t.elapso_fmt())
        # Não chama _atualizar_horas_cobraveis_auto() aqui: sobrescreveria uma edição manual
        # do usuário no campo "Horas cobráveis" com o valor calculado do cronômetro, bem antes
        # do valor ser lido abaixo pra mandar ao AdvWin.
        self._atualizar_cor_card()
        self.app.salvar()

        self.btn_inserir.configure(text="⏳", image=None, state="disabled")
        self._definir_campos_travados(True)
        pasta, data, descricao, horas_texto = t.pasta, t.data, t.descricao, t.horas_cobraveis_texto
        advwin.enfileirar(
            lambda: advwin.lancar_horas(advwin.pagina_advwin(), pasta, data, descricao, horas_texto),
            lambda resultado, erro: self._apos_inserir_advwin(erro, ao_concluir),
        )

    def _apos_inserir_advwin(self, erro, ao_concluir) -> None:
        self.after(0, lambda: self._apos_inserir_advwin_ui(erro, ao_concluir))

    def _apos_inserir_advwin_ui(self, erro: Exception | None, ao_concluir=None) -> None:
        if erro is not None:
            self.btn_inserir.configure(text="", image=icones.icone("inserir", cor="white"), state="normal")
            self._definir_campos_travados(False)
            messagebox.showerror("AdvWin", f"Não foi possível lançar no AdvWin:\n{advwin.mensagem_amigavel(erro)}")
            if ao_concluir:
                ao_concluir()
            return

        t = self.timer
        try:
            data_obj = datetime.strptime(t.data, "%d/%m/%Y").date()
        except ValueError:
            data_obj = datetime.now().date()
        horas_cobraveis = planilha.parse_horas_cobraveis(t.horas_cobraveis_texto)
        if horas_cobraveis is None:
            horas_cobraveis = timedelta(minutes=_minutos_cobraveis(t.elapso_s()))
        planilha.inserir_linha({
            "data": data_obj,
            "advogado": t.advogado,
            "cliente": t.cliente,
            "pasta": t.pasta,
            "descricao": t.descricao,
            "horas": horas_cobraveis,
            "horas_cobraveis": horas_cobraveis,
        }, planilha.CAMINHO_LOG_ADVWIN)

        t.inserido = True
        self.btn_inserir.configure(text="✓", image=None, state="disabled", fg_color=COR_SUCESSO_HOVER)
        self._atualizar_cor_card()
        self.app.salvar()
        if ao_concluir:
            ao_concluir()

    def _remover(self) -> None:
        if self.timer.fixado:
            return
        self.app.remover_card(self)

    def _alternar_fixar(self) -> None:
        self.timer.fixado = not self.timer.fixado
        self._atualizar_aparencia_fixar()
        self.app.salvar()

    def _atualizar_aparencia_fixar(self) -> None:
        if self.timer.fixado:
            self.btn_fixar.configure(fg_color=COR_PERIGO, border_width=0, hover_color=COR_PERIGO_HOVER,
                                      image=icones.icone("fixar", cor="white"))
            self.btn_remover.configure(state="disabled")
        else:
            self.btn_fixar.configure(fg_color="transparent", border_width=1, border_color=COR_PERIGO,
                                      hover_color=COR_PERIGO_HOVER, image=icones.icone("fixar", cor=COR_PERIGO))
            self.btn_remover.configure(state="normal")

    def resetar(self) -> None:
        self.timer = estado.Timer()
        self._definir_campos_travados(False)
        self.entry_data.delete(0, "end")
        self.entry_data.insert(0, datetime.now().strftime("%d/%m/%Y"))
        self.cb_pasta.set("")
        self.entry_descricao.set("")
        self.entry_horas_cobraveis.delete(0, "end")
        self.label_tempo.configure(text=self.timer.elapso_fmt())
        self.btn_inserir.configure(text="", image=icones.icone("inserir", cor="white"),
                                    state="normal", fg_color=COR_SUCESSO)
        self._atualizar_cor_card()
        self._atualizar_estrela_pasta()

    def alternar_iniciar_pausar(self) -> None:
        """Usado pelo atalho de teclado (Ctrl+Espaço) no card com foco."""
        if self.timer.status == "rodando":
            self._pausar()
        else:
            self._iniciar()

    def atualizar_relogio(self) -> None:
        if self.timer.status == "rodando":
            self.label_tempo.configure(text=self.timer.elapso_fmt())


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VLF Advogados - Ficha de Tempo")
        self.geometry("1040x640")
        self.minsize(860, 560)
        self.configure(fg_color=("#ffffff", "#18181d"))

        icone = PASTA_ASSETS / "vlf_icon.ico"
        if icone.exists():
            self.iconbitmap(icone)

        self.listas = planilha.carregar_listas()
        self.modelos_descricao = modelos.carregar_modelos()
        self.pastas_favoritas = favoritos.carregar_pastas()

        timers, advogado_atual = estado.carregar_estado()
        self.advogado_atual = advogado_atual

        hoje = datetime.now().strftime("%d/%m/%Y")
        for t in timers:
            if t.fixado:
                t.data = hoje
                t.status = "parado"
                t.acumulado_s = 0.0
                t.segmento_inicio = None
                t.horas_cobraveis_texto = ""
                t.inserido = False

        ctk.CTkFrame(self, fg_color=COR_PRIMARIA, corner_radius=0, height=5).pack(fill="x")

        header = ctk.CTkFrame(self, fg_color=COR_HEADER_FUNDO, corner_radius=0)
        header.pack(fill="x")

        linha_titulo = ctk.CTkFrame(header, fg_color="transparent")
        linha_titulo.pack(fill="x", padx=24, pady=(16, 8))

        titulo_frame = ctk.CTkFrame(linha_titulo, fg_color="transparent")
        titulo_frame.pack(side="left")

        logo_path = PASTA_ASSETS / "logo_escritorio.png"
        if logo_path.exists():
            imagem = Image.open(logo_path)
            largura = 170
            altura = round(largura * imagem.height / imagem.width)
            self.logo_ctk = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=(largura, altura))
            ctk.CTkLabel(titulo_frame, image=self.logo_ctk, text="").pack(anchor="w")
        else:
            ctk.CTkLabel(titulo_frame, text="VLF Advogados", font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=COR_PRIMARIA).pack(anchor="w")

        advogado_frame = ctk.CTkFrame(linha_titulo, fg_color="transparent")
        advogado_frame.pack(side="left", fill="x", expand=True, padx=(30, 0))

        ctk.CTkLabel(advogado_frame, text="Advogado responsável: *", text_color=COR_TEXTO_SUAVE).pack(side="left", padx=(0, 10))
        self.cb_advogado_geral = BuscaCombobox(
            advogado_frame, self.listas["Advogado"], placeholder_text="Seu nome", command=self._advogado_mudou
        )
        self.cb_advogado_geral.set(advogado_atual)
        self.cb_advogado_geral.pack(side="left", fill="x", expand=True)

        self.btn_tema = ctk.CTkButton(linha_titulo, text="", image=icones.icone("lua", cor=COR_ICONE_NEUTRO),
                                       width=32, height=32, fg_color="transparent", border_width=1,
                                       border_color=COR_HEADER_BORDA, hover_color=COR_PRIMARIA_CLARA,
                                       command=self._alternar_tema)
        self.btn_tema.pack(side="right", padx=(10, 0))
        Tooltip(self.btn_tema, "Alternar modo claro/escuro")

        ctk.CTkFrame(header, fg_color=COR_HEADER_BORDA, height=1).pack(fill="x")

        barra_acoes = ctk.CTkFrame(header, fg_color=COR_PRIMARIA_CLARA, corner_radius=0)
        barra_acoes.pack(fill="x")

        linha_topo = ctk.CTkFrame(barra_acoes, fg_color="transparent")
        linha_topo.pack(fill="x", padx=24, pady=14)

        # Relógio primeiro (side="right"): reserva o espaço dele antes dos botões, senão
        # fica espremido pra fora da janela quando a barra fluida ocupa tudo que sobrar.
        caixa_relogio = self._construir_relogio_total(linha_topo)
        caixa_relogio.pack(side="right", padx=(12, 0))

        linha_acoes = _BarraFluida(linha_topo)
        linha_acoes.pack(side="left", fill="both", expand=True)

        FONTE_BOTAO = ctk.CTkFont(size=13, weight="bold")

        linha_acoes.adicionar(ctk.CTkButton(
            linha_acoes, text="+ Novo cronômetro", width=170, height=40, font=FONTE_BOTAO,
            fg_color=COR_PRIMARIA, text_color="white",
            hover_color=COR_PRIMARIA_HOVER, command=self.novo_card))
        linha_acoes.adicionar(ctk.CTkButton(
            linha_acoes, text="Limpar tudo", width=140, height=40, font=FONTE_BOTAO,
            fg_color="transparent", border_width=1,
            border_color=COR_NEUTRO, text_color=COR_NEUTRO, hover_color=COR_HEADER_BORDA,
            command=self._limpar_tudo))
        self.btn_conectar_advwin = ctk.CTkButton(
            linha_acoes, text="Conectar AdvWin", width=160, height=40, font=FONTE_BOTAO,
            fg_color="transparent", border_width=1,
            border_color=COR_PRIMARIA, text_color=COR_PRIMARIA, hover_color="white",
            command=self._conectar_advwin,
        )
        linha_acoes.adicionar(self.btn_conectar_advwin)
        self.btn_lancar_retroativo = ctk.CTkButton(
            linha_acoes, text="Lançar retroativo (planilha)", width=210, height=40, font=FONTE_BOTAO,
            fg_color="transparent", border_width=1,
            border_color=COR_PRIMARIA, text_color=COR_PRIMARIA, hover_color="white",
            command=self._lancar_retroativo,
        )
        linha_acoes.adicionar(self.btn_lancar_retroativo)
        Tooltip(self.btn_lancar_retroativo,
                "Lança em lote linhas retroativas de uma cópia da planilha de modelo "
                "(aba \"Ficha-Tempo\") que já não foram lançadas no AdvWin.")

        # Separado dos outros de propósito: "Excluir tudo" é irreversível e não deve ficar
        # colado em "Limpar tudo" (nomes parecidos, risco de clique errado).
        linha_acoes.adicionar(ctk.CTkFrame(linha_acoes, fg_color=COR_HEADER_BORDA, width=1, height=32))
        linha_acoes.adicionar(ctk.CTkButton(
            linha_acoes, text="Excluir tudo", width=140, height=40, font=FONTE_BOTAO,
            fg_color="transparent", border_width=1,
            border_color=COR_PERIGO, text_color=COR_PERIGO, hover_color=COR_PERIGO_HOVER,
            command=self._excluir_tudo))

        linha_legenda = ctk.CTkFrame(barra_acoes, fg_color="transparent")
        linha_legenda.pack(pady=(0, 12))
        _legenda_cor(linha_legenda, COR_CARD_RODANDO, "Rodando").pack(side="left", padx=8)
        _legenda_cor(linha_legenda, COR_CARD_PAUSADO, "Pausado").pack(side="left", padx=8)
        _legenda_cor(linha_legenda, COR_CARD_INSERIDO, "Inserido").pack(side="left", padx=8)

        ctk.CTkFrame(self, fg_color=COR_HEADER_BORDA, height=1).pack(fill="x")

        # Rodapé precisa ser empacotado (side="bottom") antes do scroll (fill="both",
        # expand=True) - senão o scroll toma a área toda e não sobra espaço pro rodapé.
        self.rodape = ctk.CTkFrame(self, fg_color=COR_HEADER_FUNDO, corner_radius=0, height=26)
        self.rodape.pack(fill="x", side="bottom")
        self.rodape.pack_propagate(False)
        self.label_salvo = ctk.CTkLabel(self.rodape, text="", font=ctk.CTkFont(size=11), text_color=COR_TEXTO_SUAVE)
        self.label_salvo.pack(side="right", padx=16)

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=("white", "#18181d"))
        self.scroll.pack(fill="both", expand=True, padx=16, pady=16)

        self.cards_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.cards_frame.pack(fill="x")
        self._colunas_configuradas = 0
        self._job_redimensionar: str | None = None
        # Mede/observa self.scroll (largura fixada de fora, pelo layout da janela) - não
        # cards_frame, cuja própria largura pedida depende de quantas colunas o grid interno
        # tem (referência circular: encolhia a janela, mas a largura medida não acompanhava).
        self.scroll.bind("<Configure>", self._ao_redimensionar_cards)

        self.cards: list[TimerCard] = []
        self.btn_inserir_todos = ctk.CTkButton(
            self.scroll, text="Lançar todas no AdvWin", height=40, font=FONTE_BOTAO,
            fg_color=COR_SUCESSO, hover_color=COR_SUCESSO_HOVER, command=self._inserir_todos,
        )
        self.btn_inserir_todos.pack(fill="x", pady=(6, 0))
        for timer in timers:
            self._adicionar_card(timer)
        if not self.cards:
            self._adicionar_card(estado.Timer())
        self._atualizar_total_horas()

        self._instalador_pendente: Path | None = None

        # Ctrl+Espaço/Ctrl+N em vez de só Espaço: os cards têm campos de texto (descrição
        # etc.) onde a barra de espaço precisa continuar digitando um espaço normal.
        self.bind_all("<Control-space>", lambda e: self._atalho_play_pause())
        self.bind_all("<Control-n>", lambda e: self.novo_card())

        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        self.after(1000, self._tick)
        self.after(30_000, self._checar_inatividade)
        self.after(3000, self._checar_atualizacao)

    def _construir_relogio_total(self, master) -> ctk.CTkFrame:
        """Mostra o total de horas trabalhadas hoje, estilizado como um relógio digital."""
        caixa = ctk.CTkFrame(master, fg_color=COR_PRIMARIA, corner_radius=10,
                              border_width=1, border_color=COR_PRIMARIA_HOVER)
        conteudo = ctk.CTkFrame(caixa, fg_color="transparent")
        conteudo.pack(padx=20, pady=8)
        ctk.CTkLabel(conteudo, text="H O R A S   H O J E", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=COR_RELOGIO_LEGENDA).pack()
        self.label_total_horas = ctk.CTkLabel(
            conteudo, text="0:00", font=ctk.CTkFont(family="Consolas", size=30, weight="bold"),
            text_color=COR_RELOGIO_DIGITO,
        )
        self.label_total_horas.pack()
        return caixa

    def _total_horas_hoje_s(self) -> float:
        """Soma o campo "Horas" (cobráveis, editável manualmente) dos cards de hoje - não
        o tempo bruto do cronômetro, que pode ter sido ajustado pra mais ou pra menos."""
        hoje = datetime.now().strftime("%d/%m/%Y")
        total = timedelta()
        for c in self.cards:
            if c.entry_data.get().strip() != hoje:
                continue
            horas = planilha.parse_horas_cobraveis(c.entry_horas_cobraveis.get())
            if horas:
                total += horas
        return total.total_seconds()

    def _atualizar_total_horas(self) -> None:
        self.label_total_horas.configure(text=_fmt_relogio_total(self._total_horas_hoje_s()))

    def _advogado_mudou(self) -> None:
        self.advogado_atual = self.cb_advogado_geral.get()
        self.salvar()

    def advogado_valido(self) -> bool:
        if not self.advogado_atual:
            messagebox.showwarning("Advogado obrigatório", "Selecione o advogado responsável antes de continuar.")
            return False
        return True

    def _limpar_tudo(self) -> None:
        if not messagebox.askyesno(
            "Limpar tudo",
            "Isso apaga os dados de todos os cronômetros abertos (mantendo a quantidade de cartões). Continuar?",
        ):
            return
        for card in self.cards:
            if not card.timer.fixado:
                card.resetar()
        self.salvar()

    def _excluir_tudo(self) -> None:
        if not messagebox.askyesno(
            "Excluir tudo",
            "Isso exclui todos os cronômetros da tela (mantendo apenas o advogado selecionado). "
            "Essa ação não pode ser desfeita. Continuar?",
            icon="warning",
        ):
            return
        restantes = []
        for card in self.cards:
            if card.timer.fixado:
                restantes.append(card)
            else:
                card.destroy()
        self.cards = restantes
        self._relayout_cards()
        self.salvar()

    def _conectar_advwin(self) -> None:
        """Abre a sessão do AdvWin (perfil próprio de automação; pode pedir login manual
        na primeira vez), pela mesma fila usada pelos lançamentos por card."""
        self.btn_conectar_advwin.configure(text="Aguardando login...", state="disabled")
        advwin.enfileirar(advwin.pagina_advwin, self._apos_conectar_advwin)

    def _apos_conectar_advwin(self, resultado, erro) -> None:
        self.after(0, lambda: self._apos_conectar_advwin_ui(erro))

    def _apos_conectar_advwin_ui(self, erro: Exception | None) -> None:
        self.btn_conectar_advwin.configure(text="Conectar AdvWin", state="normal")
        if erro is not None:
            messagebox.showerror("AdvWin", f"Não foi possível conectar ao AdvWin:\n{advwin.mensagem_amigavel(erro)}")
        else:
            messagebox.showinfo("AdvWin", "Conectado com sucesso.")

    def _lancar_retroativo(self) -> None:
        """Lê uma cópia preenchida da planilha de modelo e abre a prévia editável
        (retro_preview.JanelaRetroativa) antes de lançar qualquer coisa no AdvWin."""
        if not self.advogado_valido():
            return
        resultado = retro_preview.selecionar_e_ler(self)
        if resultado is None:
            return
        caminho, linhas = resultado
        retro_preview.JanelaRetroativa(self, caminho, linhas, self.advogado_atual, self.pastas_favoritas)

    def novo_card(self) -> None:
        self._adicionar_card(estado.Timer())
        self.salvar()

    def _adicionar_card(self, timer: estado.Timer) -> None:
        card = TimerCard(self.cards_frame, self, timer)
        self.cards.append(card)
        self._relayout_cards()

    def _calcular_colunas(self) -> int:
        largura = self.scroll.winfo_width() - 24  # 24px de folga pra barra de rolagem interna
        if largura <= 1:  # janela ainda não desenhada (winfo_width não confiável)
            return 3
        return max(1, largura // LARGURA_MIN_CARD)

    def _ao_redimensionar_cards(self, event) -> None:
        """Debounced: evita relayout a cada pixel arrastado ao redimensionar a janela."""
        if self._job_redimensionar is not None:
            self.after_cancel(self._job_redimensionar)
        self._job_redimensionar = self.after(150, self._relayout_cards)

    def _relayout_cards(self) -> None:
        """Reposiciona os cards numa grade cujo número de colunas se adapta à largura
        disponível (sem buracos após remoção)."""
        self._job_redimensionar = None
        colunas = self._calcular_colunas()
        maximo = max(colunas, self._colunas_configuradas)
        for c in range(maximo):
            self.cards_frame.grid_columnconfigure(c, weight=1 if c < colunas else 0, uniform="col")
        self._colunas_configuradas = maximo
        for i, card in enumerate(self.cards):
            card.grid(row=i // colunas, column=i % colunas, sticky="nsew", padx=6, pady=6)

    def _card_com_foco(self) -> "TimerCard | None":
        widget = self.focus_get()
        while widget is not None:
            if widget in self.cards:
                return widget
            widget = getattr(widget, "master", None)
        return self.cards[0] if self.cards else None

    def _atalho_play_pause(self) -> None:
        card = self._card_com_foco()
        if card is not None:
            card.alternar_iniciar_pausar()

    def _alternar_tema(self) -> None:
        novo_modo = "Light" if ctk.get_appearance_mode() == "Dark" else "Dark"
        ctk.set_appearance_mode(novo_modo)
        self.btn_tema.configure(image=icones.icone("sol" if novo_modo == "Dark" else "lua", cor=COR_ICONE_NEUTRO))

    def _inserir_todos(self) -> None:
        if not self.advogado_valido():
            return
        pendentes = [c for c in self.cards if not c.timer.inserido]
        if not pendentes:
            return
        self._lote_total = len(pendentes)
        self._lote_concluidos = 0
        self.btn_inserir_todos.configure(text=f"Lançando... 0/{self._lote_total}", state="disabled")
        for card in pendentes:
            card._inserir(self._apos_item_lote)

    def _apos_item_lote(self) -> None:
        self._lote_concluidos += 1
        if self._lote_concluidos < self._lote_total:
            self.btn_inserir_todos.configure(text=f"Lançando... {self._lote_concluidos}/{self._lote_total}")
        else:
            self.btn_inserir_todos.configure(text="Lançar todas no AdvWin", state="normal")

    def remover_card(self, card: TimerCard) -> None:
        self.cards.remove(card)
        card.destroy()
        self._relayout_cards()
        self.salvar()

    def salvar(self) -> None:
        for card in self.cards:
            card._coletar_campos()
        estado.salvar_estado([c.timer for c in self.cards], self.advogado_atual)
        self.label_salvo.configure(text=f"Salvo às {datetime.now().strftime('%H:%M')}")

    def _tick(self) -> None:
        for card in self.cards:
            card.atualizar_relogio()
        self._atualizar_total_horas()
        self.after(1000, self._tick)

    def _checar_inatividade(self) -> None:
        ativos = [c for c in self.cards if c.timer.status == "rodando"]
        if ativos and _segundos_sem_atividade() >= LIMITE_INATIVIDADE_S:
            for card in ativos:
                card._pausar()
            messagebox.showwarning(
                "Ainda está aí?",
                "Seus cronômetros foram pausados, lembre de ativá-los quando voltar.",
            )
        self.after(30_000, self._checar_inatividade)

    def _checar_atualizacao(self) -> None:
        threading.Thread(target=self._checar_atualizacao_bg, daemon=True).start()

    def _checar_atualizacao_bg(self) -> None:
        info = atualizador.verificar_nova_versao()
        if not info:
            return
        try:
            self._instalador_pendente = atualizador.baixar_instalador(info["url"])
        except OSError:
            pass

    def _ao_fechar(self) -> None:
        self.salvar()
        if self._instalador_pendente is not None:
            atualizador.instalar_silenciosamente(self._instalador_pendente)
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
