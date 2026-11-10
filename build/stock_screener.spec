# PyInstaller recipe for the Stock Screener app (run from the repository root: pyinstaller build/stock_screener.spec).
# Two programs share one folder: "StockScreener" (the launcher, no text window) and "stockscreener-worker" (the
# program itself and the screener's scripts; it has a text window, which the launcher keeps hidden).
import glob
import os
import sys

from PyInstaller.utils.hooks import collect_all, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))
CODE_DIRS = [os.path.join(ROOT, 'app'), os.path.join(ROOT, 'screener', 'code'), os.path.join(ROOT, 'playbook', 'code')]

datas, binaries, hiddenimports = [], [], []
for pkg in ('streamlit', 'altair', 'yfinance', 'curl_cffi', 'pymupdf', 'certifi'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
for pkg in ('streamlit', 'altair', 'pandas', 'numpy', 'pyarrow', 'yfinance', 'pymupdf', 'certifi', 'requests', 'packaging'):
    datas += copy_metadata(pkg)

# the program's own code runs as plain files (the screener's scripts are started by path), but everything they import
# must be in the app: so all of it is analysed here too
for d in CODE_DIRS:
    hiddenimports += [os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(d, '*.py'))]
hiddenimports += ['views.' + os.path.splitext(os.path.basename(f))[0]
                  for f in glob.glob(os.path.join(ROOT, 'app', 'views', '*.py')) if not f.endswith('__init__.py')]
hiddenimports = sorted(set(hiddenimports) - {'desktop', 'app', 'eodhd_test', 'launch'})


def tree(src, dst):
    out = []
    for d, dirs, files in os.walk(src):
        dirs[:] = [x for x in dirs if x != '__pycache__']
        for f in files:
            if not f.endswith('.pyc'):
                out.append((os.path.join(d, f), os.path.join(dst, os.path.relpath(d, src))))
    return out


datas += tree(os.path.join(ROOT, 'app'), 'app') + tree(os.path.join(ROOT, 'screener'), 'screener') \
    + tree(os.path.join(ROOT, 'playbook'), 'playbook')

a = Analysis([os.path.join(ROOT, 'app', 'desktop.py')], pathex=CODE_DIRS, datas=datas, binaries=binaries,
             hiddenimports=hiddenimports, excludes=['pytest', 'IPython', 'matplotlib'], noarchive=False)
pyz = PYZ(a.pure)
mac = sys.platform == 'darwin'
icon = os.path.join(ROOT, 'app', 'icons', 'icon.icns' if mac else 'icon.ico')
options = [('X utf8_mode=1', None, 'OPTION')]

launcher = EXE(pyz, a.scripts, options, exclude_binaries=True, name='StockScreener', console=False, icon=icon,
               upx=False)
worker = EXE(pyz, a.scripts, options, exclude_binaries=True, name='stockscreener-worker', console=True, icon=icon,
             upx=False)
coll = COLLECT(launcher, worker, a.binaries, a.datas, name='StockScreener', upx=False)

if mac:
    app = BUNDLE(coll, name='Stock Screener.app', icon=icon, bundle_identifier='local.stockscreener',
                 info_plist={'CFBundleName': 'Stock Screener', 'CFBundleDisplayName': 'Stock Screener',
                             'CFBundleShortVersionString': os.environ.get('APP_VERSION_SHORT', '1.0'),
                             'NSHighResolutionCapable': True, 'LSMinimumSystemVersion': '12.0',
                             # the window is the browser's: the launcher itself needs no Dock icon
                             'LSUIElement': True})
