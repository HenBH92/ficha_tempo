# Distribuicao Windows

## Contrato do pacote

- Identidade permanente: `VLFAdvogados.FichaTempo`.
- Executavel: `FichaTempo_VLF.exe`, Windows x64, PyInstaller onedir.
- Canal: `win`, versoes estaveis `X.Y.Z` maiores que `0.0.0`, sem prefixo `v` na entrada.
- Python 3.14.0 x64; dependencias diretas e transitivas em `requirements*.txt`; SDK Python Velopack e CLI `vpk` ambos 1.2.0.
- Pacotes completos (`--delta None`); nao gera distribuicao portatil. O Setup, o pacote full e os manifests produzidos pelo vpk devem permanecer juntos e manter seus nomes.
- Recursos somente leitura: logo, icone, `aquivo_modelo.xlsx`, temas/fontes CustomTkinter, driver Node do Playwright e `build-info.json`.
- Google Chrome e instalado separadamente. O pacote inclui o driver Playwright, nao baixa um navegador durante o build.

O arquivo JSON de build tem `versao` e `commit`. Ele e gerado a partir da entrada de versao e do SHA Git completo. O mesmo valor preenche o recurso de versao Windows e o pacote Velopack. Em desenvolvimento, sem esse JSON, o aplicativo usa 1.0.0. A identidade do pacote e independente da versao e nao deve mudar.

Os arquivos gravaveis continuam em `%APPDATA%\VLF Ficha de Tempo` conforme `caminhos.py`; o instalador e o atualizador nao devem apagar nem migrar essa pasta. A instalacao Velopack e por usuario. O Python e o .NET SDK sao ferramentas de build; nao sao pre-requisitos para o usuario final.

## Build local

Prepare Python 3.14.0 x64 e .NET SDK 8. O vpk e restaurado pelo manifesto `.config/dotnet-tools.json`, sem instalacao global.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
New-Item -ItemType Directory -Force build | Out-Null
Set-Content -LiteralPath build\notas.md -Value 'Descricao das alteracoes.' -Encoding utf8
.\scripts\build.ps1 -Version '1.0.1' -NotesFile 'build\notas.md'
```

Saidas para esse comando:

| Pasta | Conteudo |
|---|---|
| `build\releases\1.0.1\app\FichaTempo_VLF` | Executavel e dependencias onedir |
| `build\releases\1.0.1\Releases` | Artefatos exatos gerados pelo vpk para distribuicao |
| `build\releases\1.0.1\metadata` | JSON de origem, recurso Windows, notas e `pip freeze` |
| `build\releases\1.0.1\pyinstaller` | Intermediarios e avisos do PyInstaller |

O script interrompe em qualquer erro. Ele recusa um destino que ja existe, preservando builds anteriores. Para repetir use `-OutputRoot 'build\outra-tentativa'`. Para validar somente o executavel, `-SkipPackage` dispensa o SDK .NET e nao produz um instalador. A especificacao PyInstaller exige os metadados gerados pelo script: nao rode o `.spec` diretamente.

O manifesto torna as versoes de dependencias reproduziveis e registra o ambiente resolvido; nao promete binarios identicos byte a byte. Antes de distribuir, gere o build a partir de um commit revisado e sem alteracoes locais pendentes.

## Preparacao unica no GitHub

1. Criar o repositorio **publico** `HenBH92/ficha_tempo-releases`, inicializado com um README e uma branch padrao. Ele recebera apenas instaladores, pacotes, manifests e notas publicas; o codigo fica no repositorio original.
2. Criar um personal access token **fine-grained**, limitado ao repositorio `HenBH92/ficha_tempo-releases`, com **Contents: Read and write**. Metadata read e a permissao implicita do GitHub. Definir vencimento e responsavel pela renovacao. Nenhuma permissao para o repositorio de codigo e necessaria nesse token.
3. No repositorio **de codigo**, abrir Settings > Secrets and variables > Actions e criar o secret `RELEASES_TOKEN` com esse token. Ele so e fornecido ao passo final de upload e nao entra no executavel, nos metadados nem no arquivo de notas.
4. Disponibilizar o workflow `.github/workflows/release-draft.yml` na branch padrao do repositorio de codigo para aparecer a opcao Run workflow.

Essas etapas alteram recursos externos e precisam ser executadas pelo responsavel autorizado. A existencia do arquivo de workflow nao significa que o repositorio ou o secret foram criados.

## Preparar e publicar uma versao

1. No repositorio de codigo: Actions > **Preparar release Windows (rascunho)** > Run workflow. Escolher o commit/branch revisado, informar por exemplo `1.0.1` e as notas Markdown. As notas sao tratadas como dados e gravadas em arquivo.
2. O job instala dependencias fixadas, executa os testes locais, empacota e guarda um artifact com os pacotes e os metadados. O vpk cria **somente draft**, com tag `v1.0.1`, no repositorio publico de distribuicao. Uma tag existente nao e sobrescrita nem mesclada. Nao reutilizar versoes ja publicadas.
3. Revisar no draft o Setup, o pacote `*-full.nupkg` e todos os manifests que o vpk anexou. Conferir a versao, as notas e o commit no artifact do Actions. Os fontes `.zip`/`.tar.gz` que o GitHub adiciona automaticamente nao sao o instalador.
4. Baixar o Setup do draft autenticado e executar o checklist abaixo em um perfil/maquina de teste. Um draft ainda nao aparece ao atualizador publico.
5. Apos validar, abrir o draft no repositorio de distribuicao e clicar **Publish release**, mantendo release estavel. So entao a versao fica disponivel para os aplicativos instalados.

Nao criar uma release manual com apenas o `.exe`: os manifests e o pacote completo sao necessarios para o protocolo de atualizacao. O upload e feito pelo proprio `vpk upload github`, com `--publish false`, `--pre false` e `--merge false`; ele seleciona os assets nativos do protocolo. Mantenha as releases anteriores para rastreabilidade. O workflow nao publica automaticamente.

## Checklist de duas versoes e preservacao

O teste de instalacao deve usar um perfil Windows isolado, com dados ficticios. Nao efetuar lancamentos reais no AdvWin.

1. Gerar dois builds, por exemplo `1.0.1` e `1.0.2`, com notas diferentes. Sao pastas separadas sob `build\releases`.
2. Instalar a primeira pelo Setup. Abrir pelo atalho, conferir versao/commit e recursos visuais, criar um favorito/modelo e um timer ficticio, salvar e fechar. Conferir que a planilha modelo pode ser lida e a planilha de saida gravada.
3. Preparar a segunda versao em um feed local de teste ou no draft autenticado. Para verificar o fluxo completo do feed publico, e necessario publicar uma release de teste autorizada; drafts sao invisiveis aos clientes anonimos. Verificar isso separadamente, sem declarar o teste online concluido apenas por instalar um Setup.
4. Com uma versao instalada e um feed de teste controlado, exercitar detectar, baixar, recusar/adiar a confirmacao e confirmar a instalacao. Conferir que nao ha instalacao enquanto existir timer ativo ou lancamento pendente.
5. Depois do reinicio, conferir nova versao e preservacao de estado, favoritos, modelos, planilha de saida e perfil Chrome em `%APPDATA%`. Conferir que o aplicativo continua abrindo apos reiniciar o Windows.
6. Repetir sem rede e sem release: o app continua funcional, com erro informativo na verificacao manual e sem repetir avisos de erro em segundo plano. Confirmar que versoes anteriores nao sao oferecidas como atualizacao.
7. Registrar resultados reais, versoes, sistema usado e limitacoes. Testes unitarios e build bem-sucedido nao comprovam instalacao, reinicio nem preservacao na maquina do usuario.

## Instalacoes antigas

`installer.iss` permanece como historico do Inno Setup e esta descontinuado. A transicao para Velopack exige instalar o novo Setup manualmente uma vez. A identidade do instalador antigo e diferente: uma instalacao antiga pode continuar listada no Windows e seus atalhos podem coexistir. Validar a nova instalacao e os dados antes de remover atalhos ou desinstalar a antiga; nao automatizar essa limpeza. Nunca apagar `%APPDATA%\VLF Ficha de Tempo` para fazer a migracao.

## Referencias

- [Velopack para Python](https://docs.velopack.io/getting-started/python)
- [CLI vpk 1.2.0 para Windows](https://docs.velopack.io/reference/cli/content/vpk-windows)
- [Empacotamento Velopack](https://docs.velopack.io/packaging/overview)
- [Gerenciar releases no GitHub](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
