[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$')]
    [string]$Version,
    [Parameter(Mandatory = $true)][string]$NotesFile,
    [string]$OutputRoot = 'build\releases',
    [string]$Python = '.venv\Scripts\python.exe',
    [switch]$SkipPackage
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$raiz = Split-Path -Parent $PSScriptRoot
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Confirmar-Saida([string]$Etapa) {
    if ($LASTEXITCODE -ne 0) { throw "$Etapa falhou (codigo $LASTEXITCODE)." }
}

Push-Location -LiteralPath $raiz
$metadadosAntes = $env:FICHA_BUILD_METADATA
try {
    $notas = (Resolve-Path -LiteralPath $NotesFile).Path
    if (-not (Test-Path -LiteralPath $notas -PathType Leaf)) { throw 'NotesFile deve ser um arquivo.' }
    if ([string]::IsNullOrWhiteSpace([IO.File]::ReadAllText($notas))) { throw 'As notas nao podem estar vazias.' }
    $pythonCmd = (Get-Command $Python -ErrorAction Stop).Source
    $saida = [IO.Path]::GetFullPath((Join-Path $OutputRoot $Version))
    if (Test-Path -LiteralPath $saida) { throw "Destino ja existe; escolha outro OutputRoot: $saida" }
    $commit = & git rev-parse HEAD
    Confirmar-Saida 'Leitura do commit'
    $metadata = Join-Path $saida 'metadata'
    & $pythonCmd (Join-Path $PSScriptRoot 'build_metadata.py') --version $Version --commit $commit --output $metadata --check-environment
    Confirmar-Saida 'Validacao de versao e dependencias'
    & $pythonCmd -m pip check
    Confirmar-Saida 'Consistencia das dependencias'
    $manifesto = & $pythonCmd -m pip freeze
    Confirmar-Saida 'Manifesto de dependencias'
    [IO.File]::WriteAllLines((Join-Path $metadata 'requirements-resolved.txt'), [string[]]$manifesto, $utf8)
    Copy-Item -LiteralPath $notas -Destination (Join-Path $metadata 'release-notes.md')
    if (-not $SkipPackage) {
        & dotnet tool restore --tool-manifest (Join-Path $raiz '.config\dotnet-tools.json')
        Confirmar-Saida 'Restauracao do vpk local (requer .NET SDK)'
    }
    $env:FICHA_BUILD_METADATA = $metadata
    $dist = Join-Path $saida 'app'
    & $pythonCmd -m PyInstaller --noconfirm --clean --distpath $dist --workpath (Join-Path $saida 'pyinstaller') (Join-Path $raiz 'FichaTempo_VLF.spec')
    Confirmar-Saida 'PyInstaller'
    $aplicativo = Join-Path $dist 'FichaTempo_VLF'
    if (-not (Test-Path -LiteralPath (Join-Path $aplicativo 'FichaTempo_VLF.exe'))) { throw 'Executavel nao encontrado.' }
    if (-not $SkipPackage) {
        $releases = Join-Path $saida 'Releases'
        & dotnet tool run vpk -- pack --packId 'VLFAdvogados.FichaTempo' --packVersion $Version --packDir $aplicativo --mainExe 'FichaTempo_VLF.exe' --packTitle 'Ficha Tempo VLF' --packAuthors 'VLF Advogados' --runtime win-x64 --channel win --delta None --noPortable --icon (Join-Path $raiz 'assets\vlf_icon.ico') --releaseNotes (Join-Path $metadata 'release-notes.md') --outputDir $releases
        Confirmar-Saida 'Velopack pack'
        Write-Host "Artefatos para distribuicao: $releases"
        Get-ChildItem -LiteralPath $releases -File | Select-Object Name, Length
    }
    Write-Host "Executavel: $(Join-Path $aplicativo 'FichaTempo_VLF.exe')"
    Write-Host "Metadados: $metadata"
}
finally {
    $env:FICHA_BUILD_METADATA = $metadadosAntes
    Pop-Location
}
