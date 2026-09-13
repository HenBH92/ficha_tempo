"""Combobox pesquisável reutilizável para listas grandes (Advogado/Tipo/Cliente/Pasta)."""
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import modelos
from cores import (COR_HOVER_NEUTRO, COR_POPUP_BORDA, COR_POPUP_FUNDO, COR_POPUP_TEXTO,
                   COR_PRIMARIA_CLARA, COR_TEXTO_SUAVE, COR_TOOLTIP_BORDA, COR_TOOLTIP_FUNDO)

MAX_RESULTADOS = 40
LINHAS_VISIVEIS = 8
ALTURA_LINHA = 28
ATRASO_DICA_MS = 400


class BuscaCombobox(ctk.CTkFrame):
    def __init__(self, master, opcoes: list[str], estrito: bool = True, command=None, **kw):
        super().__init__(master, fg_color="transparent")
        self.opcoes = opcoes
        self.estrito = estrito
        self.command = command
        self._popup: tk.Toplevel | None = None
        self._caixa: ctk.CTkFrame | None = None
        self._linhas: list[ctk.CTkButton] = []
        self._dicas: list["Tooltip"] = []
        self._itens: list[str] = []
        self._aberto = False
        self._topo = 0     # primeiro item de _itens desenhado (lista virtual: só LINHAS_VISIVEIS widgets)
        self._indice = -1  # item destacado; -1 = nenhum, pra Enter não trocar texto livre por sugestão
        self._job_focus_out: str | None = None
        self._job_seguir: str | None = None
        self._geometria = ""

        self.entry = ctk.CTkEntry(self, **kw)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Down>", lambda e: self._mover(1))
        self.entry.bind("<Up>", lambda e: self._mover(-1))
        self.entry.bind("<Return>", self._ao_enter)
        self.entry.bind("<Escape>", lambda e: self._esconder_popup())
        self.entry.bind("<Button-1>", self._ao_clicar)

        self.btn_seta = ctk.CTkButton(self, text="▼", width=24, font=ctk.CTkFont(size=9),
                                       fg_color="transparent", text_color=COR_TEXTO_SUAVE,
                                       hover_color=COR_HOVER_NEUTRO, command=self._mostrar_todos)
        self.btn_seta.pack(side="left", padx=(2, 0))

    def get(self) -> str:
        return self.entry.get().strip()

    def set(self, valor: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, valor)

    def _on_key(self, event) -> None:
        if event.keysym in ("Down", "Up", "Return", "Escape"):
            return
        texto = self.entry.get().strip().lower()
        if not texto:
            self._esconder_popup()
            return
        filtrados = [o for o in self.opcoes if texto in o.lower()][:MAX_RESULTADOS]
        if filtrados:
            self._mostrar_popup(filtrados)
        else:
            self._esconder_popup()

    def _construir_popup(self) -> None:
        """Monta o popup uma vez só. As linhas são widgets reaproveitados (lista virtual):
        recriá-las a cada tecla digitada travava o campo, e o tk.Listbox que havia aqui antes
        era Tk puro - não seguia o tema do CTk nem tinha hover."""
        self._popup = tk.Toplevel(self)
        self._popup.wm_overrideredirect(True)
        self._popup.withdraw()
        self._caixa = ctk.CTkFrame(self._popup, corner_radius=0, border_width=1,
                                   border_color=COR_POPUP_BORDA, fg_color=COR_POPUP_FUNDO)
        self._caixa.pack(fill="both", expand=True)
        # Moldura só pra sobrar folga igual em cima e embaixo: a altura do popup sai do
        # reqheight da caixa, e sem isso a última linha encostava na borda.
        lista = ctk.CTkFrame(self._caixa, fg_color="transparent")
        lista.pack(fill="both", expand=True, pady=4)
        for i in range(LINHAS_VISIVEIS):
            # text=" " e não "": o CTkButton só cria o label interno quando há texto, e o
            # Tooltip abaixo precisa dele existindo pra se prender. Com "" a dica ficava só no
            # canvas, que o label cobre depois - o <Enter> nunca chegava (medido com mouse real).
            linha = ctk.CTkButton(lista, text=" ", anchor="w", height=ALTURA_LINHA,
                                  corner_radius=6, fg_color="transparent", text_color=COR_POPUP_TEXTO,
                                  hover_color=COR_HOVER_NEUTRO, font=ctk.CTkFont(size=12),
                                  command=lambda i=i: self._escolher(self._topo + i))
            self._dicas.append(Tooltip(linha, lambda i=i: self._dica_linha(i), lado="direita"))
            self._linhas.append(linha)
        # A bindtag do Toplevel também vale pros filhos: um bind aqui pega a roda em cima
        # de qualquer linha.
        self._popup.bind("<MouseWheel>", self._rolar)

    def _dica_linha(self, i: int) -> str:
        """Texto do hover da linha `i` - só quando não coube nela (modelo de descrição é longo).
        Sempre mostrar encheria a tela de balão por cima de código de pasta, que já cabe inteiro."""
        indice = self._topo + i
        if not 0 <= indice < len(self._itens):
            return ""
        linha, texto = self._linhas[i], self._itens[indice]
        # cget("font") devolve a fonte no tamanho pedido; quem renderiza aplica a escala de DPI.
        escala = ctk.ScalingTracker.get_widget_scaling(linha)
        cabe = linha.cget("font").measure(texto) * escala <= linha.winfo_width() - 12
        return "" if cabe else texto

    def _desenhar(self) -> None:
        visiveis = min(LINHAS_VISIVEIS, len(self._itens))
        self._topo = max(0, min(self._topo, len(self._itens) - visiveis))
        for i, linha in enumerate(self._linhas):
            if i >= visiveis:
                linha.pack_forget()
                continue
            indice = self._topo + i
            linha.configure(text=self._itens[indice],
                            fg_color=COR_PRIMARIA_CLARA if indice == self._indice else "transparent")
            linha.pack(fill="x", padx=4, pady=1)

    def _mostrar_popup(self, itens: list[str]) -> None:
        if self._popup is None:
            self._construir_popup()
        self._itens = itens
        self._topo, self._indice = 0, -1
        self._desenhar()
        self._popup.update_idletasks()
        self._posicionar()
        self._popup.deiconify()
        self._popup.lift()
        self._aberto = True
        self._seguir_campo()

    def _posicionar(self) -> None:
        largura = max(self.winfo_width(), self.winfo_reqwidth())
        geometria = (f"{largura}x{self._caixa.winfo_reqheight()}"
                     f"+{self.winfo_rootx()}+{self.winfo_rooty() + self.winfo_height() + 2}")
        if geometria != self._geometria:  # sem isso pisca ao reaplicar a mesma geometria
            self._geometria = geometria
            self._popup.geometry(geometria)

    def _seguir_campo(self) -> None:
        """Cola o popup no campo enquanto estiver aberto. É uma janela solta, e rolar a lista
        de cards ou redimensionar a janela não gera <Configure> aqui - a posição do campo dentro
        do pai não muda, só na tela. Por isso confere de tempos em tempos em vez de reagir a
        evento. ponytail: 40ms só enquanto aberto; se pesar, dá pra escutar o wheel do frame
        de cards e o <Configure> da janela."""
        if not self._aberto:
            return
        recorte = self._recorte()
        if recorte is not None:
            topo = self.winfo_rooty() - recorte.winfo_rooty()
            if topo < 0 or topo + self.winfo_height() > recorte.winfo_height():
                self._esconder_popup()  # campo saindo da área rolável: lista solta no meio da tela
                return
        self._posicionar()
        self._job_seguir = self.after(40, self._seguir_campo)

    def _recorte(self) -> tk.Canvas | None:
        """Canvas do frame rolável que contém o campo - é ele que recorta o card na rolagem.
        O campo continua mapeado quando sai de vista (o canvas só recorta), então é pela
        posição dentro dele que dá pra saber se ainda está visível."""
        pai = self.master
        while pai is not None:
            if isinstance(pai, tk.Canvas):
                return pai
            pai = pai.master
        return None

    def _esconder_popup(self) -> None:
        if self._job_seguir is not None:
            self.after_cancel(self._job_seguir)
            self._job_seguir = None
        if self._popup is not None:
            self._popup.withdraw()
        self._aberto = False

    def _rolar(self, event):
        if len(self._itens) > LINHAS_VISIVEIS:
            self._topo += -1 if event.delta > 0 else 1
            self._desenhar()
        # "break": sem isso a área de cards por baixo rola junto (bind_all do CTkScrollableFrame).
        return "break"

    def _mover(self, passo: int):
        """Seta pra cima/baixo anda no destaque sem tirar o foco do campo (dá pra continuar
        digitando). Com o popup fechado, a seta abre a lista."""
        if not self._aberto:
            self._mostrar_todos()
            return "break"
        if self._itens:
            self._indice = max(0, min(self._indice + passo, len(self._itens) - 1))
            self._topo = max(self._indice - LINHAS_VISIVEIS + 1, min(self._topo, self._indice))
            self._desenhar()
        return "break"

    def _ao_enter(self, event):
        if self._aberto and self._indice >= 0:
            self._escolher(self._indice)
            return "break"
        self._validar_e_fechar()
        return None

    def _mostrar_todos(self) -> None:
        """Botão de seta: mostra tudo que já está salvo, sem precisar digitar nada."""
        if self._job_focus_out is not None:
            self.after_cancel(self._job_focus_out)
            self._job_focus_out = None
        self.entry.focus_set()
        if self.opcoes:
            self._mostrar_popup(self.opcoes[:MAX_RESULTADOS])

    def _ao_clicar(self, event) -> None:
        """Clicar no campo já abre a lista completa, igual ao botão de seta."""
        if not self._aberto:
            self._mostrar_todos()

    def _escolher(self, indice: int) -> None:
        if 0 <= indice < len(self._itens):
            self.set(self._itens[indice])
        if self._job_focus_out is not None:  # o clique na linha tira o foco do campo
            self.after_cancel(self._job_focus_out)
            self._job_focus_out = None
        self._esconder_popup()
        self.entry.focus_set()
        if self.command:
            self.command()

    def _on_focus_out(self, event) -> None:
        # dá tempo do clique na listbox (ou no botão de seta) registrar antes de fechar/validar
        self._job_focus_out = self.after(150, self._validar_e_fechar)

    def _validar_e_fechar(self) -> None:
        self._job_focus_out = None
        self._esconder_popup()
        if self.estrito:
            texto = self.get()
            if texto and texto not in self.opcoes:
                self.entry.delete(0, "end")
        if self.command:
            self.command()


class DescricaoModeloEntry(BuscaCombobox):
    """Campo de texto livre; digitar "/" sugere modelos salvos (Enter ou Tab completa)."""

    def __init__(self, master, opcoes: list[str], **kw):
        super().__init__(master, opcoes, estrito=False, **kw)
        self.entry.bind("<Return>", self._completar)
        self.entry.bind("<Tab>", self._completar)

    def _on_key(self, event) -> None:
        if event.keysym in ("Down", "Up", "Return", "Escape", "Tab"):
            return
        texto = self.entry.get()
        if not texto.startswith("/"):
            self._esconder_popup()
            return
        consulta = texto[1:].strip().lower()
        filtrados = [o for o in self.opcoes if consulta in o.lower()][:MAX_RESULTADOS]
        if filtrados:
            self._mostrar_popup(filtrados)
        else:
            self._esconder_popup()

    def _construir_popup(self) -> None:
        super()._construir_popup()
        for i, linha in enumerate(self._linhas):
            linha.bind("<Button-3>", lambda e, i=i: self._remover_clicado(self._topo + i))

    def _completar(self, event):
        if self._aberto and self._itens:
            self._escolher(max(self._indice, 0))  # sem destaque, Enter/Tab pega o primeiro
            return "break"
        return None

    def _remover_clicado(self, indice: int) -> None:
        if not 0 <= indice < len(self._itens):
            return
        item = self._itens[indice]
        if messagebox.askyesno("Remover modelo", f'Remover o modelo "{item}"?'):
            self.opcoes[:] = modelos.remover_modelo(item)
            self._esconder_popup()


class Tooltip:
    """Texto flutuante ao passar o mouse sobre um widget (hover).

    `texto` também aceita uma função: as linhas do dropdown trocam de conteúdo conforme filtra
    e rola, então a dica delas só pode ser lida na hora do hover. Função que devolve "" não
    abre balão nenhum.

    `lado="direita"` para linhas de lista - abaixo o balão cairia em cima da linha seguinte, e
    o mouse indo pra ela entraria no balão (<Leave> na linha), fechando e reabrindo sem parar."""

    def __init__(self, widget, texto, lado: str = "abaixo"):
        self.widget = widget
        self.texto = texto
        self.lado = lado
        self.popup: tk.Toplevel | None = None
        self._job: str | None = None
        widget.bind("<Enter>", self._agendar)
        widget.bind("<Leave>", self._esconder)

    def _agendar(self, event=None) -> None:
        """Atraso pra passar o mouse por cima sem disparar balão em tudo que toca."""
        self._cancelar()
        self._job = self.widget.after(ATRASO_DICA_MS, self._mostrar)

    def _cancelar(self) -> None:
        if self._job is not None:
            self.widget.after_cancel(self._job)
            self._job = None

    def _mostrar(self, event=None) -> None:
        self._job = None
        if self.popup is not None:
            return
        texto = self.texto() if callable(self.texto) else self.texto
        if not texto:
            return
        self.popup = tk.Toplevel(self.widget)
        self.popup.wm_overrideredirect(True)
        self.popup.withdraw()
        self.popup.configure(background=COR_TOOLTIP_FUNDO)
        caixa = ctk.CTkFrame(self.popup, corner_radius=0, fg_color=COR_TOOLTIP_FUNDO,
                             border_width=1, border_color=COR_TOOLTIP_BORDA)
        caixa.pack(fill="both", expand=True)
        ctk.CTkLabel(caixa, text=texto, justify="left", wraplength=320, corner_radius=0,
                     fg_color=COR_TOOLTIP_FUNDO, text_color="#f2f2f5",
                     font=ctk.CTkFont(size=11)).pack(padx=10, pady=7)
        self.popup.update_idletasks()
        if self.lado == "direita":
            x = self.widget.winfo_rootx() + self.widget.winfo_width() + 6
            y = self.widget.winfo_rooty()
        else:
            x = self.widget.winfo_rootx()
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        # Balão de linha de lista pode nascer perto da borda da tela; sem isso some metade dele.
        x = max(0, min(x, self.widget.winfo_screenwidth() - self.popup.winfo_reqwidth() - 4))
        y = max(0, min(y, self.widget.winfo_screenheight() - self.popup.winfo_reqheight() - 4))
        self.popup.wm_geometry(f"+{x}+{y}")
        self.popup.deiconify()
        self.popup.lift()

    def _esconder(self, event=None) -> None:
        self._cancelar()
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None


def _demo():
    class _Ev:
        keysym = "t"
        delta = -120  # roda pra baixo

    root = ctk.CTk()
    root.withdraw()

    campo = DescricaoModeloEntry(root, ["Elaboração de contestação", "Audiência de instrução"])
    campo.entry.insert(0, "/contest")
    campo._on_key(_Ev())
    assert campo._aberto
    assert campo._linhas[0].cget("text") == "Elaboração de contestação"

    assert campo._completar(None) == "break"
    assert campo.get() == "Elaboração de contestação"
    assert not campo._aberto

    campo._mostrar_todos()
    assert campo._aberto
    assert campo._itens == campo.opcoes
    campo._esconder_popup()

    campo.set("")
    campo.entry.insert(0, "/inexistente")
    campo._on_key(_Ev())
    assert not campo._aberto
    assert campo._completar(None) is None

    campo.set("")
    campo._ao_clicar(None)
    assert campo._aberto and len(campo._itens) == 2
    campo._ao_clicar(None)
    assert len(campo._linhas) == LINHAS_VISIVEIS  # já aberto: segundo clique não recria as linhas
    campo._esconder_popup()

    # Lista virtual: mais itens do que linhas, a roda desliza a janela sem criar widget.
    lista = BuscaCombobox(root, [f"item {i}" for i in range(20)])
    lista._mostrar_todos()
    assert lista._topo == 0 and lista._linhas[0].cget("text") == "item 0"
    lista._rolar(_Ev())
    assert lista._topo == 1 and lista._linhas[0].cget("text") == "item 1"
    lista._topo = 999
    lista._desenhar()
    assert lista._topo == 20 - LINHAS_VISIVEIS  # não rola além do fim

    # Seta anda no destaque e arrasta a janela junto; Enter só troca o texto se houver destaque.
    assert lista._indice == -1
    assert lista._ao_enter(None) is None and lista.get() == ""
    lista._mostrar_todos()
    for _ in range(LINHAS_VISIVEIS + 2):
        lista._mover(1)
    assert lista._indice == LINHAS_VISIVEIS + 1
    assert lista._topo == 2 and lista._linhas[-1].cget("text") == f"item {LINHAS_VISIVEIS + 1}"
    assert lista._ao_enter(None) == "break"
    assert lista.get() == f"item {LINHAS_VISIVEIS + 1}"
    assert not lista._aberto

    # Hover da linha: texto lido na hora do mouse, e só quando não coube na linha.
    dropdown = BuscaCombobox(root, ["curto", "D" * 300])
    dropdown._mostrar_todos()
    root.update()
    assert dropdown._dica_linha(0) == ""
    assert dropdown._dica_linha(1) == "D" * 300
    assert dropdown._dica_linha(LINHAS_VISIVEIS - 1) == ""  # linha sem item

    # Regressão: o CTkButton só cria o label interno quando tem texto, e é ele que fica embaixo
    # do mouse. Se a dica não estiver presa nele, o <Enter> nunca chega e o hover não abre.
    rotulos = [f for f in dropdown._linhas[1].winfo_children() if isinstance(f, tk.Label)]
    assert rotulos, "CTkButton sem label interno: a dica não teria onde se prender"
    rotulos[0].event_generate("<Enter>")
    assert dropdown._dicas[1]._job is not None
    dropdown._dicas[1]._esconder()
    dropdown._esconder_popup()

    # O popup é janela solta: fica colado no campo por acompanhamento, não por evento.
    assert dropdown._recorte() is None  # sem frame rolável em volta
    dropdown._mostrar_todos()
    assert dropdown._job_seguir is not None
    geometria = dropdown._geometria
    dropdown._posicionar()
    assert dropdown._geometria == geometria  # não se mexeu: não reaplica geometria (piscava)
    dropdown._esconder_popup()
    assert dropdown._job_seguir is None
    dropdown._seguir_campo()
    assert dropdown._job_seguir is None  # fechado: não reagenda

    botao = ctk.CTkButton(root, text="x")
    dica = Tooltip(botao, "explicação")
    dica._mostrar()
    assert dica.popup is not None
    dica._esconder()
    assert dica.popup is None

    vazia = Tooltip(botao, lambda: "")
    vazia._mostrar()
    assert vazia.popup is None

    root.destroy()
    print("widgets.py OK")


if __name__ == "__main__":
    _demo()
