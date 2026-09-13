"""Avisos de atualização; trabalho de rede nunca executa na thread do Tkinter."""
import logging
import threading
from tkinter import messagebox

import customtkinter as ctk

from atualizador import INTERVALO_MS, ServicoAtualizacao, mensagem_amigavel
from caminhos import VERSAO
from cores import COR_PRIMARIA
from reinicio import ReinicioSeguro

log = logging.getLogger(__name__)


class ControladorAtualizacao:
    def __init__(self, app, advwin, servico=None):
        self.app = app
        self.servico = servico or ServicoAtualizacao()
        self.reinicio = ReinicioSeguro(app, advwin)
        self.ocupado = False
        self.janela = None
        self.nova = None
        self._timer = app.after(2500, self._periodico)

    def _periodico(self):
        self._timer = self.app.after(INTERVALO_MS, self._periodico)
        self.verificar()

    def parar(self):
        self.app.after_cancel(self._timer)

    def _executar(self, trabalho, sucesso, erro):
        self.ocupado = True
        def worker():
            try:
                resultado = trabalho()
            except Exception as exc:
                log.exception("Falha na operação de atualização")
                self.app.agendar_ui(lambda e=exc: finalizar(erro, e))
            else:
                self.app.agendar_ui(lambda r=resultado: finalizar(sucesso, r))
        def finalizar(callback, resultado):
            self.ocupado = False
            callback(resultado)
        threading.Thread(target=worker, name="atualizador", daemon=True).start()

    def verificar(self, manual=False):
        if self.app._encerrando:
            return
        if self.ocupado:
            if manual:
                messagebox.showinfo("Atualizações", "Uma verificação ou download já está em andamento.", parent=self.app)
            return
        if self.janela is not None and self.janela.winfo_exists():
            if manual:
                self.janela.deiconify()
                self.janela.lift()
            return
        def pronto(nova):
            if self.app._encerrando:
                return
            if nova is not None:
                self.nova = nova
                self._mostrar()
            elif manual:
                messagebox.showinfo("Atualizações", f"Você está usando a versão mais recente disponível ({VERSAO}).", parent=self.app)
        def falhou(exc):
            if manual:
                messagebox.showwarning("Atualizações", mensagem_amigavel(exc), parent=self.app)
        self._executar(lambda: self.servico.verificar(manual=manual), pronto, falhou)

    def _mostrar(self):
        if self.janela is not None and self.janela.winfo_exists():
            self.janela.destroy()
        janela = self.janela = ctk.CTkToplevel(self.app)
        janela.title("Atualização disponível")
        janela.geometry("590x390")
        janela.minsize(540, 360)
        janela.transient(self.app)
        janela.protocol("WM_DELETE_WINDOW", self._depois)
        ctk.CTkLabel(janela, text=f"Nova versão {self.nova.versao}",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(padx=20, pady=(18, 4))
        ctk.CTkLabel(janela, text=f"Versão atual: {VERSAO}").pack()
        notas = ctk.CTkTextbox(janela, height=155, wrap="word")
        notas.pack(fill="both", expand=True, padx=20, pady=12)
        notas.insert("1.0", self.nova.notas)
        notas.configure(state="disabled")
        self.status = ctk.CTkLabel(janela, text="Você decide quando atualizar.", wraplength=540)
        self.status.pack(padx=20)
        self.progresso = ctk.CTkProgressBar(janela)
        self.progresso.set(0)
        self.progresso.pack(fill="x", padx=20, pady=8)
        botoes = ctk.CTkFrame(janela, fg_color="transparent")
        botoes.pack(padx=15, pady=(4, 16))
        self.btn_ignorar = ctk.CTkButton(botoes, text="Ignorar esta versão", width=150, command=self._ignorar)
        self.btn_ignorar.pack(side="left", padx=4)
        self.btn_depois = ctk.CTkButton(botoes, text="Depois", width=95, command=self._depois)
        self.btn_depois.pack(side="left", padx=4)
        self.btn_acao = ctk.CTkButton(botoes, text="Atualizar", width=190, fg_color=COR_PRIMARIA, command=self._baixar)
        self.btn_acao.pack(side="left", padx=4)
        if self.nova.baixada:
            self._pronta()
        janela.lift()

    def _depois(self):
        if self.app._encerrando:
            return
        if self.janela is not None:
            if self.ocupado:
                self.janela.withdraw()
            else:
                self.janela.destroy()
                self.janela = None

    def _ignorar(self):
        try:
            self.servico.ignorar(self.nova.versao)
        except OSError:
            log.exception("Não foi possível salvar a preferência")
            messagebox.showerror("Atualizações", "Não foi possível salvar sua preferência. Tente novamente.", parent=self.janela)
            return
        self._depois()

    def _baixar(self):
        if self.ocupado:
            return
        self.btn_acao.configure(state="disabled")
        self.btn_ignorar.configure(state="disabled")
        self.status.configure(text="Baixando atualização… Você pode continuar trabalhando.")
        def progresso(valor):
            self.app.agendar_ui(lambda v=valor: self.progresso.set(max(0, min(100, v)) / 100))
        def falhou(exc):
            self.janela.deiconify()
            self.btn_acao.configure(state="normal", text="Tentar novamente")
            self.btn_ignorar.configure(state="normal")
            self.status.configure(text="O download falhou. Confira sua conexão e tente novamente.")
        self._executar(lambda: self.servico.baixar(self.nova, progresso), lambda _: self._pronta(), falhou)

    def _pronta(self):
        self.janela.deiconify()
        self.progresso.set(1)
        self.status.configure(text="Download concluído. Ao reiniciar, seus cronômetros serão salvos e ficarão pausados.")
        self.btn_acao.configure(state="normal", text="Instalar e reiniciar", command=self._instalar)
        self.btn_ignorar.configure(state="normal")

    def _instalar(self):
        if self.ocupado or self.app._encerrando:
            return
        def erro(exc):
            log.error("Reinício cancelado: %s", exc)
            self.reinicio.cancelar()
            self.app.attributes("-disabled", False)
            self.btn_acao.configure(state="normal")
            self.btn_depois.configure(state="normal")
            self.btn_ignorar.configure(state="normal")
            self.status.configure(text="Não foi possível preparar a instalação. Seus dados foram mantidos; tente novamente.")
            messagebox.showerror("Atualizações", str(exc), parent=self.janela)
        def encerrar(_):
            self.parar()
            self.app.destroy()
        def pronto():
            self.status.configure(text="Preparando a instalação…")
            self._executar(lambda: self.servico.preparar_instalacao(self.nova), encerrar, erro)
        try:
            self.reinicio.iniciar(pronto, erro)
        except Exception as exc:
            messagebox.showwarning("Atualizações", str(exc), parent=self.janela)
            return
        self.app.attributes("-disabled", True)
        self.btn_acao.configure(state="disabled")
        self.btn_depois.configure(state="disabled")
        self.btn_ignorar.configure(state="disabled")
        self.status.configure(text="Salvando e encerrando a sessão do AdvWin…")

