$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$JdkRoot = "C:\Program Files\Android\openjdk\jdk-21.0.8"
$SdkRoot = Join-Path $RepoRoot ".local-android-sdk"
$GradleProject = Join-Path $RepoRoot "android"
$SourceApk = Join-Path $GradleProject "app\build\outputs\apk\debug\app-debug.apk"
$OutputDir = Join-Path $RepoRoot "apk-output"
$OutputApk = Join-Path $OutputDir "pixel-garage-debug.apk"

if (-not (Test-Path (Join-Path $JdkRoot "bin\java.exe"))) {
  throw "JDK not found at $JdkRoot"
}

if (-not (Test-Path (Join-Path $SdkRoot "platforms\android-36"))) {
  throw "Android SDK platform android-36 not found at $SdkRoot"
}

$env:JAVA_HOME = $JdkRoot
$env:ANDROID_HOME = $SdkRoot
$env:ANDROID_SDK_ROOT = $SdkRoot
$env:Path = "$JdkRoot\bin;$(Join-Path $SdkRoot "platform-tools");$(Join-Path $SdkRoot "cmdline-tools\latest\bin");$env:Path"

Push-Location $RepoRoot
try {
  npm run build
  npx cap sync android

  Push-Location $GradleProject
  try {
    .\gradlew.bat assembleDebug
  } finally {
    Pop-Location
  }

  New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
  Copy-Item -LiteralPath $SourceApk -Destination $OutputApk -Force
  Write-Host "APK created: $OutputApk"
} finally {
  Pop-Location
}
