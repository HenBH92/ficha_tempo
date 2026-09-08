import queue
import threading
import unittest


class FilaTest(unittest.TestCase):
    def nova_fila(self):
        from fila_trabalho import FilaTrabalho
        return FilaTrabalho()

    def test_trabalho_e_retorno_ui_impedem_bloqueio(self):
        fila = self.nova_fila()
        eventos = queue.Queue()
        iniciou = threading.Event()
        liberar = threading.Event()
        def job():
            iniciou.set()
            liberar.wait(2)
            return 42
        resultados = []
        fila.enfileirar(job, lambda resultado, erro: resultados.append(resultado), eventos.put)
        self.assertTrue(iniciou.wait(2))
        self.assertFalse(fila.bloquear_se_ociosa())
        liberar.set()
        retorno = eventos.get(timeout=2)
        self.assertFalse(fila.bloquear_se_ociosa())
        retorno()
        self.assertEqual(resultados, [42])
        self.assertTrue(fila.bloquear_se_ociosa())
        with self.assertRaises(RuntimeError):
            fila.enfileirar(lambda: None, lambda r, e: None)

    def test_worker_sobrevive_erro_de_job_e_callback(self):
        fila = self.nova_fila()
        concluido = threading.Event()
        def falha(*args):
            raise ValueError("simulado")
        fila.enfileirar(falha, falha)
        fila.enfileirar(lambda: 7, lambda r, e: concluido.set())
        self.assertTrue(concluido.wait(2))
        self.assertTrue(fila.falha_retorno)
        self.assertFalse(fila.bloquear_se_ociosa())

    def test_encerrar_roda_na_thread_do_worker(self):
        fila = self.nova_fila()
        terminou = threading.Event()
        ids = []
        fila.enfileirar(lambda: ids.append(threading.get_ident()), lambda r, e: terminou.set())
        self.assertTrue(terminou.wait(2))
        # Retorno pode estar concluindo seu finally: a fila de eventos resolve a ordenação.
        eventos = queue.Queue()
        fila.enfileirar(lambda: None, lambda r, e: None, eventos.put)
        eventos.get(timeout=2)()
        self.assertTrue(fila.bloquear_se_ociosa())
        fila.encerrar(lambda: ids.append(threading.get_ident()), lambda r, e: None, eventos.put)
        eventos.get(timeout=2)()
        self.assertEqual(ids[0], ids[1])

