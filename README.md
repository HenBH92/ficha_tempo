# Ficha de Tempo VLF

Aplicativo Windows para cronometrar atividades, preencher a planilha diaria e lancar horas no AdvWin.

## Desenvolvimento

Requer Python **3.14.0 x64** e Google Chrome instalado para o AdvWin.

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe main.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Build e distribuicao

O executavel `FichaTempo_VLF.exe` usa PyInstaller **onedir** e Velopack **1.2.0**. A versao e informada uma unica vez ao build; o aplicativo e o pacote recebem a mesma versao. Requer .NET SDK 8 para restaurar a ferramenta local `vpk` fixada no manifesto.

```powershell
New-Item -ItemType Directory -Force build | Out-Null
Set-Content -LiteralPath build\notas.md -Value 'Correcoes desta versao.' -Encoding utf8
.\scripts\build.ps1 -Version '1.0.1' -NotesFile 'build\notas.md'
```

Pacotes: `build\releases\1.0.1\Releases\`. Executavel: `build\releases\1.0.1\app\FichaTempo_VLF\FichaTempo_VLF.exe`. Preserve a pasta completa do executavel.

O workflow manual **Preparar release Windows (rascunho)** gera um draft em `HenBH92/ficha_tempo-releases`; publicar continua sendo uma acao manual apos a validacao. O repositorio de codigo e separado do repositorio publico de instaladores.

Consulte [o guia de distribuicao](docs/distribuicao.md) para configurar o repositorio e o secret, validar duas versoes, migrar o instalador antigo e publicar.
