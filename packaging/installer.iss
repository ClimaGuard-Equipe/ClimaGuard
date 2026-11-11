#ifndef BuildDir
  #define BuildDir "..\work\windows-build\dist\ClimaGuard"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif
#ifndef Bootstrapper
  #error Supply /DBootstrapper=path-to-MicrosoftEdgeWebview2Setup.exe
#endif

[Setup]
AppId={{D87FE6EA-6F56-4A7A-9B3D-0DC5A5C91732}
AppName=ClimaGuard
AppVersion=1.6.5
AppVerName=ClimaGuard 1.6.5
AppPublisher=Equipe ClimaGuard
DefaultDirName={localappdata}\Programs\ClimaGuard
DefaultGroupName=ClimaGuard
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableProgramGroupPage=yes
DisableWelcomePage=no
WizardStyle=modern
SetupIconFile=climaguard.ico
UninstallDisplayIcon={app}\ClimaGuard.exe
OutputDir={#OutputDir}
OutputBaseFilename=ClimaGuard-Instalador-1.6.5-x64
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
InfoBeforeFile=leia-me.txt

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na área de trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "{#BuildDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "leia-me.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#Bootstrapper}"; DestName: "MicrosoftEdgeWebview2Setup.exe"; Flags: dontcopy

[Icons]
Name: "{autoprograms}\ClimaGuard"; Filename: "{app}\ClimaGuard.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\ClimaGuard"; Filename: "{app}\ClimaGuard.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\ClimaGuard.exe"; Description: "Abrir ClimaGuard"; Flags: nowait postinstall skipifsilent

[Code]
function HasWebView2: Boolean;
var
  Version: String;
  Key: String;
begin
  Key := 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  Result := (RegQueryStringValue(HKLM32, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
  if not Result then
    Result := (RegQueryStringValue(HKCU, Key, 'pv', Version) and (Version <> '') and (Version <> '0.0.0.0'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  if not HasWebView2 then begin
    WizardForm.StatusLabel.Caption := 'Preparando o componente Microsoft WebView2...';
    ExtractTemporaryFile('MicrosoftEdgeWebview2Setup.exe');
    if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'), '/silent /install', '',
                SW_HIDE, ewWaitUntilTerminated, ExitCode) then begin
      Result := 'Não foi possível iniciar a instalação do Microsoft WebView2. Confira a conexão com a internet.';
      Exit;
    end;
    if not HasWebView2 then
      Result := 'O Microsoft WebView2 não ficou disponível. Confira a internet, instale o WebView2 pela Microsoft e execute este instalador novamente.';
  end;
end;
