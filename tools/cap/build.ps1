# build.ps1 — one-shot: sync www/ into the Android project and compile the debug APK.
#
#   edit tools/cap/www/index.html  ->  .\tools\cap\build.ps1  ->  app-debug.apk
#
# Run from anywhere; paths are resolved relative to this script.
# Pass -Release to build an (unsigned) release APK instead of debug.

param([switch]$Release)

$ErrorActionPreference = 'Stop'
$cap = $PSScriptRoot                      # ...\tools\cap
$android = Join-Path $cap 'android'

# --- 1. Java -----------------------------------------------------------------
# The Android build needs a *full* JDK (it runs jlink). A JetBrains Runtime
# (PyCharm/IDEA) won't do — those ship without jlink.exe. So we require a
# JAVA_HOME that actually contains bin\jlink.exe, and otherwise hunt for one.
function Test-FullJdk($jdk) { $jdk -and (Test-Path (Join-Path $jdk 'bin\jlink.exe')) }

if (-not (Test-FullJdk $env:JAVA_HOME)) {
  $candidate = @(
    'C:\Program Files\Microsoft',
    'C:\Program Files\Eclipse Adoptium',
    'C:\Program Files\Java',
    'C:\Program Files\Amazon Corretto'
  ) | Where-Object { Test-Path $_ } |
      ForEach-Object { Get-ChildItem $_ -Recurse -Filter jlink.exe -ErrorAction SilentlyContinue } |
      Select-Object -First 1
  if (-not $candidate) { throw "No full JDK found (need one with bin\jlink.exe). Install one: winget install Microsoft.OpenJDK.21" }
  $env:JAVA_HOME = Split-Path (Split-Path $candidate.FullName)   # strip \bin\jlink.exe
}
Write-Host "java: $env:JAVA_HOME" -ForegroundColor DarkGray

# --- 2. Stage the app payload ------------------------------------------------
# www/ is the dev tree (curate pages, source photos for the catalog pipeline);
# stage.py copies only what the app opens into dist/, which is the Capacitor webDir.
Write-Host "==> stage.py (www/ -> dist/)" -ForegroundColor Cyan
$py = Join-Path $cap '..\..\.venv\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = 'python' }
& $py (Join-Path $cap 'stage.py')
if ($LASTEXITCODE -ne 0) { throw "stage.py failed." }

# --- 3. Sync web assets into the native project ------------------------------
Write-Host "==> cap sync (copying www/ into android assets)" -ForegroundColor Cyan
Push-Location $cap
try { & (Join-Path $cap 'node_modules\.bin\cap.cmd') sync android }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "cap sync failed." }

# --- 4. Compile the APK ------------------------------------------------------
$task = if ($Release) { 'assembleRelease' } else { 'assembleDebug' }
Write-Host "==> gradlew $task" -ForegroundColor Cyan
Push-Location $android
# 'clean' first: AGP packages incrementally and leaves removed assets as holes in
# the zip, so an APK whose payload shrank by 100 MB stayed 160 MB on disk.
try { & (Join-Path $android 'gradlew.bat') clean $task }
finally { Pop-Location }
if ($LASTEXITCODE -ne 0) { throw "gradle build failed." }

# --- 5. Report the artifact --------------------------------------------------
$variant = if ($Release) { 'release' } else { 'debug' }
$apk = Join-Path $android "app\build\outputs\apk\$variant\app-$variant.apk"
if (Test-Path $apk) {
  Write-Host "`nAPK ready: $apk" -ForegroundColor Green
} else {
  Write-Host "`nBuild finished but APK not found at expected path: $apk" -ForegroundColor Yellow
}
