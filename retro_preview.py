"""Janela de prévia do lançamento retroativo: mostra as linhas lidas de uma ou mais
planilhas retroativas (ver retroativo.py) antes de mandar pro AdvWin, com campos
editáveis e possibilidade de excluir linhas do lote. Sem cronômetro - são horas já
registradas no passado, só falta lançar."""
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import advwin
import favoritos
import icones
import planilha
import retroativo
from cores import (
    COR_BORDA_CARD,
    COR_FUNDO_CARD,
    COR_MARCA_LARANJA,
    COR_MARCA_LARANJA_CLARA,
    COR_PERIGO,
    COR_PRIMARIA,
    COR_PRIMARIA_HOVER,
    COR_RELOGIO_DIGITO,
    COR_RELOGIO_LEGENDA,
    COR_SUCESSO,
    COR_TEXTO_SUAVE,
)
from widgets import BuscaCombobox


def selecionar_e_ler_varias(parent) -> list[tuple[Path, list[retroativo.LinhaRetroativa]]]:
    """Abre o seletor de arquivos (multi-seleção), lê as linhas pendentes de cada
    planilha escolhida e mostra um único aviso agregado para as que falharem ou não
    tiverem linha pendente - essas são puladas, as demais seguem carregando
    normalmente. Retorna lista vazia se o usuário cancelar ou nenhum arquivo for
    aproveitável."""
    caminhos_txt = filedialog.askopenfilenames(
        parent=parent, title="Selecionar planilha(s) retroativa(s)", filetypes=[("Planilha Excel", "*.xlsx")]
    )
    if not caminhos_txt:
        return []
    resultado = []
    avisos = []
    for caminho_txt in caminhos_txt:
        caminho = Path(caminho_txt)
        try:
            linhas = retroativo.ler_linhas_pendentes(caminho)
        except Exception as e:
            avisos.append(f"{caminho.name}: não foi possível ler ({e})")
            continue
        if not linhas:
            avisos.append(f"{caminho.name}: nenhuma linha pendente")
            continue
        resultado.append((caminho, linhas))
    if avisos:
        messagebox.showwarning("Lançamento retroativo", "\n".join(avisos))
    return resultado


def _formatar_horas(total: timedelta) -> str:
    minutos = round(total.total_seconds() / 60)
    return f"{minutos // 60}:{minutos % 60:02d}"


class _LinhaPreview(ctk.CTkFrame):
    def __init__(self, master, caminho: Path, item: retroativo.LinhaRetroativa,
                 pastas_favoritas: list[str], advogado_atual: str):
        super().__init__(master, corner_radius=8, border_width=1,
                          border_color=COR_BORDA_CARD, fg_color=COR_FUNDO_CARD)
        self.caminho = caminho
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
        self.btn_favoritar_pasta = ctk.CTkButton(linha_pasta, text="", image=icones.icone("estrela", cor=COR_MARCA_LARANJA),
                                                  width=26, fg_color="transparent", border_width=1,
                                                  border_color=COR_MARCA_LARANJA, hover_color=COR_MARCA_LARANJA_CLARA,
                                                  command=self._alternar_favorito_pasta)
        self.btn_favoritar_pasta.pack(side="left", padx=(4, 0))
        self._atualizar_estrela_pasta()

        self.entry_descricao = self._campo(campos, "Descrição", item.descricao, 240)
        self.entry_horas = self._campo(campos, "Horas", item.horas_texto, 90)

        self.label_status = ctk.CTkLabel(self, text="", anchor="w", justify="left",
                                          font=ctk.CTkFont(size=11), text_color=COR_TEXTO_SUAVE)
        self.label_status.pack(fill="x", padx=10, pady=(0, 6))

    def _atualizar_estrela_pasta(self) -> None:
        ativo = self.cb_pasta.get() in self.pastas_favoritas
        if ativo:
            self.btn_favoritar_pasta.configure(fg_color=COR_MARCA_LARANJA, border_width=0,
                                                image=icones.icone("estrela", cor="white"))
        else:
            self.btn_favoritar_pasta.configure(fg_color="transparent", border_width=1, border_color=COR_MARCA_LARANJA,
                                                image=icones.icone("estrela", cor=COR_MARCA_LARANJA))

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
    def __init__(self, master, lotes: list[tuple[Path, list[retroativo.LinhaRetroativa]]],
                 advogado_atual: str, pastas_favoritas: list[str], area_atual: str = "Trabalhista"):
        super().__init__(master)
        self.title("Lançamento retroativo no AdvWin")
        self.geometry("900x580")
        self._processando = False
        self.advogado_atual = advogado_atual
        self.pastas_favoritas = pastas_favoritas
        self.area_atual = area_atual

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
        ctk.CTkButton(barra_selecao, text="Baixar planilha modelo", height=28, fg_color="transparent",
                       border_width=1, border_color=COR_PRIMARIA, text_color=COR_PRIMARIA,
                       command=self._baixar_modelo).pack(side="right")

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=("white", "#18181d"))
        self.scroll.pack(fill="both", expand=True, padx=16)

        self.linhas_preview: list[_LinhaPreview] = []
        self.arquivos: list[Path] = []

        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.pack(fill="x", padx=16, pady=14)
        self.label_resumo = ctk.CTkLabel(barra, text="", text_color=COR_TEXTO_SUAVE)
        self.label_resumo.pack(side="left")
        self.btn_lancar = ctk.CTkButton(barra, text="Lançar todas no AdvWin", height=36,
                                         fg_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_HOVER,
                                         command=self._confirmar_lote)
        self.btn_lancar.pack(side="right")
        self.btn_fechar = ctk.CTkButton(barra, text="Fechar", height=36, fg_color="transparent",
                                         border_width=1, border_color=COR_PRIMARIA, text_color=COR_PRIMARIA,
                                         command=self._fechar)
        self.btn_fechar.pack(side="right", padx=8)
        self.btn_adicionar = ctk.CTkButton(barra, text="Adicionar planilha(s)", height=36,
                                            fg_color="transparent", border_width=1,
                                            border_color=COR_PRIMARIA, text_color=COR_PRIMARIA,
                                            command=self._adicionar_mais)
        self.btn_adicionar.pack(side="right", padx=(0, 8))
        self.btn_limpar = ctk.CTkButton(barra, text="Limpar lista", height=36,
                                         fg_color="transparent", border_width=1,
                                         border_color=COR_PRIMARIA, text_color=COR_PRIMARIA,
                                         command=self._limpar_lista)
        self.btn_limpar.pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self._adicionar_lotes(lotes)

        self.transient(master)
        self.lift()
        self.focus_force()

    def _construir_relogio_total(self, master) -> ctk.CTkFrame:
        """Total de horas marcadas, estilizado como o relógio digital da tela principal."""
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

    def _atualizar_titulo(self) -> None:
        self.label_titulo.configure(
            text=f"{len(self.linhas_preview)} linha(s) de {len(self.arquivos)} planilha(s) "
                 "- revise e edite antes de lançar"
        )

    def _adicionar_lotes(self, lotes: list[tuple[Path, list[retroativo.LinhaRetroativa]]]) -> None:
        for caminho, linhas in lotes:
            self.arquivos.append(caminho)
            for item in linhas:
                linha_widget = _LinhaPreview(self.scroll, caminho, item, self.pastas_favoritas, self.advogado_atual)
                linha_widget.pack(fill="x", pady=4)
                linha_widget.var_incluir.trace_add("write", lambda *_: self._recalcular_total())
                linha_widget.entry_horas.bind("<KeyRelease>", lambda _e: self._recalcular_total())
                self.linhas_preview.append(linha_widget)
        self._atualizar_titulo()
        self.label_resumo.configure(text="")
        self.btn_lancar.configure(text="Lançar todas no AdvWin", state="normal")
        self._recalcular_total()

    def _limpar_lista(self) -> None:
        if self._processando:
            messagebox.showwarning("Lançamento retroativo", "Aguarde o lote terminar antes de limpar a lista.")
            return
        if self.linhas_preview and not messagebox.askyesno(
            "Lançamento retroativo", "Isso vai remover todas as linhas carregadas da lista. Continuar?"
        ):
            return
        for lp in self.linhas_preview:
            lp.destroy()
        self.linhas_preview = []
        self.arquivos = []
        self._atualizar_titulo()
        self.label_resumo.configure(text="")
        self.btn_lancar.configure(text="Lançar todas no AdvWin", state="normal")
        self._recalcular_total()

    def _baixar_modelo(self) -> None:
        destino = filedialog.asksaveasfilename(
            parent=self, title="Salvar planilha modelo", defaultextension=".xlsx",
            initialfile="planilha_modelo_ficha_tempo.xlsx", filetypes=[("Planilha Excel", "*.xlsx")],
        )
        if not destino:
            return
        try:
            shutil.copy(planilha.CAMINHO_MODELO, destino)
        except OSError as e:  # ex.: destino aberto no Excel
            messagebox.showerror("Planilha modelo", f"Não foi possível salvar a planilha modelo:\n{e}")

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

    def _adicionar_mais(self) -> None:
        if self._processando:
            messagebox.showwarning("Lançamento retroativo", "Aguarde o lote terminar antes de adicionar planilha(s).")
            return
        lotes = selecionar_e_ler_varias(self)
        if not lotes:
            return
        self._adicionar_lotes(lotes)

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
        self.btn_adicionar.configure(state="disabled")
        self.btn_limpar.configure(state="disabled")
        self.btn_lancar.configure(state="disabled")
        for lp in incluidas:
            lp.marcar_status("⏳ na fila...", COR_TEXTO_SUAVE)
            item = lp.valores_editados()
            advwin.enfileirar(
                lambda item=item: advwin.lancar_horas(
                    advwin.pagina_advwin(), item.pasta, item.data, item.descricao, item.horas_texto,
                    self.area_atual, cobravel=False,
                ),
                lambda resultado, erro, lp=lp, item=item: self._apos_linha(lp, item, erro),
            )

    def _apos_linha(self, lp: _LinhaPreview, item: retroativo.LinhaRetroativa, erro: Exception | None) -> None:
        """Roda na thread de fundo da fila do AdvWin - só a atualização de widgets abaixo
        precisa passar por self.after(0, ...)."""
        if erro is None:
            marcado = self._marcar_linha_segura(
                lp.caminho, item, f"Lançado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            )
            try:
                horas = planilha.parse_horas_cobraveis(item.horas_texto) or timedelta()
                planilha.inserir_linha({
                    "data": datetime.strptime(item.data, "%d/%m/%Y").date(),
                    "advogado": item.advogado, "cliente": item.cliente, "pasta": item.pasta,
                    "descricao": item.descricao, "horas": horas, "horas_cobraveis": timedelta(),
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
                           "avise antes de reabrir esta planilha - senão duplica)", COR_PERIGO)
        else:
            mensagem = advwin.mensagem_amigavel(erro)
            self._marcar_linha_segura(lp.caminho, item, f"Erro: {mensagem}")
            self._erros += 1
            self.after(0, lp.marcar_status, f"✗ {mensagem}", COR_PERIGO)

        self.after(0, self.master._atualizar_botao_advwin)
        concluidos = self._ok + self._erros
        self.after(0, self._atualizar_resumo, concluidos)
        if concluidos == self._total:
            self.after(0, self._finalizar_lote)

    def _marcar_linha_segura(self, caminho: Path, item: retroativo.LinhaRetroativa, texto_status: str) -> bool:
        try:
            retroativo.marcar_linha(caminho, item.linha, texto_status)
            return True
        except Exception as e:
            print(f"[retroativo] não deu pra marcar a linha {item.linha} em {caminho}: {e!r}")
            return False

    def _atualizar_resumo(self, concluidos: int) -> None:
        self.label_resumo.configure(text=f"Lançando... {concluidos}/{self._total} ({self._erros} com erro)")
        self._recalcular_total()

    def _finalizar_lote(self) -> None:
        self._processando = False
        self.label_resumo.configure(text=f"Concluído: {self._ok} ok, {self._erros} com erro.")
        self.btn_adicionar.configure(state="normal")
        self.btn_limpar.configure(state="normal")
        if self._erros:
            self.btn_lancar.configure(text=f"Tentar novamente ({self._erros})", state="normal")
        else:
            self.btn_lancar.configure(text="Lote concluído", state="disabled")

        log = "\n".join(
            f"Linha {lp.item.linha} ({lp.caminho.name}) - {lp.cb_pasta.get().strip()}: {lp.label_status.cget('text')}"
            for lp in self._lote_atual
        )
        messagebox.showinfo(
            "Lançamento retroativo concluído",
            f"{self._ok} lançada(s) com sucesso, {self._erros} com erro.\n\n{log}",
        )
