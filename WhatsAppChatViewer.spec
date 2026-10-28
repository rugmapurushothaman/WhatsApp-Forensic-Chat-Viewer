
# WhatsAppChatViewer.spec

from PyInstaller.utils.hooks import collect_all

# Collect Streamlit and its runtime resources.
streamlit_datas, streamlit_binaries, streamlit_hiddenimports = (
    collect_all("streamlit")
)

# Collect pywebview and its runtime resources.
webview_datas, webview_binaries, webview_hiddenimports = (
    collect_all("webview")
)

# Collect pandas, commonly used by the chat viewer for data handling.
pandas_datas, pandas_binaries, pandas_hiddenimports = (
    collect_all("pandas")
)

datas = (
    streamlit_datas
    + webview_datas
    + pandas_datas
    + [("app.py", ".")]
)

binaries = (
    streamlit_binaries
    + webview_binaries
    + pandas_binaries
)

hiddenimports = list(set(
    streamlit_hiddenimports
    + webview_hiddenimports
    + pandas_hiddenimports
))

a = Analysis(
    ["WhatsAppChatViewer.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="WhatsAppChatViewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
