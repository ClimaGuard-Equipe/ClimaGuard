param(
    [string]$Python = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'),
    [Parameter(Mandatory=$true)][string]$IsccPath,
    [Parameter(Mandatory=$true)][string]$Bootstrapper,
    [string]$OutputDir = (Join-Path $PSScriptRoot '..\dist'),
    [switch]$ReuseCache
)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$buildDirectory = Join-Path $projectRoot 'work\windows-build'
$IsccPath = (Resolve-Path -LiteralPath $IsccPath).Path
$Bootstrapper = (Resolve-Path -LiteralPath $Bootstrapper).Path
$Python = (Resolve-Path -LiteralPath $Python).Path
$signature = Get-AuthenticodeSignature -LiteralPath $Bootstrapper
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notlike '*Microsoft Corporation*') {
    throw 'Use o bootstrapper oficial do Microsoft WebView2, com assinatura digital válida.'
}
Push-Location $projectRoot
try {
    & $Python packaging\check_publication.py --working-tree
    if ($LASTEXITCODE -ne 0) { throw 'A revisão dos arquivos públicos falhou.' }
    & $Python packaging\prepare_whatsapp.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao preparar o WhatsApp local.' }
    & $Python -c "import ssl; context = ssl.create_default_context(); assert context.verify_mode == ssl.CERT_REQUIRED"
    if ($LASTEXITCODE -ne 0) { throw 'O ambiente Python não conseguiu preparar conexões HTTPS verificadas.' }
    & $Python packaging\build_icon.py
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o ícone.' }
    & $Python -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Os testes falharam.' }
    $freezerArgs = @('-m','PyInstaller','--noconfirm','--distpath',(Join-Path $buildDirectory 'dist'),'--workpath',(Join-Path $buildDirectory 'build'))
    if (-not $ReuseCache) { $freezerArgs += '--clean' }
    & $Python @freezerArgs packaging\ClimaGuard.spec
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar ClimaGuard.exe.' }
    $frozenExe = Join-Path $buildDirectory 'dist\ClimaGuard\ClimaGuard.exe'
    & $Python packaging\check_publication.py --bundle (Join-Path $buildDirectory 'dist\ClimaGuard')
    if ($LASTEXITCODE -ne 0) { throw 'O pacote contém arquivos que não devem ser publicados.' }
    $testReport = Join-Path $buildDirectory 'frozen-self-test.json'
    $probe = Start-Process -FilePath $frozenExe -ArgumentList @('--self-test',('"' + $testReport + '"')) -WindowStyle Hidden -PassThru
    if (-not $probe.WaitForExit(30000)) {
        Stop-Process -Id $probe.Id
        throw 'O executável empacotado não concluiu a verificação de inicialização.'
    }
    if ($probe.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $testReport) -or -not (Get-Content -LiteralPath $testReport -Raw | ConvertFrom-Json).ok) {
        throw 'O executável empacotado falhou na verificação. O instalador não será compilado.'
    }
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    $OutputDir = (Resolve-Path -LiteralPath $OutputDir).Path
    & $IsccPath ('/DBuildDir=' + (Join-Path $buildDirectory 'dist\ClimaGuard')) ('/DOutputDir=' + $OutputDir) ('/DBootstrapper=' + $Bootstrapper) packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao gerar o instalador.' }
    Get-ChildItem -LiteralPath $OutputDir -Filter 'ClimaGuard-Instalador-*.exe' | Get-FileHash -Algorithm SHA256
} finally {
    Pop-Location
}
