Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$output = 'C:\Users\Hyein\ClaudeAI\AI_Project\project_result_capture.png'
$url = 'http://127.0.0.1:8000/projects/proj_4c97bbb4ba6d/result?surface_mode=internal'
$form = New-Object System.Windows.Forms.Form
$form.Width = 1440
$form.Height = 2200
$form.ShowInTaskbar = $false
$form.StartPosition = 'Manual'
$form.Location = New-Object System.Drawing.Point(-32000, -32000)
$browser = New-Object System.Windows.Forms.WebBrowser
$browser.ScriptErrorsSuppressed = $true
$browser.ScrollBarsEnabled = $false
$browser.Dock = 'Fill'
$form.Controls.Add($browser)
$completed = $false
$browser.add_DocumentCompleted({
    if ($browser.ReadyState -eq [System.Windows.Forms.WebBrowserReadyState]::Complete) {
        Start-Sleep -Milliseconds 3000
        $bitmap = New-Object System.Drawing.Bitmap $form.Width, $form.Height
        $form.DrawToBitmap($bitmap, (New-Object System.Drawing.Rectangle 0,0,$form.Width,$form.Height))
        $bitmap.Save($output, [System.Drawing.Imaging.ImageFormat]::Png)
        $bitmap.Dispose()
        $script:completed = $true
        $form.Close()
    }
})
$browser.Navigate($url)
[void]$form.Show()
while (-not $completed) {
    [System.Windows.Forms.Application]::DoEvents()
    Start-Sleep -Milliseconds 100
}
