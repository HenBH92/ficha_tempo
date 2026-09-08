"""Coordena a passagem da interface ao instalador sem interromper trabalho."""


class ReinicioSeguro:
    def __init__(self, app, advwin):
        self.app = app
        self.advwin = advwin

    def iniciar(self, ao_pronto, ao_erro):
        if self.app._encerrando:
            raise RuntimeError("O programa já está preparando o encerramento.")
        if self.app.tem_previa_aberta():
            raise RuntimeError("Feche a prévia do lançamento retroativo antes de instalar a atualização.")
        if not self.advwin.bloquear_para_atualizacao():
            raise RuntimeError("Aguarde a conclusão das operações e dos resultados do AdvWin antes de atualizar.")
        self.app._encerrando = True
        anteriores = []
        try:
            for card in self.app.cards:
                timer = card.timer
                anteriores.append((timer, timer.status, timer.acumulado_s, timer.segmento_inicio))
                if timer.status == "rodando":
                    timer.pausar()
            # Coleta os campos sem recalcular/sobrescrever as horas digitadas manualmente.
            self.app.salvar(retomada_atualizacao=True)
        except Exception:
            for timer, status, acumulado, inicio in anteriores:
                timer.status, timer.acumulado_s, timer.segmento_inicio = status, acumulado, inicio
            self.cancelar()
            raise

        def encerrado(resultado, erro):
            if erro is not None:
                self.cancelar()
                ao_erro(erro)
                return
            ao_pronto()
        try:
            self.advwin.encerrar_sessao(encerrado, self.app.agendar_ui)
        except Exception:
            self.cancelar()
            raise

    def cancelar(self):
        self.advwin.cancelar_encerramento()
        self.app._encerrando = False

