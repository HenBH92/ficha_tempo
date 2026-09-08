"""Fila serial com contagem que inclui o processamento de retornos na interface."""
import logging
import queue
import threading

log = logging.getLogger(__name__)


class FilaTrabalho:
    def __init__(self):
        self._fila = queue.Queue()
        self._lock = threading.Lock()
        self._worker = None
        self._pendentes = 0
        self._bloqueada = False
        self.falha_retorno = False

    @property
    def ocupada(self):
        with self._lock:
            return self._pendentes > 0 or self.falha_retorno

    def bloquear_se_ociosa(self):
        with self._lock:
            if self._pendentes or self.falha_retorno or self._bloqueada:
                return False
            self._bloqueada = True
            return True

    def desbloquear(self):
        with self._lock:
            self._bloqueada = False

    def enfileirar(self, job, ao_concluir, despachar=None):
        with self._lock:
            if self._bloqueada:
                raise RuntimeError("O programa está preparando uma atualização. Aguarde.")
            self._adicionar(job, ao_concluir, despachar)

    def encerrar(self, job, ao_concluir, despachar):
        with self._lock:
            if not self._bloqueada or self._pendentes:
                raise RuntimeError("Há operações em andamento.")
            self._adicionar(job, ao_concluir, despachar)

    def _adicionar(self, job, ao_concluir, despachar):
        self._pendentes += 1
        self._fila.put((job, ao_concluir, despachar))
        if self._worker is None:
            self._worker = threading.Thread(target=self._processar, name="advwin-worker", daemon=True)
            self._worker.start()

    def _retornar(self, callback, resultado, erro):
        try:
            callback(resultado, erro)
        except Exception:
            self.falha_retorno = True
            log.exception("[advwin] ERRO no callback ao_concluir")
        finally:
            with self._lock:
                self._pendentes -= 1

    def _processar(self):
        while True:
            job, callback, despachar = self._fila.get()
            try:
                resultado, erro = job(), None
            except Exception as exc:
                log.exception("[advwin] ERRO")
                resultado, erro = None, exc
            # Os try/except separados são essenciais: um callback não pode matar o worker.
            if despachar is None:
                self._retornar(callback, resultado, erro)
            else:
                try:
                    despachar(lambda c=callback, r=resultado, e=erro: self._retornar(c, r, e))
                except Exception:
                    self.falha_retorno = True
                    with self._lock:
                        self._pendentes -= 1
                    log.exception("[advwin] Não foi possível entregar o retorno à interface")
            self._fila.task_done()
