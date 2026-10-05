"""Read-only HTTP gate for the product's current, authenticated API."""
import json
import os
import urllib.error
import urllib.request


def main():
    base = 'http://127.0.0.1:8000'
    token = os.environ.get('TOKEN')
    if not token:
        raise SystemExit('BLOCKED: authenticated HTTP gate requires TOKEN')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path, key in (('/cloud/projects', 'projects'), ('/cloud/executions', 'executions'),
                      ('/providers/catalog', 'providers')):
        request = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + token})
        with opener.open(request, timeout=10) as response:
            data = json.load(response)
            if response.status != 200 or not isinstance(data.get(key), list):
                raise SystemExit('FAIL: API contract mismatch at ' + path)
        try:
            opener.open(base + path, timeout=10).close()
        except urllib.error.HTTPError as error:
            if error.code != 401:
                raise SystemExit('FAIL: unauthenticated status mismatch at ' + path)
        else:
            raise SystemExit('FAIL: API allowed an unauthenticated request at ' + path)
    print('PASS: current authenticated API and unauthenticated rejection')


if __name__ == '__main__':
    main()
