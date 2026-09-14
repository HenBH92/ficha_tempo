"""App de ficha de tempo: múltiplos cronômetros -> linhas na planilha diária do AdvWin."""
# O instalador pode executar este processo apenas para hooks: nada da UI antes disso.
if __name__ == "__main__":
    from inicializacao import iniciar_velopack, diagnosticar_se_solicitado, configurar_logs, garantir_instancia_unica
    iniciar_velopack()
    diagnosticar_se_solicitado()
    garantir_instancia_unica()
    configurar_logs()

import ctypes
import math
import queue
from datetime import datetime, timedelta
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

import advwin
import barra_tarefas
import estado
import favoritos
import icones
import modelos
import planilha
import relatos
import retro_preview
from caminhos import pasta_recursos, VERSAO
from atualizacao_ui import ControladorAtualizacao
from cores import (
    COR_BORDA_CARD,
    COR_CARD_INSERIDO,
    COR_CARD_PAUSADO,
    COR_CARD_RODANDO,
    COR_FUNDO_CARD,
    COR_HEADER_BORDA,
    COR_HEADER_FUNDO,
    COR_HOVER_NEUTRO,
    COR_ICONE_NEUTRO,
    COR_MARCA_LARANJA,
    COR_MARCA_LARANJA_CLARA,
    COR_NEUTRO,
    COR_NEUTRO_HOVER,
    COR_PERIGO,
    COR_PERIGO_HOVER,
    COR_PRIMARIA,
    COR_PRIMARIA_CLARA,
    COR_PRIMARIA_HOVER,
    COR_RELOGIO_DIGITO,
    COR_RELOGIO_LEGENDA,
    COR_SUCESSO,
    COR_SUCESSO_HOVER,
    COR_TEXTO_SUAVE,
)
from widgets import BuscaCombobox, DescricaoModeloEntry, Tooltip

PASTA_ASSETS = pasta_recursos() / "assets"

LIMITE_INATIVIDADE_S = 10 * 60
LARGURA_MIN_CARD = 300
MAX_COLUNAS = 4
INTERVALO_SESSAO_ADVWIN_MS = 5000
# Diz também por que os campos não respondem - card lançado trava tudo, e sem esse aviso
# parecia defeito. _apos_item_lote() reaproveita este texto no resumo do lote.
TEXTO_CARD_LANCADO = "✓ Lançado no AdvWin - campos bloqueados"

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


def _bloco(master, rotulo: str, dica: str = "") -> ctk.CTkFrame:
    """Frame com um rótulo pequeno em cima, para o campo ser empacotado dentro.

    `dica` prende o Tooltip no rótulo, não no campo - o popup do Tooltip nasce logo abaixo
    do widget, que é exatamente onde um CTkOptionMenu abre o dropdown (tk_popup); com os
    dois no mesmo lugar o menu fecha antes de dar pra escolher a opção."""
    frame = ctk.CTkFrame(master, fg_color="transparent")
    label = ctk.CTkLabel(frame, text=rotulo, font=ctk.CTkFont(size=10),
                         text_color=COR_TEXTO_SUAVE, anchor="w")
    label.pack(anchor="w")
    if dica:
        Tooltip(label, dica)
    return frame


def _legenda_cor(master, cor: str, texto: str, borda=COR_BORDA_CARD) -> ctk.CTkFrame:
    """Item de legenda: quadradinho colorido + texto, para explicar as cores dos cards.

    `borda` existe porque o card já lançado se distingue pela borda, não pelo preenchimento."""
    item = ctk.CTkFrame(master, fg_color="transparent")
    ctk.CTkFrame(item, fg_color=cor, border_width=1, border_color=borda,
                 width=11, height=11, corner_radius=3).pack(side="left")
    ctk.CTkLabel(item, text=texto, font=ctk.CTkFont(size=10), text_color=COR_TEXTO_SUAVE).pack(side="left", padx=(5, 0))
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
        linha1.pack(fill="x", padx=12, pady=(10, 3))

        # Seleção é transitória (não vai pro estado.json): serve só pras ações em lote da
        # barra do topo. pady alinha a caixinha com o campo, não com o rótulo do _bloco.
        self.var_selecionado = ctk.BooleanVar(value=False)
        self.chk_selecionar = ctk.CTkCheckBox(linha1, text="", width=20, variable=self.var_selecionado,
                                               command=app._atualizar_barra_selecao)
        self.chk_selecionar.pack(side="left", padx=(0, 8), pady=(14, 0))
        Tooltip(self.chk_selecionar, "Selecionar este card (para duplicar em lote)")

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
        linha2.pack(fill="x", padx=12, pady=3)

        bloco_pasta = _bloco(linha2, "Pasta")
        bloco_pasta.pack(fill="x")
        linha_pasta = ctk.CTkFrame(bloco_pasta, fg_color="transparent")
        linha_pasta.pack(fill="x")
        self.cb_pasta = BuscaCombobox(linha_pasta, app.pastas_favoritas, estrito=False, placeholder_text="Pasta",
                                       command=self._atualizar_estrela_pasta)
        self.cb_pasta.set(timer.pasta)
        self.cb_pasta.pack(side="left", fill="x", expand=True)
        self.btn_favoritar_pasta = ctk.CTkButton(linha_pasta, text="", image=icones.icone("estrela", cor=COR_MARCA_LARANJA),
                                                   width=30, fg_color="transparent", border_width=1,
                                                   border_color=COR_MARCA_LARANJA, hover_color=COR_MARCA_LARANJA_CLARA,
                                                   command=self._alternar_favorito_pasta)
        self.btn_favoritar_pasta.pack(side="left", padx=(4, 0))

        # Linha própria: com o card em LARGURA_MIN_CARD não sobra largura pra esse seletor
        # em nenhuma das outras linhas (medido: linha1 já pede 352px pra 276 úteis). Fica
        # colado na Pasta de propósito - os dois juntos é que identificam o processo.
        linha_modulo = ctk.CTkFrame(self, fg_color="transparent")
        linha_modulo.pack(fill="x", padx=12, pady=3)
        bloco_modulo = _bloco(linha_modulo, "Módulo",
                              "Listagem do AdvWin onde esta pasta será procurada.\n"
                              "O código da pasta só é único dentro de cada módulo.")
        bloco_modulo.pack(side="left")
        # Segmentado, não CTkOptionMenu: no Windows o dropdown do CTkOptionMenu é um
        # tkinter.Menu aberto com post(), que bloqueia o loop do Tk e não pega o clique
        # na opção (medido - o menu abre e o app congela até ser dispensado).
        self.seg_modulo = ctk.CTkSegmentedButton(
            bloco_modulo, values=list(advwin.URLS_AREA), font=ctk.CTkFont(size=12), height=28,
            selected_color=COR_PRIMARIA, selected_hover_color=COR_PRIMARIA_HOVER,
            unselected_hover_color=COR_HOVER_NEUTRO,
        )
        self.seg_modulo.set(timer.area if timer.area in advwin.URLS_AREA else app.area_atual)
        self.seg_modulo.pack()

        linha3 = ctk.CTkFrame(self, fg_color="transparent")
        linha3.pack(fill="x", padx=12, pady=3)

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
        linha4.pack(fill="x", padx=12, pady=3)

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
        linha5.pack(fill="x", padx=12, pady=(3, 10))

        self.btn_iniciar = ctk.CTkButton(linha5, text="", image=icones.icone("play", cor="white"), width=32,
                                          fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HOVER, command=self._iniciar)
        self.btn_iniciar.pack(side="left", padx=2)
        Tooltip(self.btn_iniciar, "Iniciar (Ctrl+Espaço)")
        self.btn_pausar = ctk.CTkButton(linha5, text="", image=icones.icone("pause", cor=COR_PRIMARIA), width=32,
                                         fg_color="transparent", border_width=1, border_color=COR_PRIMARIA,
                                         hover_color=COR_PRIMARIA_CLARA, command=self._pausar)
        self.btn_pausar.pack(side="left", padx=2)
        Tooltip(self.btn_pausar, "Pausar (Ctrl+Espaço)")
        self.btn_parar = ctk.CTkButton(linha5, text="", image=icones.icone("stop", cor="white"), width=32,
                                        fg_color=COR_NEUTRO, hover_color=COR_NEUTRO_HOVER, command=self._parar)
        self.btn_parar.pack(side="left", padx=2)
        Tooltip(self.btn_parar, "Parar")

        ctk.CTkFrame(linha5, fg_color=COR_BORDA_CARD, width=1, height=24).pack(side="left", padx=6)

        self.btn_inserir = ctk.CTkButton(linha5, text="", image=icones.icone("inserir", cor="white"), width=32,
                                          fg_color=COR_SUCESSO, hover_color=COR_SUCESSO_HOVER, command=self._inserir)
        self.btn_inserir.pack(side="left", padx=2)
        Tooltip(self.btn_inserir, "Inserir no AdvWin")
        self.btn_remover = ctk.CTkButton(linha5, text="", image=icones.icone("remover", cor=COR_PERIGO), width=32,
                                          fg_color="transparent", border_width=1, border_color=COR_PERIGO,
                                          hover_color=COR_PERIGO_HOVER, command=self._remover)
        self.btn_remover.pack(side="left", padx=2)
        Tooltip(self.btn_remover, "Remover")

        self.label_status_advwin = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                                  font=ctk.CTkFont(size=11), text_color=COR_TEXTO_SUAVE,
                                                  wraplength=260)
        self.label_status_advwin.pack(fill="x", padx=12, pady=(0, 8))

        if timer.inserido:
            self.btn_inserir.configure(text="✓", image=None, state="disabled", fg_color=COR_SUCESSO_HOVER)
            self._definir_campos_travados(True)
            self._marcar_status_advwin(TEXTO_CARD_LANCADO, COR_SUCESSO)
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
        # Borda verde é o que distingue o card já lançado: o fundo dele tem que ficar
        # discreto pra não brigar com o verde de "rodando" e o bege de "pausado", e sozinho
        # não chamava atenção nenhuma - foi por isso que os campos travados pareciam bug.
        inserido = self.timer.inserido
        self.configure(fg_color=cor,
                       border_width=2 if inserido else 1,
                       border_color=COR_SUCESSO if inserido else COR_BORDA_CARD)

    def _marcar_status_advwin(self, texto: str, cor: str) -> None:
        self.label_status_advwin.configure(text=texto, text_color=cor)

    def _definir_campos_travados(self, travado: bool) -> None:
        """Bloqueia campos e cronômetro do card enquanto o lançamento no AdvWin está em voo
        (evita editar pasta/descrição sem saber se o valor enviado já mudou) - também usada
        para manter travado um card que já foi inserido.

        Os botões só dão o retorno visual; quem de fato barra a ação é o guarda em
        _iniciar/_pausar/_parar, porque o atalho Ctrl+Espaço não passa pelos botões."""
        estado_campo = "disabled" if travado else "normal"
        self.btn_iniciar.configure(state=estado_campo)
        self.btn_pausar.configure(state=estado_campo)
        self.btn_parar.configure(state=estado_campo)
        self.entry_data.configure(state=estado_campo)
        self.seg_modulo.configure(state=estado_campo)
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
            botao.configure(fg_color=COR_MARCA_LARANJA, border_width=0, image=icones.icone("estrela", cor="white"))
        else:
            botao.configure(fg_color="transparent", border_width=1, border_color=COR_MARCA_LARANJA,
                             image=icones.icone("estrela", cor=COR_MARCA_LARANJA))

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
        t.area = self.seg_modulo.get()
        t.descricao = self.entry_descricao.get()
        t.horas_cobraveis_texto = self.entry_horas_cobraveis.get().strip()

    def _atualizar_horas_cobraveis_auto(self) -> None:
        texto = _fmt_horas_cobraveis(_minutos_cobraveis(self.timer.elapso_s()))
        self.entry_horas_cobraveis.delete(0, "end")
        self.entry_horas_cobraveis.insert(0, texto)

    def _cronometro_travado(self) -> bool:
        """Card já lançado não mexe mais no cronômetro: o tempo dele virou linha no AdvWin e
        no log local, e mudar depois só criaria divergência entre os dois."""
        return self.timer.inserido

    def _iniciar(self) -> None:
        if self.app._encerrando or self._cronometro_travado():
            return
        self.timer.iniciar()
        self._atualizar_cor_card()
        self.app.salvar()

    def _pausar(self) -> None:
        if self._cronometro_travado():
            return
        self.timer.pausar()
        self._atualizar_horas_cobraveis_auto()
        self._atualizar_cor_card()
        self.app.salvar()

    def _parar(self) -> None:
        if self._cronometro_travado():
            return
        self.timer.parar()
        self.label_tempo.configure(text=self.timer.elapso_fmt())
        self._atualizar_horas_cobraveis_auto()
        self._atualizar_cor_card()
        self.app.salvar()

    def _inserir(self, ao_concluir=None) -> None:
        """Lança este card no AdvWin (numa fila em segundo plano - a sessão do navegador
        é compartilhada entre cards) e, se der certo, registra a linha no log local.
        `ao_concluir`, se passado, roda ao final com um bool de sucesso - usado por
        "Lançar todas" para acompanhar o progresso do lote. Nesse modo (em_lote=True),
        erros não abrem popup - ficam só no status do próprio card, pra não empilhar um
        messagebox bloqueante por card que falhar."""
        if self.app._encerrando:
            return
        em_lote = ao_concluir is not None
        self._marcar_status_advwin("", COR_TEXTO_SUAVE)
        if not self.app.advogado_valido():
            if ao_concluir:
                ao_concluir(False)
            return

        self._coletar_campos()
        t = self.timer
        try:
            datetime.strptime(t.data, "%d/%m/%Y")
        except ValueError:
            if em_lote:
                self._marcar_status_advwin("✗ Data inválida (use dd/mm/aaaa).", COR_PERIGO)
            else:
                messagebox.showwarning("Data inválida", 'A data deve estar no formato dd/mm/aaaa (ex.: "14/08/2026").')
            if ao_concluir:
                ao_concluir(False)
            return
        if not t.pasta:
            if em_lote:
                self._marcar_status_advwin("✗ Pasta obrigatória.", COR_PERIGO)
            else:
                messagebox.showwarning("Pasta obrigatória", "Preencha a Pasta antes de lançar no AdvWin.")
            if ao_concluir:
                ao_concluir(False)
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
        area = t.area  # _coletar_campos() acima já leu o seletor de módulo deste card
        advwin.enfileirar(
            lambda: advwin.lancar_horas(advwin.pagina_advwin(), pasta, data, descricao, horas_texto, area),
            lambda resultado, erro: self._apos_inserir_advwin_ui(erro, ao_concluir),
            despachar=self.app.agendar_ui,
        )

    def _apos_inserir_advwin(self, erro, ao_concluir) -> None:
        self.after(0, lambda: self._apos_inserir_advwin_ui(erro, ao_concluir))

    def _apos_inserir_advwin_ui(self, erro: Exception | None, ao_concluir=None) -> None:
        if erro is not None:
            self.btn_inserir.configure(text="", image=icones.icone("inserir", cor="white"), state="normal")
            self._definir_campos_travados(False)
            mensagem = advwin.mensagem_amigavel(erro)
            if ao_concluir:
                self._marcar_status_advwin(f"✗ {mensagem}", COR_PERIGO)
            else:
                messagebox.showerror("AdvWin", f"Não foi possível lançar no AdvWin:\n{mensagem}")
            self.app._atualizar_botao_advwin()
            if ao_concluir:
                ao_concluir(False)
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
        self._marcar_status_advwin(TEXTO_CARD_LANCADO, COR_SUCESSO)
        self._atualizar_cor_card()
        self.app.salvar()
        self.app._atualizar_botao_advwin()
        if ao_concluir:
            ao_concluir(True)

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
        self.var_selecionado.set(False)
        self._definir_campos_travados(False)
        self._marcar_status_advwin("", COR_TEXTO_SUAVE)
        self.entry_data.delete(0, "end")
        self.entry_data.insert(0, datetime.now().strftime("%d/%m/%Y"))
        self.seg_modulo.set(self.app.area_atual)
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
        self._encerrando = False
        self._destruida = False
        self._eventos_ui = queue.Queue()
        self.title("VLF Advogados - Ficha Tempo")
        self.geometry("1040x640")
        self.minsize(860, 560)
        self.configure(fg_color=("#ffffff", "#18181d"))

        icone = PASTA_ASSETS / "vlf_icon.ico"
        if icone.exists():
            self.iconbitmap(icone)

        self.listas = planilha.carregar_listas()
        self.modelos_descricao = modelos.carregar_modelos()
        self.pastas_favoritas = favoritos.carregar_pastas()

        timers, advogado_atual, area_atual = estado.carregar_estado()
        self.advogado_atual = advogado_atual
        # estado.json é editável na mão: um módulo desconhecido aqui viraria KeyError em
        # advwin.lancar_horas(), então cai no padrão em vez de propagar.
        self.area_atual = area_atual if area_atual in advwin.URLS_AREA else next(iter(advwin.URLS_AREA))

        hoje = datetime.now().strftime("%d/%m/%Y")
        retomando = estado.retomada_pendente()
        for t in timers:
            if t.fixado and not retomando:
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
        linha_titulo.pack(fill="x", padx=24, pady=(12, 6))

        titulo_frame = ctk.CTkFrame(linha_titulo, fg_color="transparent")
        titulo_frame.pack(side="left")

        logo_path = PASTA_ASSETS / "logo_escritorio.png"
        if logo_path.exists():
            imagem = Image.open(logo_path)
            largura = 170
            altura = round(largura * imagem.height / imagem.width)
            self.logo_ctk = ctk.CTkImage(light_image=imagem, dark_image=imagem, size=(largura, altura))
            # Placa branca fixa: a arte do logo é navy sobre fundo transparente e não muda
            # com o tema, então o fundo dela também precisa ficar fixo (senão some no dark mode).
            placa_logo = ctk.CTkFrame(titulo_frame, fg_color="white", corner_radius=8)
            placa_logo.pack(anchor="w")
            ctk.CTkLabel(placa_logo, image=self.logo_ctk, text="").pack(padx=10, pady=6)
        else:
            ctk.CTkLabel(titulo_frame, text="VLF Advogados", font=ctk.CTkFont(size=20, weight="bold"),
                         text_color=COR_PRIMARIA).pack(anchor="w")

        advogado_frame = ctk.CTkFrame(linha_titulo, fg_color="transparent")
        advogado_frame.pack(side="left", fill="x", expand=True, padx=(30, 0))

        linha_advogado = ctk.CTkFrame(advogado_frame, fg_color="transparent")
        linha_advogado.pack(side="top", fill="x")
        ctk.CTkLabel(linha_advogado, text="Advogado responsável: *", text_color=COR_TEXTO_SUAVE).pack(side="left", padx=(0, 10))
        self.cb_advogado_geral = BuscaCombobox(
            linha_advogado, self.listas["Advogado"], placeholder_text="Seu nome", command=self._advogado_mudou
        )
        self.cb_advogado_geral.set(advogado_atual)
        self.cb_advogado_geral.pack(side="left", fill="x", expand=True)

        linha_area = ctk.CTkFrame(advogado_frame, fg_color="transparent")
        linha_area.pack(side="top", fill="x", pady=(6, 0))
        # Tooltip vai no rótulo: CTkSegmentedButton não implementa bind().
        rotulo_area = ctk.CTkLabel(linha_area, text="Módulo padrão:", text_color=COR_TEXTO_SUAVE)
        rotulo_area.pack(side="left", padx=(0, 10))
        Tooltip(rotulo_area, "Módulo com que os cards novos nascem (e o lançamento retroativo usa).\n"
                             "Cada card já existente mantém o módulo escolhido nele.")
        self.seg_area = ctk.CTkSegmentedButton(
            linha_area, values=list(advwin.URLS_AREA), command=self._area_mudou,
            selected_color=COR_PRIMARIA, selected_hover_color=COR_PRIMARIA_HOVER,
            unselected_hover_color=COR_HOVER_NEUTRO,
        )
        self.seg_area.set(self.area_atual)
        self.seg_area.pack(side="left")

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
        linha_topo.pack(fill="x", padx=24, pady=10)

        # Relógio primeiro (side="right"): reserva o espaço dele antes dos botões, senão
        # fica espremido pra fora da janela quando a barra fluida ocupa tudo que sobrar.
        caixa_relogio = self._construir_relogio_total(linha_topo)
        caixa_relogio.pack(side="right", padx=(12, 0))

        linha_acoes = _BarraFluida(linha_topo)
        linha_acoes.pack(side="left", fill="both", expand=True)

        FONTE_BOTAO = ctk.CTkFont(size=13, weight="bold")
        FONTE_BOTAO_SECUNDARIO = ctk.CTkFont(size=12)

        linha_acoes.adicionar(ctk.CTkButton(
            linha_acoes, text="+ Novo cronômetro", width=170, height=40, font=FONTE_BOTAO,
            fg_color=COR_PRIMARIA, text_color="white",
            hover_color=COR_PRIMARIA_HOVER, command=self.novo_card))
        self.var_selecionar_todos = ctk.BooleanVar(value=False)
        linha_acoes.adicionar(ctk.CTkCheckBox(
            linha_acoes, text="Selecionar todos", width=145, height=32, font=FONTE_BOTAO_SECUNDARIO,
            variable=self.var_selecionar_todos, command=self._alternar_selecionar_todos))
        # Largura fixa de propósito: _BarraFluida mede winfo_reqwidth() dos itens, e um texto
        # que cresce com o contador refluiria a barra inteira a cada clique num checkbox.
        self.btn_duplicar = ctk.CTkButton(
            linha_acoes, text="Duplicar selecionados", width=200, height=32, font=FONTE_BOTAO_SECUNDARIO,
            fg_color="transparent", border_width=1,
            border_color=COR_PRIMARIA, text_color=COR_PRIMARIA, hover_color="white",
            state="disabled", command=self._duplicar_selecionados,
        )
        linha_acoes.adicionar(self.btn_duplicar)
        Tooltip(self.btn_duplicar,
                "Cria uma cópia de cada card marcado, ao lado do original, com a mesma Pasta, "
                "Descrição e Data - cronômetro zerado e ainda não lançado no AdvWin.")

        linha_acoes.adicionar(ctk.CTkButton(
            linha_acoes, text="Limpar tudo", width=130, height=32, font=FONTE_BOTAO_SECUNDARIO,
            fg_color="transparent", border_width=1,
            border_color=COR_NEUTRO, text_color=COR_NEUTRO, hover_color=COR_HEADER_BORDA,
            command=self._limpar_tudo))
        self.btn_conectar_advwin = ctk.CTkButton(
            linha_acoes, text="Conectar AdvWin", width=150, height=32, font=FONTE_BOTAO_SECUNDARIO,
            fg_color="transparent", border_width=1,
            border_color=COR_PRIMARIA, text_color=COR_PRIMARIA, hover_color="white",
            command=self._conectar_advwin,
        )
        linha_acoes.adicionar(self.btn_conectar_advwin)
        self.btn_lancar_retroativo = ctk.CTkButton(
            linha_acoes, text="Lançar retroativo (planilha)", width=195, height=32, font=FONTE_BOTAO_SECUNDARIO,
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
        linha_acoes.adicionar(ctk.CTkFrame(linha_acoes, fg_color=COR_HEADER_BORDA, width=1, height=24))
        linha_acoes.adicionar(ctk.CTkButton(
            linha_acoes, text="Excluir tudo", width=130, height=32, font=FONTE_BOTAO_SECUNDARIO,
            fg_color="transparent", border_width=1,
            border_color=COR_PERIGO, text_color=COR_PERIGO, hover_color=COR_PERIGO_HOVER,
            command=self._excluir_tudo))

        linha_legenda = ctk.CTkFrame(barra_acoes, fg_color="transparent")
        linha_legenda.pack(pady=(4, 8))
        _legenda_cor(linha_legenda, COR_CARD_RODANDO, "Rodando").pack(side="left", padx=8)
        _legenda_cor(linha_legenda, COR_CARD_PAUSADO, "Pausado").pack(side="left", padx=8)
        _legenda_cor(linha_legenda, COR_CARD_INSERIDO, "Lançado (bloqueado)",
                     borda=COR_SUCESSO).pack(side="left", padx=8)

        ctk.CTkFrame(self, fg_color=COR_HEADER_BORDA, height=1).pack(fill="x")

        # Rodapé e a barra "Lançar todas" precisam ser empacotados (side="bottom") antes do
        # scroll (fill="both", expand=True) - senão o scroll toma a área toda e não sobra
        # espaço pra eles. Ficam fora do scroll de propósito: dentro dele, o scrollregion do
        # CTkScrollableFrame não recalculava certo com cards_frame usando grid, e o botão
        # ficava inacessível mesmo rolando até o fim.
        self.rodape = ctk.CTkFrame(self, fg_color=COR_HEADER_FUNDO, corner_radius=0, height=26)
        self.rodape.pack(fill="x", side="bottom")
        self.rodape.pack_propagate(False)
        # Só aparece com o formulário de relatos configurado - sem ele o botão só levaria a
        # "não deu para enviar". Preenchendo URL_FORMULARIO em relatos.py, volta sozinho.
        # Empacotado antes do label_salvo: em side="right" quem vem primeiro fica mais à direita.
        if relatos.URL_FORMULARIO:
            ctk.CTkButton(self.rodape, text="Relatar problema ou sugestão", height=22,
                           fg_color="transparent", text_color=COR_TEXTO_SUAVE,
                           hover_color=COR_HOVER_NEUTRO, command=self.abrir_relato).pack(side="right", padx=12)
        self.label_salvo = ctk.CTkLabel(self.rodape, text="", font=ctk.CTkFont(size=11), text_color=COR_TEXTO_SUAVE)
        self.label_salvo.pack(side="right", padx=16)
        ctk.CTkButton(self.rodape, text=f"v{VERSAO} · Verificar atualizações", height=22,
                       fg_color="transparent", text_color=COR_TEXTO_SUAVE,
                       command=lambda: self.atualizacoes.verificar(manual=True)).pack(side="left", padx=12)

        self.btn_inserir_todos = ctk.CTkButton(
            self, text="Lançar todas no AdvWin", height=40, font=FONTE_BOTAO,
            fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HOVER, command=self._inserir_todos,
        )
        self.btn_inserir_todos.pack(fill="x", side="bottom", padx=16, pady=(0, 12))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=("white", "#18181d"))
        self.scroll.pack(fill="both", expand=True, padx=16, pady=16)

        self.cards_frame = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.cards_frame.pack(fill="x")
        self._colunas_configuradas = 0
        self._job_redimensionar: str | None = None
        self._ultima_largura_scroll = 0
        # Mede/observa self.scroll (largura fixada de fora, pelo layout da janela) - não
        # cards_frame, cuja própria largura pedida depende de quantas colunas o grid interno
        # tem (referência circular: encolhia a janela, mas a largura medida não acompanhava).
        # add="+" é obrigatório aqui: o CustomTkinter já tem um bind interno de <Configure>
        # nesse mesmo widget pra recalcular o scrollregion do canvas - sem add="+", .bind()
        # substitui esse handler e a área para de rolar de verdade.
        self.scroll.bind("<Configure>", self._ao_redimensionar_cards, add="+")

        self.cards: list[TimerCard] = []
        for timer in timers:
            self._adicionar_card(timer, relayout=False)
        if not self.cards:
            self._adicionar_card(estado.Timer(), relayout=False)
        self._relayout_cards()
        self._atualizar_total_horas()

        # Ctrl+Espaço/Ctrl+N em vez de só Espaço: os cards têm campos de texto (descrição
        # etc.) onde a barra de espaço precisa continuar digitando um espaço normal.
        self.bind_all("<Control-space>", lambda e: self._atalho_play_pause())
        self.bind_all("<Control-n>", lambda e: self.novo_card())

        self.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        self.after(1000, self._tick)
        self.after(30_000, self._checar_inatividade)
        self.after(50, self._processar_eventos_ui)
        self.after(INTERVALO_SESSAO_ADVWIN_MS, self._monitorar_sessao_advwin)
        self.atualizacoes = ControladorAtualizacao(self, advwin)
        if retomando:
            self.salvar()  # Consome a retomada somente após reconstruir a interface.

    def agendar_ui(self, callback) -> None:
        if not self._destruida:
            self._eventos_ui.put(callback)

    def _processar_eventos_ui(self) -> None:
        for _ in range(100):
            try:
                callback = self._eventos_ui.get_nowait()
            except queue.Empty:
                break
            try:
                callback()
            except Exception as erro:
                self.report_callback_exception(type(erro), erro, erro.__traceback__)
            if self._destruida:
                return
        self.after(50, self._processar_eventos_ui)

    def tem_previa_aberta(self) -> bool:
        return any(isinstance(w, retro_preview.JanelaRetroativa) and w.winfo_exists()
                   for w in self.winfo_children())

    def destroy(self):
        self._destruida = True
        # Destruir os Toplevels explicitamente antes do root evita um TclError do
        # customtkinter (CTkTextbox) quando a destruição em cascata do Tk os alcança primeiro.
        for filho in list(self.winfo_children()):
            if isinstance(filho, ctk.CTkToplevel) and filho.winfo_exists():
                filho.destroy()
        super().destroy()

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

    def _area_mudou(self, valor: str) -> None:
        self.area_atual = valor
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
        self._atualizar_barra_selecao()
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
        self._atualizar_barra_selecao()
        self._relayout_cards()
        self.salvar()

    def _monitorar_sessao_advwin(self) -> None:
        """Detecta a janela do Chrome fechada na mão e devolve o botão para "Conectar
        AdvWin". A checagem vai pela fila porque a sessão do Playwright é presa à thread
        dela - e só quando a fila está ociosa, para não entrar na frente de um lote nem
        competir com o encerramento seguro."""
        self.after(INTERVALO_SESSAO_ADVWIN_MS, self._monitorar_sessao_advwin)
        if self._encerrando or not advwin.esta_conectado() or advwin.esta_ocupado():
            return
        advwin.enfileirar(advwin.verificar_sessao,
                          lambda resultado, erro: self._atualizar_botao_advwin(),
                          self.agendar_ui)

    def _atualizar_botao_advwin(self) -> None:
        """Reflete no botão o último estado conhecido da sessão do AdvWin - atualizado a
        cada tentativa real de uso (conectar, inserir card, lote retroativo), sem polling."""
        if advwin.esta_conectado():
            self.btn_conectar_advwin.configure(
                text="Conectado", state="normal",
                fg_color=COR_SUCESSO, border_color=COR_SUCESSO,
                text_color="white", hover_color=COR_SUCESSO_HOVER,
            )
        else:
            self.btn_conectar_advwin.configure(
                text="Conectar AdvWin", state="normal",
                fg_color="transparent", border_color=COR_PRIMARIA,
                text_color=COR_PRIMARIA, hover_color="white",
            )

    def _conectar_advwin(self) -> None:
        """Abre a sessão do AdvWin (perfil próprio de automação; pode pedir login manual
        na primeira vez), pela mesma fila usada pelos lançamentos por card."""
        if self._encerrando:
            return
        self.btn_conectar_advwin.configure(text="Aguardando login...", state="disabled")
        advwin.enfileirar(advwin.pagina_advwin,
                         lambda resultado, erro: self._apos_conectar_advwin_ui(erro), self.agendar_ui)

    def _apos_conectar_advwin(self, resultado, erro) -> None:
        self.after(0, lambda: self._apos_conectar_advwin_ui(erro))

    def _apos_conectar_advwin_ui(self, erro: Exception | None) -> None:
        self._atualizar_botao_advwin()
        if erro is not None:
            messagebox.showerror("AdvWin", f"Não foi possível conectar ao AdvWin:\n{advwin.mensagem_amigavel(erro)}")
        else:
            messagebox.showinfo("AdvWin", "Conectado com sucesso.")

    def _lancar_retroativo(self) -> None:
        """Lê uma ou mais cópias preenchidas da planilha de modelo e abre a prévia editável
        (retro_preview.JanelaRetroativa) antes de lançar qualquer coisa no AdvWin."""
        if self._encerrando or not self.advogado_valido():
            return
        lotes = retro_preview.selecionar_e_ler_varias(self)
        if not lotes:
            return
        retro_preview.JanelaRetroativa(self, lotes, self.advogado_atual, self.pastas_favoritas, self.area_atual)

    def abrir_relato(self) -> None:
        """Relato de problema/sugestão, entregue pelo próprio app (ver relatos.py)."""
        if self._encerrando:
            return
        janela = next((w for w in self.winfo_children()
                       if isinstance(w, relatos.JanelaRelato) and w.winfo_exists()), None)
        if janela is not None:  # já aberta: traz pra frente em vez de abrir outra
            janela.lift()
            janela.focus_force()
            return
        relatos.JanelaRelato(self, {
            "advogado": self.advogado_atual or "(não escolhido)",
            "modulo_padrao": self.area_atual,
            "cards_abertos": len(self.cards),
            "advwin_conectado": advwin.esta_conectado(),
        })

    def novo_card(self) -> None:
        if self._encerrando:
            return
        self._adicionar_card(estado.Timer())
        self.salvar()

    def _adicionar_card(self, timer: estado.Timer, posicao: int | None = None, relayout: bool = True) -> None:
        """`posicao` insere o card no meio da lista (usado pela duplicação, pro clone nascer
        ao lado do original); `relayout=False` evita o custo O(n²) de regridar a grade
        inteira a cada card quando vários são criados de uma vez."""
        card = TimerCard(self.cards_frame, self, timer)
        if posicao is None:
            self.cards.append(card)
        else:
            self.cards.insert(posicao, card)
        if relayout:
            self._relayout_cards()

    def _atualizar_barra_selecao(self) -> None:
        selecionados = sum(1 for c in self.cards if c.var_selecionado.get())
        self.btn_duplicar.configure(
            text=f"Duplicar selecionados ({selecionados})" if selecionados else "Duplicar selecionados",
            state="normal" if selecionados else "disabled",
        )
        if not selecionados:
            self.var_selecionar_todos.set(False)

    def _alternar_selecionar_todos(self) -> None:
        valor = self.var_selecionar_todos.get()
        for card in self.cards:
            card.var_selecionado.set(valor)
        self._atualizar_barra_selecao()

    def _duplicar_selecionados(self) -> None:
        """Clona cada card marcado logo ao lado do original, copiando só Pasta, Módulo,
        Descrição e Data - o clone nasce com cronômetro zerado, destravado e não lançado
        (defaults do estado.Timer)."""
        if self._encerrando:
            return
        selecionados = [c for c in self.cards if c.var_selecionado.get()]
        if not selecionados:
            return
        for card in selecionados:
            card.var_selecionado.set(False)
            # Ler dos widgets, não de card.timer: _coletar_campos() só roda dentro de
            # App.salvar(), então o que foi digitado desde o último salvamento ainda não
            # chegou no Timer.
            clone = estado.Timer(
                data=card.entry_data.get().strip(),
                advogado=self.advogado_atual,
                pasta=card.cb_pasta.get(),
                area=card.seg_modulo.get(),
                descricao=card.entry_descricao.get(),
            )
            self._adicionar_card(clone, posicao=self.cards.index(card) + 1, relayout=False)
        self._atualizar_barra_selecao()
        self._relayout_cards()
        self.salvar()

    def _largura_util(self) -> int:
        """Largura disponível pra grade de cards, ou 0 se a janela ainda não foi desenhada.
        O frame interno do CTkScrollableFrame já vem dimensionado descontando a barra de
        rolagem, então só sobra a folga dos padx=6 de cada card."""
        largura = self.scroll.winfo_width() - 8
        return largura if largura > 1 else 0

    def _calcular_colunas(self) -> int:
        largura = self._largura_util()
        if not largura:  # janela ainda não desenhada (winfo_width não confiável)
            return 3
        return min(MAX_COLUNAS, max(1, largura // LARGURA_MIN_CARD))

    def _ao_redimensionar_cards(self, event) -> None:
        """Debounced: evita relayout a cada pixel arrastado ao redimensionar a janela.
        O <Configure> daqui também dispara por altura (ao adicionar/remover card, ao rolar),
        e nesses casos não há coluna nenhuma pra recalcular."""
        if event.width == self._ultima_largura_scroll:
            return
        self._ultima_largura_scroll = event.width
        if self._job_redimensionar is not None:
            self.after_cancel(self._job_redimensionar)
        self._job_redimensionar = self.after(150, self._relayout_cards)

    def _relayout_cards(self) -> None:
        """Reposiciona os cards numa grade cujo número de colunas se adapta à largura
        disponível (sem buracos após remoção).

        As colunas têm largura FIXA (minsize + weight=0) em vez de dividirem a largura da
        janela. Com weight=1 os cards esticavam a cada pixel arrastado, e toda mudança de
        largura faz o CustomTkinter redesenhar ~14 canvases por card (<Configure> ->
        _draw) - era isso que travava a janela no resize. Agora a largura do card só muda
        aqui, depois do debounce; a variação contínua do arrasto é absorvida pela
        coluna-sobra no fim da grade."""
        self._job_redimensionar = None
        colunas = self._calcular_colunas()
        largura_col = max(LARGURA_MIN_CARD, (self._largura_util() or colunas * LARGURA_MIN_CARD) // colunas)
        for c in range(max(colunas + 1, self._colunas_configuradas)):
            if c < colunas:
                self.cards_frame.grid_columnconfigure(c, weight=0, minsize=largura_col)
            elif c == colunas:
                self.cards_frame.grid_columnconfigure(c, weight=1, minsize=0)
            else:
                self.cards_frame.grid_columnconfigure(c, weight=0, minsize=0)
        self._colunas_configuradas = colunas + 1
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
        if self._encerrando or not self.advogado_valido():
            return
        pendentes = [c for c in self.cards if not c.timer.inserido]
        if not pendentes:
            return
        self._lote_pendentes = pendentes
        self._lote_total = len(pendentes)
        self._lote_concluidos = 0
        self._lote_erros = 0
        self.btn_inserir_todos.configure(text=f"Lançando... 0/{self._lote_total}", state="disabled")
        for card in pendentes:
            card._inserir(self._apos_item_lote)

    def _apos_item_lote(self, sucesso: bool) -> None:
        self._lote_concluidos += 1
        if not sucesso:
            self._lote_erros += 1
        if self._lote_concluidos < self._lote_total:
            texto = f"Lançando... {self._lote_concluidos}/{self._lote_total}"
            if self._lote_erros:
                texto += f" ({self._lote_erros} com erro)"
            self.btn_inserir_todos.configure(text=texto)
        else:
            self.btn_inserir_todos.configure(text="Lançar todas no AdvWin", state="normal")
            if self._lote_erros:
                log = "\n".join(
                    f"{c.cb_pasta.get().strip() or '(sem pasta)'}: {c.label_status_advwin.cget('text') or '✓ lançado'}"
                    for c in self._lote_pendentes
                )
                messagebox.showinfo(
                    "Lançamento no AdvWin concluído",
                    f"{self._lote_total - self._lote_erros} lançada(s) com sucesso, "
                    f"{self._lote_erros} com erro.\n\n{log}",
                )

    def remover_card(self, card: TimerCard) -> None:
        self.cards.remove(card)
        card.destroy()
        self._atualizar_barra_selecao()
        self._relayout_cards()
        self.salvar()

    def salvar(self, retomada_atualizacao=False) -> None:
        for card in self.cards:
            card._coletar_campos()
        estado.salvar_estado([c.timer for c in self.cards], self.advogado_atual, self.area_atual,
                             retomada_atualizacao=retomada_atualizacao)
        self.label_salvo.configure(text=f"Salvo às {datetime.now().strftime('%H:%M')}")

    def _tick(self) -> None:
        for card in self.cards:
            card.atualizar_relogio()
        self._atualizar_total_horas()
        barra_tarefas.definir_contador(self, sum(c.timer.status == "rodando" for c in self.cards))
        self.after(1000, self._tick)

    def _checar_inatividade(self) -> None:
        if self._encerrando:
            self.after(30_000, self._checar_inatividade)
            return
        ativos = [c for c in self.cards if c.timer.status == "rodando"]
        if ativos and _segundos_sem_atividade() >= LIMITE_INATIVIDADE_S:
            for card in ativos:
                card._pausar()
            messagebox.showwarning(
                "Ainda está aí?",
                "Seus cronômetros foram pausados, lembre de ativá-los quando voltar.",
            )
        self.after(30_000, self._checar_inatividade)

    def _ao_fechar(self) -> None:
        if self._encerrando:
            return
        if advwin.esta_ocupado():
            messagebox.showwarning("AdvWin", "Aguarde a conclusão das operações do AdvWin antes de fechar.")
            return
        if self.tem_previa_aberta():
            messagebox.showwarning("Lançamento retroativo", "Feche a prévia antes de encerrar o programa.")
            return
        if not advwin.bloquear_para_atualizacao():
            return
        try:
            self.salvar()
        except Exception as erro:
            advwin.cancelar_encerramento()
            messagebox.showerror("Salvar", f"Não foi possível salvar. O programa continuará aberto.\n{erro}")
            return
        self._encerrando = True
        self.attributes("-disabled", True)
        def encerrado(resultado, erro):
            if erro is not None:
                self._encerrando = False
                self.attributes("-disabled", False)
                advwin.cancelar_encerramento()
                messagebox.showerror("AdvWin", f"Não foi possível encerrar a sessão:\n{erro}")
                return
            self.atualizacoes.parar()
            self.destroy()
        advwin.encerrar_sessao(encerrado, self.agendar_ui)


if __name__ == "__main__":
    # sem isso, rodando via "python main.py" (fora do .exe empacotado) a barra de
    # tarefas mostra o icone do python.exe em vez do icone da janela (iconbitmap
    # so troca o icone do titulo/Alt+Tab; quem manda no icone da taskbar e o
    # AppUserModelID do processo).
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VLFAdvogados.FichaTempo")
    App().mainloop()
