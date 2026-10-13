# Builds the exe and publishes it as a GitHub release; installed copies update themselves from it.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = & .venv\Scripts\python.exe -c "import shtorka; print(shtorka.__version__)"
$tag = "v$version"

# the tag is put on the pushed commit, so it has to be the one the exe is built from
if (git status --porcelain) { throw "commit your changes first" }
git fetch --quiet origin
if ((git rev-parse HEAD) -ne (git rev-parse origin/main)) { throw "push to origin/main first" }
if ((gh release list --json tagName --jq ".[].tagName") -contains $tag) {
    throw "release $tag already exists: raise __version__ in shtorka\__init__.py"
}

.\build.ps1
gh release create $tag dist\Shtorka.exe --title "Shtorka $version" --generate-notes
if ($LASTEXITCODE) { throw "gh release failed" }
