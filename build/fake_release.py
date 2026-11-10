"""For the build machines: lay out a pretend GitHub release in a folder, to test the updater against.

Run: python build/fake_release.py INSTALLER VERSION FOLDER PORT
Writes FOLDER/latest.json (shaped like GitHub's "latest release" answer), the installer and SHA256SUMS.txt.
"""
import hashlib
import json
import os
import shutil
import sys

installer, version, folder, port = sys.argv[1:5]
os.makedirs(folder, exist_ok=True)
name = os.path.basename(installer)
shutil.copy(installer, os.path.join(folder, name))
sha = hashlib.sha256(open(installer, 'rb').read()).hexdigest()
with open(os.path.join(folder, 'SHA256SUMS.txt'), 'w') as fh:
    fh.write(f'{sha}  {name}\n')
url = f'http://127.0.0.1:{port}'
json.dump({'tag_name': f'v{version}', 'draft': False, 'prerelease': False,
           'assets': [{'name': name, 'size': os.path.getsize(installer), 'browser_download_url': f'{url}/{name}'},
                      {'name': 'SHA256SUMS.txt', 'browser_download_url': f'{url}/SHA256SUMS.txt'}]},
          open(os.path.join(folder, 'latest.json'), 'w'))
print(f'pretend release v{version} of {name} in {folder}')
