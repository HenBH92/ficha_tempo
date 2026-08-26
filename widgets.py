"""Combobox pesquisável reutilizável para listas grandes (Advogado/Tipo/Cliente/Pasta)."""
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

import modelos

MAX_RESULTADOS = 40


def _cores_popup() -> tuple[str, str, str, str, str]:
    """Cores do popup de busca (bg, fg, selectbg, selectfg, borda), ajustadas ao modo
    claro/escuro atual do CTk - tk.Listbox é Tk puro e não segue o tema sozinho."""
    if ctk.get_appearance_mode() == "Dark":
        return "#26262e", "#e6e6ec", "#201747", "white", "#3a3a44"
    return "white", "#26262e", "#201747", "white", "#c7c7d1"


class BuscaCombobox(ctk.CTkFrame):
    def __init__(self, master, opcoes: list[str], estrito: bool = True, command=None, **kw):
        super().__init__(master, fg_color="transparent")
        self.opcoes = opcoes
        self.estrito = estrito
        self.command = command
        self._popup: tk.Toplevel | None = None
        self._listbox: tk.Listbox | None = None
        self._job_focus_out: str | None = None

        self.entry = ctk.CTkEntry(self, **kw)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<KeyRelease>", self._on_key)
        self.entry.bind("<FocusOut>", self._on_focus_out)
        self.entry.bind("<Down>", self._focar_lista)
        self.entry.bind("<Return>", lambda e: self._validar_e_fechar())
        self.entry.bind("<Escape>", lambda e: self._esconder_popup())
        self.entry.bind("<Button-1>", self._ao_clicar)

        self.btn_seta = ctk.CTkButton(self, text="▼", width=22, fg_color="transparent",
                                       border_width=1, border_color="#c7c7d1", text_color="#6c6c78",
                                       hover_color="#e1e1ea", command=self._mostrar_todos)
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

    def _mostrar_popup(self, itens: list[str]) -> None:
        if self._popup is None:
            cor_fundo, cor_texto, cor_sel_fundo, cor_sel_texto, cor_borda = _cores_popup()
            self._popup = tk.Toplevel(self)
            self._popup.wm_overrideredirect(True)
            self._popup.configure(background=cor_borda)
            self._listbox = tk.Listbox(
                self._popup, height=min(8, len(itens)), font=("Segoe UI", 10),
                bg=cor_fundo, fg=cor_texto, selectbackground=cor_sel_fundo,
                selectforeground=cor_sel_texto, activestyle="none",
                relief="flat", borderwidth=0, highlightthickness=0,
            )
            self._listbox.pack(fill="both", expand=True, padx=1, pady=1)
            self._listbox.bind("<<ListboxSelect>>", self._selecionar)
            self._listbox.bind("<Return>", self._selecionar)
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height()
        largura = self.entry.winfo_width()
        self._popup.geometry(f"{largura}x{min(8, len(itens)) * 20}+{x}+{y}")
        self._listbox.configure(height=min(8, len(itens)))
        self._listbox.delete(0, "end")
        for item in itens:
            self._listbox.insert("end", item)
        self._popup.deiconify()
        self._popup.lift()

    def _esconder_popup(self) -> None:
        if self._popup is not None:
            self._popup.destroy()
            self._popup = None
            self._listbox = None

    def _focar_lista(self, event) -> None:
        if self._listbox is not None:
            self._listbox.focus_set()
            self._listbox.selection_set(0)

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
        if self._popup is None:
            self._mostrar_todos()

    def _selecionar(self, event) -> None:
        if self._listbox is None:
            return
        selecao = self._listbox.curselection()
        if selecao:
            self.set(self._listbox.get(selecao[0]))
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

    def _mostrar_popup(self, itens: list[str]) -> None:
        novo = self._listbox is None
        super()._mostrar_popup(itens)
        if novo:
            self._listbox.bind("<Button-3>", self._remover_clicado)

    def _completar(self, event):
        if self._popup is not None and self._listbox is not None:
            selecao = self._listbox.curselection()
            indice = selecao[0] if selecao else 0
            self.set(self._listbox.get(indice))
            self._esconder_popup()
            return "break"
        return None

    def _remover_clicado(self, event) -> None:
        indice = self._listbox.nearest(event.y)
        if indice < 0:
            return
        item = self._listbox.get(indice)
        if messagebox.askyesno("Remover modelo", f'Remover o modelo "{item}"?'):
            self.opcoes[:] = modelos.remover_modelo(item)
            self._esconder_popup()


class Tooltip:
    """Texto flutuante ao passar o mouse sobre um widget (hover)."""

    def __init__(self, widget, texto: str):
        self.widget = widget
        self.texto = texto
        self.popup: tk.Toplevel | None = None
        widget.bind("<Enter>", self._mostrar)
        widget.bind("<Leave>", self._esconder)

    def _mostrar(self, event=None) -> None:
        if self.popup is not None:
            return
        x = self.widget.winfo_rootx()
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.popup = tk.Toplevel(self.widget)
        self.popup.wm_overrideredirect(True)
        self.popup.wm_geometry(f"+{x}+{y}")
        tk.Label(self.popup, text=self.texto, justify="left", background="#333333",
                 foreground="white", relief="solid", borderwidth=1,
                 font=("Segoe UI", 9), padx=8, pady=6, wraplength=260).pack()

    def _esconder(self, event=None) -> None:
        if self.popup is not None:
            self.popup.destroy()
            self.popup = None


def _demo():
    class _Ev:
        keysym = "t"

    root = ctk.CTk()
    root.withdraw()

    campo = DescricaoModeloEntry(root, ["Elaboração de contestação", "Audiência de instrução"])
    campo.entry.insert(0, "/contest")
    campo._on_key(_Ev())
    assert campo._popup is not None
    assert campo._listbox.get(0) == "Elaboração de contestação"

    assert campo._completar(None) == "break"
    assert campo.get() == "Elaboração de contestação"
    assert campo._popup is None

    campo._mostrar_todos()
    assert campo._popup is not None
    assert campo._listbox.size() == 2
    campo._esconder_popup()

    campo.set("")
    campo.entry.insert(0, "/inexistente")
    campo._on_key(_Ev())
    assert campo._popup is None
    assert campo._completar(None) is None

    campo.set("")
    campo._ao_clicar(None)
    assert campo._popup is not None
    assert campo._listbox.size() == 2
    campo._ao_clicar(None)
    assert campo._listbox.size() == 2  # já aberto: segundo clique não recria o popup
    campo._esconder_popup()

    botao = ctk.CTkButton(root, text="x")
    dica = Tooltip(botao, "explicação")
    dica._mostrar()
    assert dica.popup is not None
    dica._esconder()
    assert dica.popup is None

    root.destroy()
    print("widgets.py OK")


if __name__ == "__main__":
    _demo()
