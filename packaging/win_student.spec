# British English comments.
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
block_cipher = None

pyside6_datas  = collect_data_files("PySide6", includes=["**/*"])
pyside6_hidden = collect_submodules("PySide6")

# Bundle Tectonic into the app; CI will download it into vendor/...
binaries = [
    ("vendor/tectonic/windows-x86_64/tectonic.exe", "tectonic/windows-x86_64"),
]

a = Analysis(
    ["apps/student_app/main.py"],
    pathex=[],
    binaries=binaries,
    datas=pyside6_datas,
    hiddenimports=pyside6_hidden,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Paperforge Student",
    console=False,   # GUI app
    icon=None,       # add assets/icons/student.ico when available
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="Paperforge Student"
)
