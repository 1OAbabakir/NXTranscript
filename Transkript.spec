# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_data_files


ttkbootstrap_datas = collect_data_files('ttkbootstrap')
ffmpeg_datas, ffmpeg_binaries, ffmpeg_hiddenimports = collect_all('imageio_ffmpeg')


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=ffmpeg_binaries,
    datas=[
        ('transkript-logo-transparent.png', '.'),
    ] + ttkbootstrap_datas + ffmpeg_datas,
    hiddenimports=ffmpeg_hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name='Transkript',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['transkript-logo-transparent.ico'],
)
