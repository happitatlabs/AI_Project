$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$SdkRoot = Join-Path $RepoRoot ".local-android-sdk"
$Adb = Join-Path $SdkRoot "platform-tools\adb.exe"
$Apk = Join-Path $RepoRoot "apk-output\pixel-garage-debug.apk"

if (-not (Test-Path $Adb)) {
  throw "adb not found at $Adb"
}

if (-not (Test-Path $Apk)) {
  throw "APK not found at $Apk. Run npm run android:apk:local first."
}

& $Adb devices
& $Adb install -r $Apk
