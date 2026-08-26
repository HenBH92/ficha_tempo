; Script do Inno Setup para gerar o instalador do VLF Ficha de Tempo.
; Requer o Inno Setup (compilador ISCC) - baixar em https://jrsoftware.org/isdl.php
;
; Como usar:
;   1. Gere o exe:  pyinstaller VLF-FichaDeTempo.spec
;   2. Compile este script: iscc installer.iss
;      (ou abra o arquivo no Inno Setup Compiler e clique em "Compile")
;   3. O instalador sai em installer_output\VLF-FichaDeTempo-Setup-{versao}.exe
;
; A cada nova versão do app, so precisa mudar o MyAppVersion abaixo.
; NUNCA mude o AppId depois do primeiro instalador distribuído - é ele que
; permite ao Windows reconhecer "isso é uma atualização", não a versão.

#define MyAppName "VLF Ficha de Tempo"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "VLF Advogados"
#define MyAppExeName "VLF-FichaDeTempo.exe"

[Setup]
AppId={{71A50D86-36BD-4DCF-9866-7B0E05DE0B77}
AppMutex={#MyAppName}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Instala só para o usuário atual - sem pedir permissão de administrador (UAC)
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=VLF-FichaDeTempo-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
SetupIconFile=assets\vlf_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: nowait postinstall skipifsilent

; Observação: o instalador só mexe em {app} (pasta do programa). Os dados do
; usuário (estado.json, planilhas do dia, favoritos, modelos) ficam em
; %APPDATA%\VLF Ficha de Tempo e não são tocados na instalação/desinstalação.
