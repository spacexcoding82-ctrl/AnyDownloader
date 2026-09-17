import asyncio
import time
from fastapi.testclient import TestClient
import pytest
from backend.main import app


@pytest.fixture
def client(monkeypatch):
    async def worker(self, payload, timeout, job=None):
        if payload['action'] == 'inspect':
            return {'title': 'Test video', 'platform': 'Test', 'duration': 3, 'thumbnail': None,
                    'formats': [{'key': '720', 'label': '720p', 'height': 720, 'container': 'mp4',
                                 'size_bytes': 10, 'has_audio': True}]}
        job.status = 'merging'
        await asyncio.sleep(0.02)
        (job.directory / 'video.mp4').write_bytes(b'test-video')
        return {'filename': 'video.mp4', 'size_bytes': 10}
    monkeypatch.setattr('backend.main.Manager.worker', worker)
    with TestClient(app) as client:
        client.get('/api/config')
        yield client


def inspect(client):
    response = client.post('/api/inspect', json={'url': 'https://example.com/video'})
    assert response.status_code == 200, response.text
    return response.json()['inspection_id']


def create(client, **overrides):
    return client.post('/api/download', json={'inspection_id': inspect(client), 'format_key': '720', 'rights_confirmed': True, **overrides})


def wait_job(client, key):
    for _ in range(100):
        data = client.get(f'/api/jobs/{key}').json()
        if data['status'] not in ('queued', 'downloading', 'merging'):
            return data
        time.sleep(0.01)
    pytest.fail('Job did not complete')


def test_complete_flow_single_save_and_cleanup(client):
    response = create(client)
    assert response.status_code == 202, response.text
    key = response.json()['job_id']
    assert wait_job(client, key)['status'] == 'ready'
    job = app.state.manager.jobs[key]
    response = client.get(f'/api/jobs/{key}/file')
    assert response.content == b'test-video'
    assert response.headers['content-disposition'] == 'attachment; filename="Test video.mp4"'
    assert not job.directory.exists()
    assert client.get(f'/api/jobs/{key}/file').status_code == 410


def test_confirmation_and_format_cannot_be_forged(client):
    assert create(client, rights_confirmed=False).status_code == 400
    assert create(client, format_key='best; rm -rf /').status_code == 400


def test_other_session_cannot_read_job_or_use_inspection(client):
    response = create(client)
    key = response.json()['job_id']
    token = inspect(client)
    client.cookies.clear()
    client.get('/api/config')
    assert client.get(f'/api/jobs/{key}').status_code == 404
    assert client.get(f'/api/jobs/{key}/file').status_code == 404
    assert client.post('/api/download', json={'inspection_id': token, 'format_key': '720', 'rights_confirmed': True}).status_code == 410


def test_url_validation_rate_limits_and_request_boundaries(client):
    assert client.post('/api/inspect', json={'url': 'http://127.0.0.1/secret'}).status_code == 400
    assert client.post('/api/inspect', json={'url': 'https://example.com'}, headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert client.post('/api/inspect', content='url=https://example.com', headers={'Content-Type': 'application/x-www-form-urlencoded'}).status_code == 415
    assert client.post('/api/inspect', content='x' * 9000, headers={'Content-Type': 'application/json'}).status_code == 413
    for _ in range(6):
        inspect(client)
    assert client.post('/api/inspect', json={'url': 'https://example.com/video'}).status_code == 429


def test_expiry_cleanup_leaves_active_transfers(client):
    key = create(client).json()['job_id']
    wait_job(client, key)
    job = app.state.manager.jobs[key]
    job.expires = time.monotonic() - 1
    job.transfers = 1
    app.state.manager.cleanup()
    assert job.directory.exists()
    job.transfers = 0
    app.state.manager.cleanup()
    assert not job.directory.exists()
    assert client.get(f'/api/jobs/{key}').status_code == 404


def test_daily_limit_does_not_depend_on_browser_cookie(client):
    manager = app.state.manager
    for _ in range(10):
        manager.rate(('day', 'same-ip'), 10, 86400)
    from backend.security import MediaError
    with pytest.raises(MediaError):
        manager.rate(('day', 'same-ip'), 10, 86400)


def test_cancel_releases_queue_and_files(client, monkeypatch):
    async def wait_worker(self, payload, timeout, job=None):
        await asyncio.sleep(300)
    token = inspect(client)
    monkeypatch.setattr('backend.main.Manager.worker', wait_worker)
    response = client.post('/api/download', json={'inspection_id': token, 'format_key': '720', 'rights_confirmed': True})
    key = response.json()['job_id']
    response = client.request('DELETE', f'/api/jobs/{key}', json={})
    assert response.status_code == 200
    assert client.get(f'/api/jobs/{key}').json()['status'] == 'cancelled'
    assert not app.state.manager.jobs[key].directory.exists()
