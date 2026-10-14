# Tags the pushed commit with the current version; the Release workflow builds the installer from it and publishes it.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$version = & .venv\Scripts\python.exe -c "import shtorka; print(shtorka.__version__)"
$tag = "v$version"

# the tag is put on the pushed commit, so it has to be the one the installer is built from
if (git status --porcelain) { throw "commit your changes first" }
git fetch --quiet --tags origin
if ((git rev-parse HEAD) -ne (git rev-parse origin/main)) { throw "push to origin/main first" }
if (git tag --list $tag) { throw "tag $tag already exists: raise __version__ in shtorka\__init__.py" }

git tag $tag
git push origin $tag
if ($LASTEXITCODE) { throw "git push failed" }
"Release $tag is being built: https://github.com/team-kontora/shtorka/actions/workflows/release.yml"
