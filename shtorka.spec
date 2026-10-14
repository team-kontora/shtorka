# Builds dist\Shtorka, the folder the installer packs, and dist\Shtorka.exe, a single file
# that exists to move the copies installed before 1.0.3 over to the installer.
import re
import sys

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

sys.path.insert(0, SPECPATH)
from shtorka import __version__

numbers = tuple(int(part) for part in __version__.split(".")) + (0,)
version = VSVersionInfo(
    ffi=FixedFileInfo(filevers=numbers, prodvers=numbers),
    kids=[
        StringFileInfo([StringTable("040904B0", [
            StringStruct("CompanyName", "team-kontora"),
            StringStruct("FileDescription", "Shtorka"),
            StringStruct("FileVersion", __version__),
            StringStruct("InternalName", "Shtorka"),
            StringStruct("OriginalFilename", "Shtorka.exe"),
            StringStruct("ProductName", "Shtorka"),
            StringStruct("ProductVersion", __version__),
        ])]),
        VarFileInfo([VarStruct("Translation", [1033, 1200])]),
    ],
)

# parts of Qt that PyInstaller collects and the app never loads
UNUSED = re.compile(
    r"opengl32sw|Qt6Network|QtNetwork|Qt6Svg|translations"
    r"|plugins[\\/](generic|iconengines|imageformats|networkinformation|tls)"
    r"|plugins[\\/]platforms[\\/]q(direct2d|minimal|offscreen)",
    re.IGNORECASE,
)

a = Analysis(["run.pyw"], excludes=["PySide6.QtNetwork"])
a.binaries = [entry for entry in a.binaries if not UNUSED.search(entry[0])]
a.datas = [entry for entry in a.datas if not UNUSED.search(entry[0])]
pyz = PYZ(a.pure)
options = dict(name="Shtorka", console=False, icon="build/shtorka.ico", version=version)

EXE(pyz, a.scripts, a.binaries, a.datas, **options)

exe = EXE(pyz, a.scripts, exclude_binaries=True, **options)
COLLECT(exe, a.binaries, a.datas, name="Shtorka")
