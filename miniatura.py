"""Miniatura sempre visível do card ativo enquanto o app está minimizado: pausar/retomar
sem reabrir a janela principal."""
import ctypes
from ctypes import wintypes

import customtkinter as ctk

import icones
from cores import COR_BORDA_CARD, COR_PRIMARIA, COR_PRIMARIA_CLARA, COR_PRIMARIA_HOVER, COR_TEXTO_SUAVE
from widgets import _janela_flutuante

MARGEM = 12
BORDA = 8  # faixa (px) junto das bordas que redimensiona em vez de mover
# Abaixo de 0.8 o CTk deixa de desenhar a borda de 1px do botão "Abrir" (medido a 125% de DPI).
ESCALA_MIN, ESCALA_MAX = 0.8, 2.5
_SPI_GETWORKAREA = 0x0030
_SW_RESTORE = 9
_CURSORES = {"n": "size_ns", "s": "size_ns", "e": "size_we", "w": "size_we",
             "nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw", "": ""}


def _cortar(texto: str, limite: int) -> str:
    texto = texto.strip()
    return texto if len(texto) <= limite else texto[:limite - 1] + "…"


def _area_trabalho() -> wintypes.RECT:
    """Área de trabalho do monitor principal (sem a barra de tarefas), em pixels físicos. Não usar
    winfo_screenwidth(): o Tk guarda o tamanho de antes do CTk ligar o DPI por monitor (medido:
    1536 numa tela de 1920 a 125%), enquanto a posição das janelas é física."""
    area = wintypes.RECT()
    ctypes.windll.user32.SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(area), 0)
    return area


def limitar_escala(escala: float) -> float:
    """Passos de 5%: cada tamanho distinto vira uma imagem nova no cache do CTkImage."""
    return min(max(round(escala * 20) / 20, ESCALA_MIN), ESCALA_MAX)


class JanelaMiniatura:
    def __init__(self, app):
        self.app = app
        self.card = None
        self.escala = limitar_escala(app.escala_miniatura)
        self._status = None
        self._arrastada = False
        self._redimensionou = False
        self._zona = ""
        self._inicio = (0, 0, 0, 0, 1, 1, 1.0)
        # Sem moldura de propósito: no Windows o deiconify() de janela com moldura rouba o foco,
        # e quem minimizou pra digitar em outro programa perderia o que digita. Também não ganha
        # botão na barra de tarefas. Sem transient(): janela "owned" some junto com o app minimizado.
        # Sem moldura também não há borda nativa: mover e redimensionar são feitos à mão abaixo.
        self.janela = _janela_flutuante(app)
        self.janela.attributes("-topmost", True)
        # A bindtag da janela vale pros filhos: arrasta/redimensiona a partir de qualquer ponto.
        self.janela.bind("<Motion>", self._ao_mover_mouse)
        self.janela.bind("<ButtonPress-1>", self._ao_pressionar)
        self.janela.bind("<B1-Motion>", self._ao_arrastar)
        self.janela.bind("<ButtonRelease-1>", self._ao_soltar)
        # Com o foco aqui, o bind_all do app cairia no cards[0] (_card_com_foco), não neste card.
        self.janela.bind("<Control-space>", lambda e: (self._alternar(), "break")[1])

        # Desenhados grandes e exibidos em 18px: o CTkImage só reduz, então seguem nítidos ampliados.
        self._icones = {nome: ctk.CTkImage(light_image=icones.icone(nome, 64, "white").cget("light_image"),
                                           size=(18, 18)) for nome in ("play", "pause")}

        self.fundo = ctk.CTkFrame(self.janela, corner_radius=0, border_width=1, border_color=COR_BORDA_CARD)
        self.fundo.pack(fill="both", expand=True)
        self.label_pasta = ctk.CTkLabel(self.fundo, text="", anchor="w", height=20,
                                        font=ctk.CTkFont(size=13, weight="bold"))
        self.label_pasta.pack(fill="x", padx=12, pady=(8, 0))
        self.label_descricao = ctk.CTkLabel(self.fundo, text="", anchor="w", height=16,
                                            font=ctk.CTkFont(size=11), text_color=COR_TEXTO_SUAVE)
        self.label_descricao.pack(fill="x", padx=12)
        linha = ctk.CTkFrame(self.fundo, fg_color="transparent")
        linha.pack(fill="x", padx=12, pady=(2, 10))
        self.label_tempo = ctk.CTkLabel(linha, text="", font=ctk.CTkFont(size=22, weight="bold"),
                                        text_color=COR_PRIMARIA)
        self.label_tempo.pack(side="left", padx=(0, 12))
        ctk.CTkButton(linha, text="Abrir", width=56, height=28, fg_color="transparent", border_width=1,
                      border_color=COR_PRIMARIA, text_color=COR_PRIMARIA, hover_color=COR_PRIMARIA_CLARA,
                      command=self._abrir_app).pack(side="right", padx=(4, 0))
        self.btn_play_pause = ctk.CTkButton(linha, text="", width=32, height=28, fg_color=COR_PRIMARIA,
                                            hover_color=COR_PRIMARIA_HOVER, command=self._alternar)
        self.btn_play_pause.pack(side="right")

    def mostrar(self, card) -> None:
        self.card = card
        self._status = None  # força redesenhar ícone e cor no atualizar()
        self.label_pasta.configure(text=_cortar(card.cb_pasta.get() or "(sem pasta)", 32))
        self.label_descricao.configure(text=_cortar(card.entry_descricao.get(), 40))
        self.atualizar()
        self._aplicar_escala()
        if not self._arrastada:  # depois de arrastada, fica onde a pessoa deixou
            self._posicionar()
        self.janela.deiconify()
        self.janela.lift()

    def esconder(self) -> None:
        self.janela.withdraw()

    def visivel(self) -> bool:
        return self.janela.state() == "normal"

    def atualizar(self) -> None:
        """Chamado pelo _tick do app a cada segundo enquanto a miniatura está visível."""
        timer = self.card.timer
        self.label_tempo.configure(text=timer.elapso_fmt())
        if timer.status != self._status:
            self._status = timer.status
            self.btn_play_pause.configure(image=self._icones["pause" if timer.status == "rodando" else "play"])
            self.fundo.configure(fg_color=self.card.cget("fg_color"))  # verde rodando, bege pausado

    def _alternar(self) -> None:
        # Mesmo caminho do botão/atalho do card: trava de card lançado, horas ao pausar, salvar().
        self.card.alternar_iniciar_pausar()
        self.atualizar()

    def _abrir_app(self) -> None:
        # SW_RESTORE, igual ao clique na barra de tarefas: volta maximizada se estava (o deiconify()
        # do Tk volta sempre ao tamanho normal). O <Map> da janela principal esconde a miniatura.
        ctypes.windll.user32.ShowWindow(wintypes.HWND(int(self.app.wm_frame(), 16)), _SW_RESTORE)

    def _aplicar_escala(self) -> None:
        """Escala da miniatura por cima da de DPI, pelo mesmo caminho que o CTk usa ao trocar de
        monitor: cada widget refaz fonte, tamanho e espaçamentos, e a janela acompanha."""
        # ponytail: arrastada pra um monitor com outro DPI, o ScalingTracker reaplica só o DPI e ela
        # volta a 1x até aparecer de novo; reaplicar num gancho do tracker se isso incomodar.
        rastreador = ctk.ScalingTracker
        dpi = rastreador.window_dpi_scaling_dict[self.janela]
        for callback in rastreador.window_widgets_dict[self.janela]:
            callback(dpi * rastreador.widget_scaling * self.escala, dpi * rastreador.window_scaling * self.escala)

    def _posicionar(self) -> None:
        """Canto inferior direito da área de trabalho, acima da barra de tarefas."""
        self.janela.update_idletasks()  # tamanho pedido já com o texto e a escala atuais
        area = _area_trabalho()
        self.janela.geometry(f"+{area.right - self.janela.winfo_reqwidth() - MARGEM}"
                             f"+{area.bottom - self.janela.winfo_reqheight() - MARGEM}")

    def _zona_em(self, event) -> str:
        """Borda/canto sob o ponteiro ("n", "se", ...) ou "" no meio da janela."""
        x = event.x_root - self.janela.winfo_rootx()
        y = event.y_root - self.janela.winfo_rooty()
        largura, altura = self.janela.winfo_width(), self.janela.winfo_height()
        return (("n" if y < BORDA else "s" if y >= altura - BORDA else "")
                + ("w" if x < BORDA else "e" if x >= largura - BORDA else ""))

    def _ao_mover_mouse(self, event) -> None:
        cursor = _CURSORES[self._zona_em(event)]
        if self.janela.cget("cursor") != cursor:
            self.janela.configure(cursor=cursor)  # filhos com cursor "" herdam o da janela

    def _ao_pressionar(self, event) -> None:
        self._zona = self._zona_em(event)
        self._inicio = (event.x_root, event.y_root, self.janela.winfo_x(), self.janela.winfo_y(),
                        self.janela.winfo_width(), self.janela.winfo_height(), self.escala)

    def _ao_arrastar(self, event) -> None:
        x0, y0, esq, topo, largura, altura, escala0 = self._inicio
        dx, dy = event.x_root - x0, event.y_root - y0
        if not self._zona:  # meio da janela: move
            self._arrastada = True
            self.janela.geometry(f"+{esq + dx}+{topo + dy}")
            return
        # O conteúdo cresce junto, então a janela mantém a proporção: num canto, vale o eixo
        # puxado com mais força.
        fatores = []
        if "e" in self._zona:
            fatores.append((largura + dx) / largura)
        if "w" in self._zona:
            fatores.append((largura - dx) / largura)
        if "s" in self._zona:
            fatores.append((altura + dy) / altura)
        if "n" in self._zona:
            fatores.append((altura - dy) / altura)
        escala = limitar_escala(escala0 * max(fatores, key=lambda f: abs(f - 1)))
        if escala == self.escala:
            return
        self.escala = escala
        self._redimensionou = True
        self._aplicar_escala()
        self.janela.update_idletasks()
        nova_largura, nova_altura = self.janela.winfo_reqwidth(), self.janela.winfo_reqheight()
        # O lado oposto ao puxado fica parado, como numa janela comum - sem sair da área de trabalho.
        x = esq + largura - nova_largura if "w" in self._zona else esq
        y = topo + altura - nova_altura if "n" in self._zona else topo
        area = _area_trabalho()
        x = max(area.left, min(x, area.right - nova_largura))
        y = max(area.top, min(y, area.bottom - nova_altura))
        self.janela.geometry(f"+{x}+{y}")

    def _ao_soltar(self, event) -> None:
        if self._redimensionou:  # salva uma vez por arrasto, não a cada passo
            self._redimensionou = False
            self.app.escala_miniatura = self.escala
            self.app.salvar()
