"""Exercise the actual HTTP API against MDN's downloadable flower example."""
import argparse
import json
from pathlib import Path
import time
import httpx

parser = argparse.ArgumentParser()
parser.add_argument('--base-url', default='http://127.0.0.1:8000')
parser.add_argument('--url', default='https://developer.mozilla.org/shared-assets/videos/flower.mp4')
args = parser.parse_args()

with httpx.Client(base_url=args.base_url, timeout=75, trust_env=False) as client:
    print('Health:', client.get('/api/health').json(), flush=True)
    client.get('/api/config').raise_for_status()
    response = client.post('/api/inspect', json={'url': args.url})
    print('Inspection:', response.status_code, response.text, flush=True)
    response.raise_for_status()
    info = response.json()
    selected = info['formats'][0]
    response = client.post('/api/download', json={'inspection_id': info['inspection_id'], 'format_key': selected['key'], 'rights_confirmed': True})
    response.raise_for_status()
    job = response.json()
    previous = None
    for _ in range(180):
        response = client.get('/api/jobs/' + job['job_id'])
        response.raise_for_status()
        result = response.json()
        if result['status'] != previous:
            print('Job:', result['status'], result.get('error'), flush=True)
            previous = result['status']
        if result['status'] == 'ready':
            break
        if result['status'] in ('failed', 'cancelled'):
            raise RuntimeError(result)
        time.sleep(1)
    else:
        raise RuntimeError('Download timed out')
    response = client.get(result['file_url'])
    response.raise_for_status()
    assert len(response.content) == result['size_bytes'] and len(response.content) > 1000
    output = Path(__file__).resolve().parent.parent / '.cache' / 'smoke-video.mp4'
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(response.content)
    assert client.get(result['file_url']).status_code == 410
    print(json.dumps({'result': 'passed', 'bytes': len(response.content), 'quality': selected['label'], 'file': str(output)}), flush=True)
