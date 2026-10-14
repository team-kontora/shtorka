# Builds dist\ShtorkaSetup.exe (the installer) and dist\Shtorka.exe (a single file for copies older than 1.0.3).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# the project venv locally, the Python set up by the workflow in CI
$python = if (Test-Path .venv\Scripts\python.exe) { ".venv\Scripts\python.exe" } else { "python" }
& $python -m pip install --quiet --disable-pip-version-check -r requirements.txt -r requirements-build.txt
if ($LASTEXITCODE) { throw "pip failed" }

New-Item -ItemType Directory -Force build | Out-Null
& $python -c "from PySide6.QtWidgets import QApplication; from shtorka.app import _icon; app = QApplication([]); assert _icon().pixmap(256, 256).save('build/shtorka.ico')"
if ($LASTEXITCODE) { throw "icon failed" }

& $python -m PyInstaller --noconfirm --clean --log-level WARN shtorka.spec
if ($LASTEXITCODE) { throw "PyInstaller failed" }

# Inno Setup: winget install JRSoftware.InnoSetup
$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $iscc = "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" |
        Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) { throw "Inno Setup is not installed" }
$version = & $python -c "import shtorka; print(shtorka.__version__)"
& $iscc /Qp "/DVersion=$version" installer.iss
if ($LASTEXITCODE) { throw "Inno Setup failed" }

Get-Item dist\ShtorkaSetup.exe, dist\Shtorka.exe | Select-Object Name, @{ n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
