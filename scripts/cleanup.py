import shutil
from pathlib import Path

def remove_pycache():
    for path in Path('.').rglob('__pycache__'):
        shutil.rmtree(path)
    print("Removed all __pycache__ directories")