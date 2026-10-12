# Builds dist\Shtorka.exe: a single file that runs without Python installed.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = ".venv\Scripts\python.exe"
& $python -m pip install --quiet --disable-pip-version-check -r requirements.txt pyinstaller
if ($LASTEXITCODE) { throw "pip failed" }

New-Item -ItemType Directory -Force build | Out-Null
& $python -c "from PySide6.QtWidgets import QApplication; from shtorka.app import _icon; app = QApplication([]); assert _icon().pixmap(256, 256).save('build/shtorka.ico')"
if ($LASTEXITCODE) { throw "icon failed" }

& $python -m PyInstaller --noconfirm --clean --onefile --noconsole --name Shtorka --icon (Resolve-Path build\shtorka.ico) --specpath build run.pyw
if ($LASTEXITCODE) { throw "PyInstaller failed" }

Get-Item dist\Shtorka.exe | Select-Object Name, @{ n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
