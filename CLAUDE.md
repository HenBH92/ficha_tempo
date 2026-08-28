# ficha_tempo — Contexto do Projeto

App desktop (CustomTkinter) de ficha de tempo para a VLF Advogados: múltiplos cronômetros por pasta/cliente, gera linhas na planilha diária e lança horas direto no AdvWin (sistema de gestão de processos da firma) via automação Playwright.

## Rodar em desenvolvimento

```
.venv\Scripts\Activate.ps1
python main.py
```

## Build / instalador

`FichaTempo_VLF.spec` (PyInstaller) e `installer.iss` (Inno Setup) já existem no repo, mas o processo de build/distribuição ainda está sendo definido — não assumir comandos prontos, confirmar antes de empacotar/distribuir.

Nome do executável gerado: `FichaTempo_VLF.exe` (renomeado de `VLF-FichaDeTempo.exe` em 2026-08-28, mesma convenção nos próximos builds/instaladores).

## Arquitetura (um módulo, uma responsabilidade)

| Módulo | Responsabilidade |
|---|---|
| `main.py` | UI principal: cards de cronômetro, monta a linha da planilha, dispara inserção no AdvWin |
| `advwin.py` | Sessão Playwright com o AdvWin (perfil de Chrome dedicado, fila serializada em thread de fundo) |
| `retroativo.py` | Lê planilha já preenchida e prepara lançamento retroativo em lote |
| `retro_preview.py` | Janela de prévia/edição antes de confirmar o lote retroativo |
| `planilha.py` | Lê listas auxiliares do modelo e grava linhas na planilha de saída |
| `estado.py` | Máquina de estado do timer (start/pause/stop) + persistência em JSON |
| `favoritos.py` | Pastas/clientes favoritos (sugestão priorizada) |
| `modelos.py` | Modelos de descrição reutilizáveis (atalho "/") |
| `widgets.py` | Combobox pesquisável reutilizável |
| `icones.py` | Ícones desenhados via PIL (independe do emoji do SO), cache por (nome, tamanho, cor) |
| `caminhos.py` | Caminhos de recursos (empacotados, somente leitura) vs. dados (por usuário, graváveis) |
| `atualizador.py` | Checagem/instalação silenciosa de atualização via GitHub Releases |

## Convenções

- Nomes de variáveis, funções e docstrings em português — manter o padrão ao editar/adicionar código.
- Um módulo por responsabilidade; não misturar assuntos de módulos diferentes sem necessidade.

## Testes

Sem suíte automatizada. Validação é manual — rodar o app e testar o fluxo pela UI.

## AdvWin — regras de segurança em teste ao vivo (crítico)

O AdvWin é o sistema de produção da firma; lançamentos não podem ser desfeitos pelo usuário.

**Antes de editar `advwin.py`, `retro_preview.py` ou o fluxo de inserção em `main.py`**, ler a memória do projeto (`project-advwin-integration`, `feedback-advwin-live-testing`) — várias correções já feitas parecem código redundante/simplificável para quem não conhece o histórico (ver lista abaixo).

- **Nunca** chamar `advwin.lancar_horas(...)` (ou qualquer outra inserção real) para testar uma correção. Sempre pedir para o usuário disparar pela UI do próprio app, e monitorar stdout/stderr (`[advwin]`, tracebacks) em paralelo.
- Não reiniciar o app no meio de um lote ("Lançar todas") ainda processando — esperar ficar ocioso.
- Não abrir uma segunda sessão de browser (ex.: DevTools MCP) enquanto o perfil de automação está com sessão ativa em teste — o AdvWin invalida sessões antigas ao logar de novo.
- Depois de editar `advwin.py` (sem hot-reload): reiniciar o processo e confirmar que não sobrou `python.exe` órfão — perfil do Chrome travado bloqueia o próximo launch.
- No Windows, `kill $PID` não mata de forma confiável um processo GUI em background — usar `taskkill //F //PID <pid> //T`.

### Correções já aplicadas — não reverter sem reconfirmar o motivo

- `advwin._processar_fila()`: `job()` e `ao_concluir()` cada um no seu próprio try/except. Parece redundante, mas sem isso uma exceção não tratada mata a thread única do worker pra sempre (fila trava sem erro visível) — bug crítico já corrigido.
- Verificação de segurança do link "Ficha-Tempo" em `lancar_horas()` conta matches na **página inteira**, não escopada à row. Já foi tentado escopar por `role="row"` e quebrou pior (link não é descendente DOM da row no AdvWin) — não repetir sem inspecionar o DOM ao vivo primeiro.
- `main.py` `_inserir()`: **não** chamar `_atualizar_horas_cobraveis_auto()` depois de coletar o valor de horas digitado pelo usuário — já causou horas manuais sobrescritas silenciosamente pelo tempo do cronômetro antes de salvar.

Detalhes completos, bugs em aberto e melhorias pendentes: memória do projeto (`project-advwin-integration`, `feedback-advwin-live-testing`).
