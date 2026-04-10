Add-Type -AssemblyName System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class NativeCapture {
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@
$url = 'http://127.0.0.1:8000/projects/proj_4c97bbb4ba6d/result?surface_mode=internal'
$output = 'C:\Users\Hyein\ClaudeAI\AI_Project\project_result_capture.png'
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$proc = Start-Process -FilePath $chrome -ArgumentList @('--new-window', $url) -PassThru
Start-Sleep -Seconds 6
$target = Get-Process chrome | Sort-Object StartTime -Descending | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
if (-not $target) { throw 'Chrome window not found' }
[NativeCapture]::ShowWindow($target.MainWindowHandle, 5) | Out-Null
[NativeCapture]::SetForegroundWindow($target.MainWindowHandle) | Out-Null
Start-Sleep -Seconds 2
$rect = New-Object NativeCapture+RECT
[NativeCapture]::GetWindowRect($target.MainWindowHandle, [ref]$rect) | Out-Null
$width = $rect.Right - $rect.Left
$height = $rect.Bottom - $rect.Top
$bitmap = New-Object System.Drawing.Bitmap $width, $height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($rect.Left, $rect.Top, 0, 0, $bitmap.Size)
$bitmap.Save($output, [System.Drawing.Imaging.ImageFormat]::Png)
$graphics.Dispose()
$bitmap.Dispose()
