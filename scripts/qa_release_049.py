"""Check the compiled update UI and API without requesting a Store install."""
import argparse
import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', default='http://127.0.0.1:5559')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    def read(path, method='GET', origin=None):
        request = urllib.request.Request(args.url + path, method=method,
            headers={'Origin': origin or args.url})
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()

    assert json.loads(read('/api/instance'))['version'] == '0.4.9'
    status = json.loads(read('/api/store-updates/status'))
    assert status == {'version': '0.4.9', 'packaged': False, 'previous_update': None}, status
    progress = json.loads(read('/api/store-updates/progress'))
    assert progress == {'busy': False, 'state': 'idle', 'percent': None}, progress
    for name in ['store-updates.js', 'i18n.js', 'index.html', 'styles.css']:
        packaged = read('/static/' + name)
        assert hashlib.sha256(packaged).digest() == hashlib.sha256((root / 'static' / name).read_bytes()).digest(), name
    for path, origin, expected in [('/api/store-updates/check', None, 503),
                                    ('/api/store-updates/install', 'https://untrusted.example', 403)]:
        try:
            read(path, 'POST', origin)
        except urllib.error.HTTPError as error:
            assert error.code == expected
        else:
            raise AssertionError(path + ' unexpectedly succeeded')
    print(json.dumps({'version': status['version'], 'packagedResourcesMatchSource': True,
                      'progressEndpoint': True, 'sourceAndOriginGuards': True,
                      'storeInstallationRequested': False}))


if __name__ == '__main__':
    main()
