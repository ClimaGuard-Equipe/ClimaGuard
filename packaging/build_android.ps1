param(
    [string]$ToolsRoot = '',
    [string]$OutputDir = ''
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
if (!$ToolsRoot) { $ToolsRoot = Join-Path $repo 'work\android-tools' }
$jdk = (Get-ChildItem -LiteralPath (Join-Path $ToolsRoot 'jdk') -Directory | Select-Object -First 1).FullName
$gradle = (Get-ChildItem -LiteralPath (Join-Path $ToolsRoot 'gradle') -Directory | Select-Object -First 1).FullName
$sdk = Join-Path $ToolsRoot 'sdk'
if (!(Test-Path -LiteralPath "$jdk\bin\javac.exe") -or !(Test-Path -LiteralPath "$gradle\bin\gradle.bat") -or !(Test-Path -LiteralPath "$sdk\platforms\android-36\android.jar")) {
    throw 'Prepare JDK 17, Gradle 8.11.1, Android SDK 36 e Build Tools 35.0.0 em ToolsRoot.'
}
$env:JAVA_HOME = $jdk
$env:ANDROID_HOME = $sdk
$env:PATH = "$jdk\bin;$env:PATH"
$signing = Join-Path $env:LOCALAPPDATA 'ClimaGuard\android-signing'
New-Item -ItemType Directory -Force -Path $signing | Out-Null
$env:CLIMAGUARD_KEYSTORE = Join-Path $signing 'release.jks'
$passwordFile = Join-Path $signing 'password.dpapi'
if (!(Test-Path -LiteralPath $env:CLIMAGUARD_KEYSTORE)) {
    if (Test-Path -LiteralPath $passwordFile) { throw 'Senha de assinatura existente sem a chave. Recupere o backup antes de criar outra assinatura.' }
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $password = [Convert]::ToBase64String($bytes)
    $password | ConvertTo-SecureString -AsPlainText -Force | ConvertFrom-SecureString | Set-Content -LiteralPath $passwordFile
    $env:CLIMAGUARD_STORE_PASSWORD = $password
    & "$jdk\bin\keytool.exe" -genkeypair -keystore $env:CLIMAGUARD_KEYSTORE -storepass:env CLIMAGUARD_STORE_PASSWORD -keypass:env CLIMAGUARD_STORE_PASSWORD -alias climaguard -dname 'CN=ClimaGuard, O=Projeto ClimaGuard, C=BR' -keyalg RSA -keysize 3072 -validity 10000 -storetype JKS
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar assinatura.' }
} else {
    $secure = Get-Content -LiteralPath $passwordFile | ConvertTo-SecureString
    $env:CLIMAGUARD_STORE_PASSWORD = [System.Net.NetworkCredential]::new('', $secure).Password
}
try {
    Push-Location (Join-Path $repo 'android')
    & "$gradle\bin\gradle.bat" --no-daemon --console plain testReleaseUnitTest lintRelease assembleRelease
    if ($LASTEXITCODE -ne 0) { throw 'A compilação ou validação do Android falhou.' }
    $apk = Join-Path $repo 'android\app\build\outputs\apk\release\app-release.apk'
    & "$sdk\build-tools\35.0.0\apksigner.bat" verify --verbose $apk
    if ($LASTEXITCODE -ne 0) { throw 'Assinatura do APK inválida.' }
    if ($OutputDir) {
        New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
        $metadata = Get-Content -LiteralPath (Join-Path (Split-Path -Parent $apk) 'output-metadata.json') -Raw | ConvertFrom-Json
        $appVersion = $metadata.elements[0].versionName
        if ($appVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Versao do APK invalida.' }
        $destination = Join-Path $OutputDir "ClimaGuard-Android-$appVersion.apk"
        Copy-Item -LiteralPath $apk -Destination $destination -Force
        Get-FileHash -LiteralPath $destination -Algorithm SHA256
    }
} finally {
    Pop-Location
    Remove-Item Env:\CLIMAGUARD_STORE_PASSWORD -ErrorAction SilentlyContinue
    $password = $null
}
