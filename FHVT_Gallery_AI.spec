# -*- mode: python ; coding: utf-8 -*-


from PyInstaller.utils.hooks import collect_submodules, copy_metadata

hidden_imports = []
hidden_imports += collect_submodules('mcubes')
hidden_imports += collect_submodules('pymcubes')
hidden_imports += collect_submodules('trimesh')
hidden_imports += collect_submodules('rembg')
hidden_imports += collect_submodules('onnxruntime')
hidden_imports += collect_submodules('cv2')
hidden_imports += collect_submodules('pooch')
hidden_imports += collect_submodules('pymatting')
hidden_imports += collect_submodules('hf_xet')
hidden_imports += collect_submodules('hf_transfer')

datas = [('assets', 'assets')]
datas += copy_metadata('hf_xet')
datas += copy_metadata('huggingface_hub')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FHVT_Gallery_AI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FHVT_Gallery_AI',
)
