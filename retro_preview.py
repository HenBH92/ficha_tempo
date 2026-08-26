"""Janela de prévia do lançamento retroativo: mostra as linhas lidas de uma planilha
retroativa (ver retroativo.py) antes de mandar pro AdvWin, com campos editáveis e
possibilidade de excluir linhas do lote. Sem cronômetro - são horas já registradas no
passado, só falta lançar."""
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import advwin
import favoritos
import icones
import planilha
import retroativo
from widgets import BuscaCombobox

COR_PRIMARIA = "#201747"
COR_SUCESSO = "#1f6f4a"
COR_SUCESSO_HOVER = "#175939"
COR_PERIGO = "#b3261e"
COR_BORDA_CARD = ("#e1e1ea", "#3a3a44")
COR_FUNDO_CARD = ("#f7f7fb", "#26262e")
COR_TEXTO_SUAVE = ("#6c6c78", "#9a99a8")
COR_DOURADO = "#b8860b"
COR_ESTRELA_HOVER = ("#f5f0e4", "#3a3122")
COR_PRIMARIA_HOVER = "#342a63"
COR_RELOGIO_DIGITO = "#7cffc4"
COR_RELOGIO_LEGENDA = "#a79cd1"


def selecionar_e_ler(parent) -> tuple[Path, list[retroativo.LinhaRetroativa]] | None:
    """Abre o seletor de arquivo, lê as linhas pendentes e mostra erros/avisos via
    messagebox. Retorna None se o usuário cancelar, a leitura falhar ou não houver
    linha pendente - nesses casos não há nada mais a fazer."""
    caminho_txt = filedialog.askopenfilename(
        parent=parent, title="Selecionar planilha retroativa", filetypes=[("Planilha Excel", "*.xlsx")]
    )
    if not caminho_txt:
        return None
    caminho = Path(caminho_txt)
    try:
        linhas = retroativo.ler_linhas_pendentes(caminho)
    except Exception as e:
        messagebox.showerror("Lançamento retroativo", f"Não foi possível ler a planilha:\n{e}")
        return None
    if not linhas:
        messagebox.showinfo("Lançamento retroativo", "Nenhuma linha pendente encontrada nessa planilha.")
        return None
    return caminho, linhas


def _formatar_horas(total: timedelta) -> str:
    minutos = round(total.total_seconds() / 60)
    return f"{minutos // 60}:{minutos % 60:02d}"


class _LinhaPreview(ctk.CTkFrame):
    def __init__(self, master, item: retroativo.LinhaRetroativa, pastas_favoritas: list[str], advogado_atual: str):
        super().__init__(master, corner_radius=8, border_width=1,
                          border_color=COR_BORDA_CARD, fg_color=COR_FUNDO_CARD)
        self.item = item
        self.advogado_atual = advogado_atual
        self.pastas_favoritas = pastas_favoritas

        campos = ctk.CTkFrame(self, fg_color="transparent")
        campos.pack(fill="x", padx=8, pady=(8, 2))

        self.var_incluir = ctk.BooleanVar(value=True)
        self.checkbox_incluir = ctk.CTkCheckBox(campos, text="", variable=self.var_incluir, width=20)
        self.checkbox_incluir.pack(side="left", padx=(2, 8))

        self.entry_data = self._campo(campos, "Data", item.data, 85)

        bloco_pasta = ctk.CTkFrame(campos, fg_color="transparent")
        bloco_pasta.pack(side="left", padx=4)
        ctk.CTkLabel(bloco_pasta, text="Pasta", font=ctk.CTkFont(size=10),
                     text_color=COR_TEXTO_SUAVE, anchor="w").pack(anchor="w")
        linha_pasta = ctk.CTkFrame(bloco_pasta, fg_color="transparent")
        linha_pasta.pack()
        self.cb_pasta = BuscaCombobox(linha_pasta, pastas_favoritas, estrito=False, width=140,
                                       command=self._atualizar_estrela_pasta)
        self.cb_pasta.set(item.pasta)
        self.cb_pasta.pack(side="left")
        self.btn_favoritar_pasta = ctk.CTkButton(linha_pasta, text="", image=icones.icone("estrela", cor=COR_DOURADO),
                                                  width=26, fg_color="transparent", border_width=1,
                                                  border_color=COR_DOURADO, hover_color=COR_ESTRELA_HOVER,
                                                  command=self._alternar_favorito_pasta)
        self.btn_favoritar_pasta.pack(side="left", padx=(4, 0))
        self._atualizar_estrela_pasta()

        self.entry_descricao = self._campo(campos, "Descrição", item.descricao, 240)
        self.entry_horas = self._campo(campos, "Horas cobráveis", item.horas_texto, 90)

        self.label_status = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                          font=ctk.CTkFont(size=11), text_color=COR_TEXTO_SUAVE)
        self.label_status.pack(fill="x", padx=10, pady=(0, 6))

    def _atualizar_estrela_pasta(self) -> None:
        ativo = self.cb_pasta.get() in self.pastas_favoritas
        if ativo:
            self.btn_favoritar_pasta.configure(fg_color=COR_DOURADO, border_width=0,
                                                image=icones.icone("estrela", cor="white"))
        else:
            self.btn_favoritar_pasta.configure(fg_color="transparent", border_width=1, border_color=COR_DOURADO,
                                                image=icones.icone("estrela", cor=COR_DOURADO))

    def _alternar_favorito_pasta(self) -> None:
        valor = self.cb_pasta.get()
        if not valor:
            return
        self.pastas_favoritas[:] = favoritos.alternar_pasta(valor)
        self._atualizar_estrela_pasta()

    def _campo(self, master, rotulo: str, valor: str, largura: int) -> ctk.CTkEntry:
        bloco = ctk.CTkFrame(master, fg_color="transparent")
        bloco.pack(side="left", padx=4)
        ctk.CTkLabel(bloco, text=rotulo, font=ctk.CTkFont(size=10),
                     text_color=COR_TEXTO_SUAVE, anchor="w").pack(anchor="w")
        entrada = ctk.CTkEntry(bloco, width=largura)
        entrada.insert(0, valor)
        entrada.pack()
        return entrada

    def valores_editados(self) -> retroativo.LinhaRetroativa:
        return retroativo.LinhaRetroativa(
            linha=self.item.linha,
            pasta=self.cb_pasta.get().strip(),
            data=self.entry_data.get().strip(),
            descricao=self.entry_descricao.get().strip(),
            horas_texto=self.entry_horas.get().strip(),
            advogado=self.advogado_atual,
            cliente=self.item.cliente,
        )

    def marcar_status(self, texto: str, cor: str) -> None:
        self.label_status.configure(text=texto, text_color=cor)

    def marcar_lancada(self) -> None:
        """Já foi lançada de verdade no AdvWin - tira do lote e trava a marcação pra uma
        eventual nova tentativa não relançar (duplicaria a hora no AdvWin)."""
        self.var_incluir.set(False)
        self.checkbox_incluir.configure(state="disabled")


class JanelaRetroativa(ctk.CTkToplevel):
    def __init__(self, master, caminho: Path, linhas: list[retroativo.LinhaRetroativa],
                 advogado_atual: str, pastas_favoritas: list[str]):
        super().__init__(master)
        self.title("Lançamento retroativo no AdvWin")
        self.geometry("900x580")
        self._processando = False
        self.advogado_atual = advogado_atual
        self.pastas_favoritas = pastas_favoritas

        cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        cabecalho.pack(fill="x", padx=16, pady=(14, 6))
        self.label_titulo = ctk.CTkLabel(cabecalho, text="", font=ctk.CTkFont(size=13, weight="bold"))
        self.label_titulo.pack(side="left", anchor="w")
        self._construir_relogio_total(cabecalho).pack(side="right")

        barra_selecao = ctk.CTkFrame(self, fg_color="transparent")
        barra_selecao.pack(fill="x", padx=16, pady=(0, 4))
        self.var_selecionar_todas = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(barra_selecao, text="Selecionar todas", variable=self.var_selecionar_todas,
                         command=self._alternar_selecionar_todas).pack(side="left")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=("white", "#18181d"))
        self.scroll.pack(fill="both", expand=True, padx=16)

        self.linhas_preview: list[_LinhaPreview] = []

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=16, pady=14)
        self.label_resumo = ctk.CTkLabel(barra, text="", text_color=COR_TEXTO_SUAVE)
        self.label_resumo.pack(side="left")
        self.btn_lancar = ctk.CTkButton(barra, text="Lançar todas no AdvWin", height=36,
                                         fg_color=COR_SUCESSO, hover_color=COR_SUCESSO_HOVER,
                                         command=self._confirmar_lote)
        self.btn_lancar.pack(side="right")
        self.btn_fechar = ctk.CTkButton(barra, text="Fechar", height=36, fg_color="transparent",
                                         border_width=1, border_color=COR_PRIMARIA, text_color=COR_PRIMARIA,
                                         command=self._fechar)
        self.btn_fechar.pack(side="right", padx=8)
        self.btn_carregar_outra = ctk.CTkButton(barra, text="Carregar outra planilha", height=36,
                                                 fg_color="transparent", border_width=1,
                                                 border_color=COR_PRIMARIA, text_color=COR_PRIMARIA,
                                                 command=self._carregar_outra)
        self.btn_carregar_outra.pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self._carregar_planilha(caminho, linhas)

        self.transient(master)
        self.lift()
        self.focus_force()

    def _construir_relogio_total(self, master) -> ctk.CTkFrame:
        """Total de horas cobráveis marcadas, estilizado como o relógio digital da tela principal."""
        caixa = ctk.CTkFrame(master, fg_color=COR_PRIMARIA, corner_radius=10,
                              border_width=1, border_color=COR_PRIMARIA_HOVER)
        conteudo = ctk.CTkFrame(caixa, fg_color="transparent")
        conteudo.pack(padx=20, pady=8)
        ctk.CTkLabel(conteudo, text="H O R A S   M A R C A D A S", font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=COR_RELOGIO_LEGENDA).pack()
        self.label_total_horas = ctk.CTkLabel(
            conteudo, text="0:00", font=ctk.CTkFont(family="Consolas", size=30, weight="bold"),
            text_color=COR_RELOGIO_DIGITO,
        )
        self.label_total_horas.pack()
        return caixa

    def _carregar_planilha(self, caminho: Path, linhas: list[retroativo.LinhaRetroativa]) -> None:
        self.caminho = caminho
        for lp in self.linhas_preview:
            lp.destroy()
        self.linhas_preview = []
        self.label_titulo.configure(
            text=f'{len(linhas)} linha(s) de "{caminho.name}" - revise e edite antes de lançar'
        )
        for item in linhas:
            linha_widget = _LinhaPreview(self.scroll, item, self.pastas_favoritas, self.advogado_atual)
            linha_widget.pack(fill="x", pady=4)
            linha_widget.var_incluir.trace_add("write", lambda *_: self._recalcular_total())
            linha_widget.entry_horas.bind("<KeyRelease>", lambda _e: self._recalcular_total())
            self.linhas_preview.append(linha_widget)
        self.var_selecionar_todas.set(True)
        self.label_resumo.configure(text="")
        self.btn_lancar.configure(text="Lançar todas no AdvWin", state="normal")
        self._recalcular_total()

    def _alternar_selecionar_todas(self) -> None:
        valor = self.var_selecionar_todas.get()
        for lp in self.linhas_preview:
            if lp.checkbox_incluir.cget("state") != "disabled":
                lp.var_incluir.set(valor)

    def _recalcular_total(self) -> None:
        total = timedelta()
        for lp in self.linhas_preview:
            if not lp.var_incluir.get():
                continue
            horas = planilha.parse_horas_cobraveis(lp.entry_horas.get())
            if horas:
                total += horas
        self.label_total_horas.configure(text=_formatar_horas(total))

    def _carregar_outra(self) -> None:
        if self._processando:
            messagebox.showwarning("Lançamento retroativo", "Aguarde o lote terminar antes de carregar outra planilha.")
            return
        resultado = selecionar_e_ler(self)
        if resultado is None:
            return
        caminho, linhas = resultado
        self._carregar_planilha(caminho, linhas)

    def _fechar(self) -> None:
        if self._processando:
            messagebox.showwarning("Lançamento retroativo", "Aguarde o lote terminar antes de fechar esta janela.")
            return
        self.destroy()

    def _confirmar_lote(self) -> None:
        incluidas = [lp for lp in self.linhas_preview if lp.var_incluir.get()]
        if not incluidas:
            messagebox.showinfo("Lançamento retroativo", "Nenhuma linha marcada para lançar.")
            return
        if not messagebox.askyesno(
            "Lançar retroativo",
            f"Isso vai lançar {len(incluidas)} linha(s) no AdvWin, uma de cada vez. "
            "Essa ação não pode ser desfeita. Continuar?",
            icon="warning",
        ):
            return

        self._processando = True
        self._lote_atual = incluidas
        self._total = len(incluidas)
        self._ok = 0
        self._erros = 0
        self.btn_carregar_outra.configure(state="disabled")
        self.btn_lancar.configure(state="disabled")
        for lp in incluidas:
            lp.marcar_status("⏳ na fila...", COR_TEXTO_SUAVE)
            item = lp.valores_editados()
            advwin.enfileirar(
                lambda item=item: advwin.lancar_horas(
                    advwin.pagina_advwin(), item.pasta, item.data, item.descricao, item.horas_texto
                ),
                lambda resultado, erro, lp=lp, item=item: self._apos_linha(lp, item, erro),
            )

    def _apos_linha(self, lp: _LinhaPreview, item: retroativo.LinhaRetroativa, erro: Exception | None) -> None:
        """Roda na thread de fundo da fila do AdvWin - só a atualização de widgets abaixo
        precisa passar por self.after(0, ...)."""
        if erro is None:
            marcado = self._marcar_linha_segura(
                item, f"Lançado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            try:
                horas = planilha.parse_horas_cobraveis(item.horas_texto) or timedelta()
                planilha.inserir_linha({
                    "data": datetime.strptime(item.data, "%d/%m/%Y").date(),
                    "advogado": item.advogado, "cliente": item.cliente, "pasta": item.pasta,
                    "descricao": item.descricao, "horas": horas, "horas_cobraveis": horas,
                }, planilha.CAMINHO_LOG_ADVWIN)
            except Exception:
                pass  # falha só no log local não deve travar o lote nem contar como erro
            self._ok += 1
            self.after(0, lp.marcar_lancada)
            if marcado:
                self.after(0, lp.marcar_status, "✓ lançado", COR_SUCESSO)
            else:
                # Já foi lançado no AdvWin de verdade - não marcar aqui é o perigo real
                # (reabrir esse arquivo relançaria a mesma linha), por isso fica bem visível.
                self.after(0, lp.marcar_status,
                           "⚠ LANÇADO NO ADVWIN, mas não marcado na planilha (feche o arquivo e "
                           "avise antes de reabrir esta planilha - senão duplica)", "#b3261e")
        else:
            mensagem = advwin.mensagem_amigavel(erro)
            self._marcar_linha_segura(item, f"Erro: {mensagem}")
            self._erros += 1
            self.after(0, lp.marcar_status, f"✗ {mensagem}", COR_PERIGO)

        concluidos = self._ok + self._erros
        self.after(0, self._atualizar_resumo, concluidos)
        if concluidos == self._total:
            self.after(0, self._finalizar_lote)

    def _marcar_linha_segura(self, item: retroativo.LinhaRetroativa, texto_status: str) -> bool:
        try:
            retroativo.marcar_linha(self.caminho, item.linha, texto_status)
            return True
        except Exception as e:
            print(f"[retroativo] não deu pra marcar a linha {item.linha} em {self.caminho}: {e!r}")
            return False

    def _atualizar_resumo(self, concluidos: int) -> None:
        self.label_resumo.configure(text=f"Lançando... {concluidos}/{self._total} ({self._erros} com erro)")
        self._recalcular_total()

    def _finalizar_lote(self) -> None:
        self._processando = False
        self.label_resumo.configure(text=f"Concluído: {self._ok} ok, {self._erros} com erro.")
        self.btn_carregar_outra.configure(state="normal")
        if self._erros:
            self.btn_lancar.configure(text=f"Tentar novamente ({self._erros})", state="normal")
        else:
            self.btn_lancar.configure(text="Lote concluído", state="disabled")

        log = "\n".join(
            f"Linha {lp.item.linha} - {lp.cb_pasta.get().strip()}: {lp.label_status.cget('text')}"
            for lp in self._lote_atual
        )
        messagebox.showinfo(
            "Lançamento retroativo concluído",
            f"{self._ok} lançada(s) com sucesso, {self._erros} com erro.\n\n{log}",
        )
