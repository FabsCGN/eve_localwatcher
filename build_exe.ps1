# Builds a standalone Flint Local Watcher.exe (no Python needed to run it).
#
#   PowerShell:  .\build_exe.ps1
#
# Output: dist\Flint Local Watcher.exe
# Note: Tesseract is NOT bundled (it's a separate program). The app auto-detects
# it at the standard install path — see README.

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host "Installiere/aktualisiere Build- und Laufzeit-Abhängigkeiten..."
python -m pip install --upgrade pyinstaller
python -m pip install -r requirements.txt

# Icon: uses icon.ico if present (drop in your own to replace the placeholder).
$iconArg = @()
if (Test-Path "icon.ico") { $iconArg = @("--icon", "icon.ico") }

Write-Host "Baue die .exe (das kann 1-2 Minuten dauern)..."
# Filename has no apostrophe (it breaks PyInstaller's generated .spec); the
# window title still reads "Mister Lee's magischer Intelligentheit-Helfer".
python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "Mister Lees magischer Intelligentheit-Helfer" `
    --hidden-import win32gui `
    --hidden-import win32api `
    --collect-submodules mss `
    --collect-all sv_ttk `
    --add-data "eve_localwatcher\data\weapon_ranges.json;eve_localwatcher/data" `
    --add-data "eve_localwatcher\data\map_graph.json;eve_localwatcher/data" `
    @iconArg `
    run.py

Write-Host ""
Write-Host "Fertig. Die ausführbare Datei liegt unter:" -ForegroundColor Green
Write-Host "    dist\Mister Lees magischer Intelligentheit-Helfer.exe"
Write-Host "Diese .exe kannst du frei verschieben (z. B. auf den Desktop) und per Doppelklick starten."
