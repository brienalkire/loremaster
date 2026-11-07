# Creates a "Loremaster" shortcut on the desktop that opens control_panel.py
# with the venv's pythonw.exe (no console window). Re-run any time to
# recreate it, e.g. after moving the repo.
$botDir = $PSScriptRoot
$desktop = [Environment]::GetFolderPath('Desktop')
$shortcut = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'Loremaster.lnk'))
$shortcut.TargetPath = Join-Path $botDir '.venv\Scripts\pythonw.exe'
$shortcut.Arguments = '"' + (Join-Path $botDir 'control_panel.py') + '"'
$shortcut.WorkingDirectory = $botDir
$shortcut.Description = 'Start and stop the Loremaster Discord bot'
$shortcut.IconLocation = 'C:\Windows\System32\imageres.dll,76'
$shortcut.Save()
Write-Output "Created $(Join-Path $desktop 'Loremaster.lnk')"
