Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$segmentsDir = 'C:\Users\Hyein\ClaudeAI\AI_Project\.tmp_fullpage_segments'
New-Item -ItemType Directory -Force -Path $segmentsDir | Out-Null
Get-ChildItem -LiteralPath $segmentsDir -Filter '*.png' -ErrorAction SilentlyContinue | Remove-Item -Force
$url = 'http://127.0.0.1:8000/projects/proj_4c97bbb4ba6d/result?surface_mode=internal'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
Start-Process -FilePath $chrome -ArgumentList @('--new-window', $url) | Out-Null
Start-Sleep -Seconds 6
$target = Get-Process chrome | Sort-Object StartTime -Descending | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $target) { throw 'Chrome window not found' }
$wshell = New-Object -ComObject WScript.Shell
$wshell.AppActivate($target.Id) | Out-Null
Start-Sleep -Milliseconds 500
$wshell.SendKeys('{F11}')
Start-Sleep -Milliseconds 1500
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$shotWidth = $screen.Width
$shotHeight = $screen.Height
$lastHash = ''
$stableCount = 0
for ($i = 0; $i -lt 14; $i++) {
    $bitmap = New-Object System.Drawing.Bitmap $shotWidth, $shotHeight
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($screen.Left, $screen.Top, 0, 0, $bitmap.Size)
    $path = Join-Path $segmentsDir ('segment_{0:D2}.png' -f $i)
    $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
    if ($hash -eq $lastHash) {
        $stableCount += 1
    } else {
        $stableCount = 0
    }
    if ($stableCount -ge 1) { break }
    $lastHash = $hash
    $wshell.SendKeys('{PGDN}')
    Start-Sleep -Milliseconds 1300
}
$wshell.SendKeys('{HOME}')
Start-Sleep -Milliseconds 300
$wshell.SendKeys('{F11}')
