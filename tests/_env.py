"""Run the tests against a fresh, empty data folder, with the program's code on the path.

Works from the GitHub repository (app/, screener/ and playbook/ side by side) and from the project folder
(laptop-app/app, with screener/ and playbook/ one level up)."""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = os.path.dirname(HERE)
ROOT = TOP if os.path.isdir(os.path.join(TOP, 'screener')) else os.path.dirname(TOP)
APP = os.path.join(TOP, 'app')
os.environ.setdefault('STOCK_ROOT', ROOT)
os.environ.setdefault('STOCK_DATA', tempfile.mkdtemp(prefix='stock-test-data-'))
os.environ['STOCK_NO_FIRST_DOWNLOAD'] = '1'
for p in (APP, os.path.join(ROOT, 'screener', 'code'), os.path.join(ROOT, 'playbook', 'code')):
    if p not in sys.path:
        sys.path.insert(0, p)
