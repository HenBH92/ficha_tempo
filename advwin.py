"""Sessão do AdvWin controlada pelo Playwright, num perfil de Chrome próprio da automação
(separado do perfil que o usuário já usa no dia a dia). Login é sempre manual - nenhuma
credencial é lida, recebida ou guardada aqui.

Mesmo padrão do projeto irmão atualizador_advwin (core/advwin-actions.ts): perfil Chrome
persistente, login manual só na primeira vez (a sessão fica salva em disco e sobrevive
entre execuções - da segunda vez em diante já abre autenticado). Trade-off aceito: como
o AdvWin invalida outras sessões ao logar de novo, isso pode deslogar o outro perfil do
Chrome que o usuário já está usando. A alternativa (anexar via --remote-debugging-port
no navegador que o usuário já tem aberto) exigiria configurar com antecedência o jeito
como o navegador é aberto em cada computador do escritório, o que não é viável.
"""
import re
from fila_trabalho import FilaTrabalho

from caminhos import pasta_dados

URL_DASHBOARD = "https://vlf.twtinfo.com.br/dashboard"
URLS_AREA = {
    "Trabalhista": "https://vlf.twtinfo.com.br/pasta/index/0/4",
    "Contencioso": "https://vlf.twtinfo.com.br/pasta/index/0/1",
}
PERFIL_CHROME = pasta_dados() / "advwin-chrome-profile"

_playwright = None
_contexto = None
_autenticado = False


def _esquecer_sessao() -> None:
    global _contexto, _autenticado
    _contexto, _autenticado = None, False


def _pagina_ativa():
    """Devolve a página da sessão, confirmando que o Chrome ainda responde.

    `_contexto.pages` e `pagina.is_closed()` vêm de um cache do cliente do Playwright e
    continuam dizendo que está tudo vivo depois que o usuário fecha a janela (medido:
    `pages` seguia com 1 aba e `is_closed()` com False, com o Chrome já morto). Só uma
    chamada que conversa de verdade com o browser levanta TargetClosedError - por isso o
    title(), que é quem decide se a sessão ainda existe.
    """
    pagina = _contexto.pages[0] if _contexto.pages else _contexto.new_page()
    pagina.title()
    return pagina


def pagina_advwin():
    """Abre (ou reaproveita) a sessão do AdvWin já autenticada.

    Bloqueia até o login manual terminar, se ainda não estiver logado - por isso deve ser
    chamada numa thread separada da UI (nunca direto no thread principal do Tkinter).
    """
    global _playwright, _contexto, _autenticado
    if _contexto is not None:
        try:
            pagina = _pagina_ativa()
        except Exception:
            # Sessão "morta" (ex.: usuário fechou a janela do Chrome da automação) - sem
            # isso, reconectar reaproveitava a mesma sessão inválida e falhava de novo
            # silenciosamente, mesmo depois do usuário clicar em "Conectar AdvWin".
            print("[advwin] sessão anterior não está mais disponível - reconectando...")
            _esquecer_sessao()

    if _contexto is None:
        print("[advwin] abrindo Chrome (perfil de automação)...")
        from playwright.sync_api import sync_playwright

        if _playwright is None:
            # Fechar a janela mata só o Chrome; o driver do Playwright continua de pé.
            # Reaproveitá-lo evita deixar um processo node órfão a cada reconexão.
            _playwright = sync_playwright().start()
        # chromium_sandbox tem default False na API do Playwright (ao contrário do que o
        # nome sugere) - sem isso o Chrome roda com --no-sandbox e mostra o aviso "sinalizador
        # de linha de comando não suportado". Liga de volta o sandbox de verdade.
        _contexto = _playwright.chromium.launch_persistent_context(
            str(PERFIL_CHROME),
            channel="chrome",
            headless=False,
            chromium_sandbox=True,
            args=["--start-maximized"],
            no_viewport=True,
        )
        pagina = _contexto.pages[0] if _contexto.pages else _contexto.new_page()

    if _autenticado:
        # Já confirmamos a sessão nesta execução - não repete o goto(dashboard) a cada
        # card do "Lançar todas". Achado ao vivo: o /dashboard do AdvWin redireciona
        # sozinho (JS) pra /agenda depois de carregar, e repetir esse goto pra cada card
        # da fila corre risco de colidir com esse redirecionamento em andamento
        # ("Navigation... interrupted by another navigation to .../agenda").
        return pagina

    print(f"[advwin] indo para {URL_DASHBOARD}")
    pagina.goto(URL_DASHBOARD)
    # Mesmo padrão de core/playwright-adapter.ts (waitForAuthenticated): a sessão
    # persistente pode já estar autenticada (goto acima não gera navegação nenhuma
    # depois) - sem essa checagem de URL atual, wait_for_url ficaria esperando pra
    # sempre uma navegação que já aconteceu. Não usa elemento de menu (ex.: link
    # "Trabalhista") porque esse fica escondido atrás de hover, não é um sinal confiável.
    if not pagina.url.startswith(URL_DASHBOARD):
        print(f"[advwin] não autenticado ainda (url atual: {pagina.url}) - aguardando login manual...")
        pagina.wait_for_url(lambda url: url.startswith(URL_DASHBOARD), timeout=0)
    print("[advwin] sessão autenticada")
    _autenticado = True
    return pagina


def esta_conectado() -> bool:
    """Último estado conhecido da sessão - pode ser lido de qualquer thread (só olha os
    globais, não fala com o Playwright)."""
    return _autenticado and _contexto is not None


def verificar_sessao() -> bool:
    """Confere se a janela do Chrome continua aberta e devolve o estado real da conexão.

    Precisa ir pela fila (`enfileirar`), nunca direto da interface: a API síncrona do
    Playwright só pode ser usada na thread que criou a sessão. Sem essa checagem, fechar
    a janela na mão deixava o botão "Conectado" até a próxima tentativa de uso falhar -
    o evento `context.on("close")` não serve para isso porque não chega a ser entregue
    enquanto a fila está ociosa (medido)."""
    if _contexto is not None:
        try:
            _pagina_ativa()
        except Exception:
            print("[advwin] janela do Chrome foi fechada - sessão encerrada")
            _esquecer_sessao()
    return esta_conectado()


def _esperar_rede_ociosa(pagina) -> None:
    """Mesma lição de core/advwin-actions.ts (findProcessInListing): a página termina o
    "load" antes do Angular acabar de inicializar - preencher/clicar antes disso vira
    no-op silencioso. A listagem tem chamadas de fundo que às vezes nunca deixam a rede
    ficar ociosa por 500ms, então isso é só uma tentativa (não trava se não conseguir)."""
    try:
        pagina.wait_for_load_state("networkidle")
    except Exception:
        pass


def _preencher_data(campo, data_ddmmaaaa: str) -> None:
    """Mesma técnica usada no atualizador_advwin (playwright-adapter.ts) para campos de
    data do AdvWin: o campo usa jquery.mask + Bootstrap Datetimepicker, que ignora
    .fill() (que seta o valor via JS) e só reformata certo com eventos de tecla reais,
    um a um, com atraso entre eles - por isso apaga tudo e digita só os dígitos."""
    digitos = re.sub(r"\D", "", data_ddmmaaaa)
    campo.click()
    campo.press("Control+A")
    campo.press("Delete")
    campo.press_sequentially(digitos, delay=40)
    campo.blur()


def _numero_encontrados(pagina) -> str | None:
    """Lê o contador "Encontrados: N" da listagem - usado só pra saber se a busca já
    atualizou a grade (não é a fonte de verdade da contagem final, só um sinal de mudança)."""
    return pagina.evaluate(
        "() => { const m = document.body.innerText.match(/Encontrados:\\s*(\\d+)/); return m ? m[1] : null; }"
    )


def _hhmm(texto: str) -> str:
    """"h:mm" (formato usado no card, ex.: "1:05" ou "0:15") -> "HH:MM" com hora em 2
    dígitos, exigido pelos campos <input type="time"> nativos do AdvWin (TempoSimplificado
    e Tempo) - confirmado ao vivo via DevTools que .fill() só funciona nesse formato."""
    horas, minutos = texto.strip().split(":", 1)
    return f"{int(horas):02d}:{int(minutos):02d}"


def _garantir_coluna_acoes_visivel(pagina) -> None:
    """A coluna "Ações" (onde fica o link Ficha-Tempo) é ocultável - preferência de grade
    salva por usuário no AdvWin (grid DevExtreme). Confirmado ao vivo via Chrome DevTools
    MCP: quando oculta, o link "Ficha-Tempo" nem existe no DOM (não é só invisível), então
    a busca abaixo falharia com "Nenhuma pasta encontrada" mesmo a pasta existindo.
    #idBtnHideActions é o botão de alternância dessa coluna especificamente - seu `title`
    alterna entre "Ocultar Coluna Ações" (já visível) e "Exibir Coluna Ações" (oculta)."""
    botao = pagina.locator("#idBtnHideActions")
    if botao.count() and "exibir" in (botao.get_attribute("title") or "").lower():
        print('[advwin] coluna "Ações" estava oculta - reabrindo...')
        botao.click()
        _esperar_rede_ociosa(pagina)


def lancar_horas(pagina, pasta: str, data: str, descricao: str, horas_texto: str,
                  area: str = "Trabalhista") -> None:
    """Busca a pasta pelo código e lança um registro na aba "Ficha-Tempo".

    `pagina` deve vir de pagina_advwin() (sessão já autenticada). `data` no formato
    dd/mm/aaaa, `horas_texto` no formato h:mm - mesmos formatos já usados no card.
    `area` seleciona a listagem de pastas onde buscar ("Trabalhista" ou "Contencioso" -
    ver URLS_AREA), já que o código da pasta só é único dentro de cada área.
    Preenche tanto "Horas" (TempoSimplificado) quanto "Horas Cobráveis" (Tempo) com o
    mesmo valor (horas cobráveis do card) - decisão confirmada com o usuário.
    Sequência confirmada ao vivo via Chrome DevTools MCP contra o DOM real autenticado.
    """
    print(f'[advwin] buscando pasta "{pasta}" (área={area}, data={data}, horas={horas_texto})')
    pagina.goto(URLS_AREA[area])
    _esperar_rede_ociosa(pagina)

    pagina.locator("#campoTemplate").select_option("Codigo_Comp")
    pagina.locator("#operadorTemplate").select_option("igual")
    pagina.locator("#pesquisaTemplate").fill(pasta)
    pagina.locator("#btnPesquisaTemplate").click()
    _esperar_rede_ociosa(pagina)
    # Achado ao vivo: o contador "Encontrados" e as linhas da grade (com os links de
    # Ficha-Tempo) não atualizam no mesmo instante - o contador já mostrava o valor novo
    # enquanto a grade ainda tinha as linhas da busca/visualização anterior (mesma lição
    # de core/advwin-actions.ts: Angular termina de re-renderizar depois do "load"/idle).
    # Por isso a espera é pela própria célula com o código da pasta aparecendo - evidência
    # direta de que a linha certa já renderizou, não um contador que pode ter mudado antes
    # da grade acompanhar.
    try:
        pagina.get_by_role("gridcell", name=pasta, exact=True).wait_for(timeout=15000)
    except Exception:
        pass

    _garantir_coluna_acoes_visivel(pagina)

    # Mesma trava de segurança de core/advwin-actions.ts (findProcessInListing): zero ou
    # mais de um resultado aborta sem clicar em nada, em vez de arriscar lançar a hora na
    # pasta errada (defesa extra mesmo com operador "igual").
    # ponytail: a contagem é da página inteira, não só da linha da pasta - linhas de uma
    # busca anterior que ainda não sumiram do DOM podem inflar esse total e abortar um
    # lançamento válido (falso positivo, força tentar de novo). Já foi tentado escopar por
    # linha (role="row") - travava até estourar timeout. Reinspecionado ao vivo (2026-08-28):
    # o link ESTÁ dentro de um <tr class="dx-row dx-data-row..."> real no DOM - a suposição
    # anterior de que não ficava aninhado na linha estava errada. O locator role="row"
    # provavelmente não bate por causa de como o DevExtreme monta a tabela (o role ARIA
    # implícito do <tr> pode não ser computado do jeito que o Playwright espera); escopar
    # por seletor CSS (ex. "tr.dx-data-row") em vez de role="row" é o próximo caminho a
    # tentar - não feito agora por estar fora do escopo desta mudança.
    links_ficha_tempo = pagina.get_by_role("link", description="Ficha-Tempo", exact=True)
    total = links_ficha_tempo.count()
    print(f"[advwin] {total} resultado(s) de busca (encontrados: {_numero_encontrados(pagina)})")
    if total == 0:
        raise RuntimeError(f'Nenhuma pasta encontrada para "{pasta}" no AdvWin.')
    if total > 1:
        raise RuntimeError(f'{total} pastas encontradas para "{pasta}" no AdvWin - confira o código da pasta.')
    links_ficha_tempo.click()
    print("[advwin] pasta aberta, preenchendo ficha-tempo...")

    quadro = pagina.locator("#iframeBox").content_frame

    campo_data = quadro.locator('[data-test="Data"]')
    _preencher_data(campo_data, data)
    tentativas = 0
    while campo_data.input_value().strip() != data.strip() and tentativas < 2:
        pagina.wait_for_timeout(250)
        _preencher_data(campo_data, data)
        tentativas += 1
    if campo_data.input_value().strip() != data.strip():
        raise RuntimeError(f'Campo "Data" não ficou com o valor esperado ({data}) - confira manualmente no AdvWin.')
    print("[advwin] data preenchida")

    quadro.locator('[data-test="Obs "]').fill(descricao)
    hhmm = _hhmm(horas_texto)
    quadro.locator('[data-test="TempoSimplificado"]').fill(hhmm)
    quadro.locator('[data-test="Tempo"]').fill(hhmm)
    print("[advwin] descrição e horas preenchidas, salvando...")
    quadro.locator('[data-test="button-salvar-e-fechar"]').click()
    print("[advwin] salvar e fechar clicado")


def mensagem_amigavel(erro: Exception) -> str:
    """Traduz erros comuns (sessão fechada, timeout, rede) pra uma mensagem que ajuda o
    usuário a agir, em vez da exceção crua do Playwright. Erros já lançados como
    RuntimeError por lancar_horas() (pasta não encontrada etc.) já são amigáveis e passam
    direto."""
    texto = str(erro)
    baixo = texto.lower()
    if "target page, context or browser has been closed" in baixo or "target closed" in baixo:
        return ('A sessão do AdvWin foi fechada (o Chrome da automação foi fechado). '
                'Clique em "Conectar AdvWin" para abrir de novo.')
    if "timeout" in baixo:
        return ("O AdvWin demorou demais para responder. Confira se a sessão ainda está "
                "logada e tente novamente.")
    if "net::" in baixo or "econnrefused" in baixo or "err_internet_disconnected" in baixo:
        return "Não foi possível acessar o AdvWin pela rede. Confira sua conexão e tente novamente."
    return texto


_trabalhos = FilaTrabalho()


def enfileirar(job, ao_concluir, despachar=None) -> None:
    """Executa `job()` numa fila de fundo, um de cada vez - a sessão do AdvWin (a página
    do Playwright) é compartilhada e não é segura pra usar de mais de uma thread ao mesmo
    tempo. Chama `ao_concluir(resultado, erro)` ao final, na própria thread de fundo (quem
    chamar precisa fazer o `self.after(0, ...)` pra mexer na UI a partir daí)."""
    _trabalhos.enfileirar(job, ao_concluir, despachar)


def esta_ocupado() -> bool:
    return _trabalhos.ocupada


def bloquear_para_atualizacao() -> bool:
    return _trabalhos.bloquear_se_ociosa()


def cancelar_encerramento() -> None:
    _trabalhos.desbloquear()


def _fechar_sessao() -> None:
    """Executada pelo mesmo worker que criou o Playwright e o contexto Chrome."""
    global _playwright, _contexto, _autenticado
    try:
        if _contexto is not None:
            _contexto.close()
    finally:
        if _playwright is not None:
            _playwright.stop()
        _playwright, _contexto, _autenticado = None, None, False


def encerrar_sessao(ao_concluir, despachar) -> None:
    _trabalhos.encerrar(_fechar_sessao, ao_concluir, despachar)


def _demo():
    assert PERFIL_CHROME.name == "advwin-chrome-profile"
    assert URL_DASHBOARD.startswith("https://")
    assert set(URLS_AREA) == {"Trabalhista", "Contencioso"}
    assert esta_conectado() is False
    assert verificar_sessao() is False  # sem sessão aberta não tenta falar com o Chrome
    assert re.sub(r"\D", "", "20/08/2026") == "20082026"
    assert _hhmm("0:15") == "00:15"
    assert _hhmm("1:05") == "01:05"
    assert _hhmm("10:30") == "10:30"
    assert "Conectar AdvWin" in mensagem_amigavel(RuntimeError("Target page, context or browser has been closed"))
    assert "demorou demais" in mensagem_amigavel(RuntimeError("Timeout 30000ms exceeded"))
    assert "rede" in mensagem_amigavel(RuntimeError("net::ERR_CONNECTION_RESET"))
    assert mensagem_amigavel(RuntimeError('Nenhuma pasta encontrada para "123" no AdvWin.')) == \
        'Nenhuma pasta encontrada para "123" no AdvWin.'
    print("advwin.py OK")


if __name__ == "__main__":
    _demo()
