"""Relato de problema/sugestão: janela no app e entrega feita pelo próprio app.

O destino é um formulário que só aceita escrita. O endereço dele não é segredo - quem
extrair do exe consegue, no máximo, mandar relato; não consegue ler os relatos dos outros.
É por isso que é um formulário, e não SMTP nem token do GitHub: esses dois viajariam como
credencial dentro do exe, e quem extraísse leria a caixa de entrada ou escreveria no
repositório. Também não depende de nenhum app instalado na máquina de quem relata.
"""
import json
import logging
import os
import platform
import threading
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from caminhos import VERSAO, informacoes_build, pasta_dados
from cores import COR_PRIMARIA, COR_PRIMARIA_HOVER, COR_TEXTO_SUAVE

log = logging.getLogger(__name__)

# PREENCHER: formulário do Google que recebe os relatos. A URL termina em /formResponse e os
# nomes dos campos saem do HTML do formulário (cada pergunta vira um "entry.<número>").
URL_FORMULARIO = ""
CAMPOS = {"tipo": "entry.0", "texto": "entry.0", "diagnostico": "entry.0"}

TEMPO_LIMITE_S = 20
TIPOS = ("Problema", "Sugestão")


def diagnostico_maquina() -> dict:
    """O que o app sabe sozinho. Vai junto pra não ter que perguntar versão e Windows depois."""
    info = informacoes_build()
    return {
        "quando": datetime.now().isoformat(timespec="seconds"),
        "versao": info.get("versao", VERSAO),
        "commit": info.get("commit", "?"),
        "usuario_windows": os.getenv("USERNAME", "?"),
        "windows": platform.platform(),
    }


def formatar(tipo: str, texto: str, diagnostico: dict) -> str:
    detalhes = "\n".join(f"{chave}: {valor}" for chave, valor in diagnostico.items())
    return f"[{tipo}]\n\n{texto.strip()}\n\n--- diagnóstico ---\n{detalhes}\n"


def enviar(tipo: str, texto: str, diagnostico: dict) -> None:
    """Entrega o relato. Levanta exceção se não conseguiu - quem chama guarda em disco."""
    if not URL_FORMULARIO:
        raise RuntimeError("O canal de relatos ainda não foi configurado nesta versão.")
    dados = urllib.parse.urlencode({
        CAMPOS["tipo"]: tipo,
        CAMPOS["texto"]: texto.strip(),
        CAMPOS["diagnostico"]: json.dumps(diagnostico, ensure_ascii=False, indent=2),
    }).encode()
    pedido = urllib.request.Request(URL_FORMULARIO, data=dados,
                                    headers={"User-Agent": f"FichaTempo/{VERSAO}"})
    with urllib.request.urlopen(pedido, timeout=TEMPO_LIMITE_S):
        pass


def salvar_local(tipo: str, texto: str, diagnostico: dict) -> Path:
    """Rede fora, proxy bloqueando ou formulário mudou: o relato fica em disco em vez de sumir."""
    pasta = pasta_dados() / "relatos"
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{datetime.now():%Y-%m-%d_%H%M%S}.txt"
    arquivo.write_text(formatar(tipo, texto, diagnostico), encoding="utf-8")
    return arquivo


class JanelaRelato(ctk.CTkToplevel):
    def __init__(self, master, contexto: dict | None = None):
        super().__init__(master)
        self.contexto = contexto or {}
        self._enviando = False
        self.title("Relatar problema ou sugestão")
        self.geometry("560x610")
        self.minsize(480, 540)
        self.transient(master)

        ctk.CTkLabel(self, text="O que aconteceu?",
                     font=ctk.CTkFont(size=18, weight="bold")).pack(padx=20, pady=(18, 2))
        ctk.CTkLabel(self, text="Quanto mais detalhe, mais rápido dá pra resolver.",
                     text_color=COR_TEXTO_SUAVE).pack(padx=20)

        self.seg_tipo = ctk.CTkSegmentedButton(self, values=list(TIPOS), selected_color=COR_PRIMARIA,
                                               selected_hover_color=COR_PRIMARIA_HOVER)
        self.seg_tipo.set(TIPOS[0])
        self.seg_tipo.pack(pady=12)

        self.texto = ctk.CTkTextbox(self, height=150, wrap="word")
        self.texto.pack(fill="both", expand=True, padx=20)

        ctk.CTkLabel(self, text="Enviado junto (só isto, nada da sua planilha):",
                     font=ctk.CTkFont(size=11), text_color=COR_TEXTO_SUAVE,
                     anchor="w").pack(fill="x", padx=20, pady=(10, 2))
        # Alto o bastante pra caber o diagnóstico inteiro sem rolar: quem relata tem que ver
        # exatamente o que está indo junto.
        detalhes = ctk.CTkTextbox(self, height=160, wrap="none", font=ctk.CTkFont(size=11))
        detalhes.pack(fill="x", padx=20)
        detalhes.insert("1.0", "\n".join(f"{c}: {v}" for c, v in self._diagnostico().items()))
        detalhes.configure(state="disabled")

        self.status = ctk.CTkLabel(self, text="", text_color=COR_TEXTO_SUAVE, wraplength=500)
        self.status.pack(padx=20, pady=(8, 0))

        botoes = ctk.CTkFrame(self, fg_color="transparent")
        botoes.pack(pady=(8, 16))
        self.btn_cancelar = ctk.CTkButton(botoes, text="Cancelar", width=110, fg_color="transparent",
                                          text_color=COR_TEXTO_SUAVE, command=self.destroy)
        self.btn_cancelar.pack(side="left", padx=5)
        self.btn_enviar = ctk.CTkButton(botoes, text="Enviar", width=190, fg_color=COR_PRIMARIA,
                                        hover_color=COR_PRIMARIA_HOVER, command=self._enviar)
        self.btn_enviar.pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.after(120, self.texto.focus_set)  # depois do transient, senão o foco volta pro app
        self.lift()

    def _diagnostico(self) -> dict:
        return {**diagnostico_maquina(), **self.contexto}

    def _fechar(self) -> None:
        if self._enviando:  # a thread ainda vai mexer nos widgets desta janela
            return
        self.destroy()

    def _enviar(self) -> None:
        texto = self.texto.get("1.0", "end").strip()
        if not texto:
            self.status.configure(text="Escreva o que aconteceu antes de enviar.")
            self.texto.focus_set()
            return
        tipo, diagnostico = self.seg_tipo.get(), self._diagnostico()
        self._enviando = True
        self.btn_enviar.configure(state="disabled", text="Enviando...")
        self.btn_cancelar.configure(state="disabled")
        self.status.configure(text="")

        def trabalho():
            try:
                enviar(tipo, texto, diagnostico)
                erro = None
            except Exception as exc:            # rede, proxy, formulário fora do ar
                log.exception("[relato] falha no envio")
                erro = exc
            self.after(0, lambda: self._concluir(tipo, texto, diagnostico, erro))

        threading.Thread(target=trabalho, name="relato", daemon=True).start()

    def _concluir(self, tipo: str, texto: str, diagnostico: dict, erro: Exception | None) -> None:
        self._enviando = False
        if not self.winfo_exists():
            return
        if erro is None:
            messagebox.showinfo("Obrigado!", "Relato enviado. Obrigado por avisar.", parent=self)
            self.destroy()
            return
        # Não dá pra perder o que a pessoa escreveu: guarda em disco e deixa na área de
        # transferência, pra ela conseguir mandar por outro caminho se quiser.
        try:
            arquivo = salvar_local(tipo, texto, diagnostico)
            onde = f"\n\nUma cópia ficou salva em:\n{arquivo}"
        except Exception:
            log.exception("[relato] falha ao salvar em disco")
            onde = ""
        self.clipboard_clear()
        self.clipboard_append(formatar(tipo, texto, diagnostico))
        messagebox.showwarning(
            "Não deu para enviar agora",
            f"{erro}\n\nO texto do relato foi copiado para a área de transferência.{onde}",
            parent=self)
        self.btn_enviar.configure(state="normal", text="Tentar de novo")
        self.btn_cancelar.configure(state="normal")


def _demo():
    diagnostico = diagnostico_maquina()
    assert {"versao", "commit", "windows", "usuario_windows", "quando"} <= set(diagnostico)

    texto = formatar("Problema", "  o botão sumiu  ", {"versao": "1.0.0"})
    assert "[Problema]" in texto and "o botão sumiu" in texto and "versao: 1.0.0" in texto

    # Sem formulário configurado o envio falha em vez de fingir que deu certo - é o que faz
    # a janela cair no salvamento em disco.
    assert not URL_FORMULARIO, "formulário configurado: ajuste este check"
    try:
        enviar("Problema", "teste", diagnostico)
    except RuntimeError:
        pass
    else:
        raise AssertionError("enviar() deveria falhar sem URL_FORMULARIO")

    arquivo = salvar_local("Sugestão", "podia ter atalho", diagnostico)
    assert arquivo.exists() and "podia ter atalho" in arquivo.read_text(encoding="utf-8")
    assert arquivo.parent.name == "relatos"
    arquivo.unlink()
    print("relatos.py OK")


if __name__ == "__main__":
    _demo()
