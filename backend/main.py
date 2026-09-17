import asyncio
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
import tempfile
import time

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import psutil

from .formats import MAX_BYTES, MAX_HEIGHT
from .security import MediaError, validate_url

ROOT = Path(__file__).resolve().parent.parent
LOG = logging.getLogger('viddl')
ACTIVE = {'queued', 'downloading', 'merging'}
TTL = 15 * 60


class InspectRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


class DownloadRequest(BaseModel):
    inspection_id: str = Field(max_length=64)
    format_key: str = Field(max_length=200)
    rights_confirmed: bool


@dataclass
class Job:
    id: str
    owner: str
    ip: str
    title: str
    directory: Path
    status: str = 'queued'
    progress: int | None = None
    downloaded_bytes: int = 0
    file: Path | None = None
    size_bytes: int = 0
    error: dict | None = None
    expires: float = field(default_factory=lambda: time.monotonic() + 1200)
    task: asyncio.Task | None = None
    transfers: int = 0
    claimed: bool = False


def kill_tree(pid):
    with suppress(psutil.NoSuchProcess):
        parent = psutil.Process(pid)
        for process in reversed(parent.children(recursive=True)):
            with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                process.kill()
        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
            parent.kill()


def disk_bytes(directory):
    total = 0
    for path in directory.glob('**/*'):
        with suppress(OSError):
            if path.is_file():
                total += path.stat().st_size
    return total


class Manager:
    def __init__(self):
        self.directory = Path(tempfile.mkdtemp(prefix='viddl-')).resolve()
        self.jobs = {}
        self.inspections = {}
        self.rates = {}
        self.salt = secrets.token_bytes(32)
        # Render Free has a small shared memory budget. Inspection and processing
        # must not each launch a full-size worker at the same time.
        self.inspector = self.downloader = asyncio.Semaphore(1)
        self.inspect_waiting = 0
        self.processes = set()

    def ip_key(self, request):
        # Trust proxy headers only at the server boundary, never parse arbitrary XFF here.
        value = request.client.host if request.client else 'unknown'
        return hashlib.sha256(self.salt + value.encode()).hexdigest()

    def rate(self, key, limit, window):
        now = time.monotonic()
        count, reset = self.rates.get(key, (0, now + window))
        if now >= reset:
            count, reset = 0, now + window
        if count >= limit:
            raise MediaError('rate_limited', 'You have reached the free request limit. Please try again later.')
        if key not in self.rates and len(self.rates) >= 10000:
            raise MediaError('busy', 'The service is busy. Please try again later.')
        self.rates[key] = (count + 1, reset)

    def remove_directory(self, directory):
        resolved = directory.resolve()
        if resolved.parent == self.directory and resolved != self.directory:
            shutil.rmtree(resolved, ignore_errors=True)

    def cleanup(self):
        now = time.monotonic()
        self.inspections = {k: v for k, v in self.inspections.items() if v['expires'] > now}
        self.rates = {k: v for k, v in self.rates.items() if v[1] > now}
        for key, job in list(self.jobs.items()):
            if job.expires < now and job.status not in ACTIVE and not job.transfers:
                self.remove_directory(job.directory)
                del self.jobs[key]

    async def worker(self, payload, timeout, job=None):
        env = os.environ.copy()
        for key in list(env):
            if key.lower().endswith('_proxy'):
                del env[key]
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'backend.worker', cwd=ROOT, env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=256 * 1024,
        )
        self.processes.add(process.pid)
        monitor = None

        async def watch():
            while process.returncode is None:
                await asyncio.sleep(0.4)
                if job:
                    # Merging needs space for inputs and output at once.
                    if disk_bytes(job.directory) > MAX_BYTES * 2 + 8_000_000:
                        raise MediaError('too_large', 'This file exceeds the free 500 MB limit.')
                with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                    proc = psutil.Process(process.pid)
                    memory = proc.memory_info().rss
                    for child in proc.children(recursive=True):
                        with suppress(psutil.NoSuchProcess, psutil.AccessDenied):
                            memory += child.memory_info().rss
                    if memory > 320 * 1024 * 1024:
                        raise MediaError('resource_limit', 'This video needs more memory than the free service allows. Try a smaller quality.')

        async def read():
            result = None
            while line := await process.stdout.readline():
                message = json.loads(line)
                if message['event'] == 'error':
                    raise MediaError(message['code'], message['message'])
                if message['event'] == 'result':
                    result = message['data']
                if message['event'] == 'progress' and job:
                    job.status = message['status']
                    value = message.get('progress')
                    job.progress = max(job.progress or 0, value) if value is not None else job.progress
                    job.downloaded_bytes = message.get('downloaded_bytes', job.downloaded_bytes)
            await process.wait()
            if process.returncode or result is None:
                raise MediaError('download_failed', 'The download could not be completed. Please try again.')
            return result

        reader = None
        try:
            process.stdin.write(json.dumps(payload).encode() + b'\n')
            await process.stdin.drain()
            process.stdin.close()
            monitor = asyncio.create_task(watch())
            reader = asyncio.create_task(read())
            done, pending = await asyncio.wait([reader, monitor], timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                raise MediaError('timeout', 'The request took too long. Try a smaller video or try again later.')
            if monitor in done and monitor.exception():
                raise monitor.exception()
            return await reader
        finally:
            if process.returncode is None:
                kill_tree(process.pid)
            await process.wait()
            self.processes.discard(process.pid)
            for task in (reader, monitor):
                if task:
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task

    async def perform(self, job, inspection, choice):
        try:
            async with self.downloader:
                ready_bytes = sum(j.size_bytes for j in self.jobs.values() if j.status == 'ready')
                if ready_bytes + MAX_BYTES > 1_000_000_000:
                    raise MediaError('busy', 'Temporary storage is full. Save a ready file or try again in a few minutes.')
                job.status = 'downloading'
                result = await self.worker({'action': 'download', 'url': inspection['url'],
                    'choice': choice, 'directory': str(job.directory)}, 600, job)
                path = (job.directory / result['filename']).resolve()
                if path.parent != job.directory or not path.is_file() or path.stat().st_size > MAX_BYTES:
                    raise MediaError('invalid_file', 'The download could not be completed safely.')
                job.file, job.size_bytes = path, path.stat().st_size
                job.status, job.progress = 'ready', 100
        except asyncio.CancelledError:
            job.status = 'cancelled'
            self.remove_directory(job.directory)
            raise
        except MediaError as error:
            job.status, job.error = 'failed', {'code': error.code, 'message': str(error)}
            self.remove_directory(job.directory)
        except Exception:
            LOG.exception('Download worker failed (no source URL logged)')
            job.status, job.error = 'failed', {'code': 'server_error', 'message': 'The service could not finish this video. Please try again.'}
            self.remove_directory(job.directory)
        finally:
            job.expires = time.monotonic() + TTL


def owner(request):
    token = request.cookies.get('viddl_session', '')
    if not re.fullmatch('[a-f0-9]{64}', token):
        raise MediaError('session_required', 'Refresh the page to start a download session.')
    return token


@asynccontextmanager
async def lifespan(app):
    manager = Manager()
    app.state.manager = manager

    async def clean():
        while True:
            await asyncio.sleep(30)
            manager.cleanup()

    task = asyncio.create_task(clean())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        jobs = [job.task for job in manager.jobs.values() if job.task and not job.task.done()]
        for item in jobs:
            item.cancel()
        await asyncio.gather(*jobs, return_exceptions=True)
        for pid in list(manager.processes):
            kill_tree(pid)
        # This exact directory was created by this lifespan, never supplied by a request.
        shutil.rmtree(manager.directory, ignore_errors=True)


app = FastAPI(title='VidDL', lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(MediaError)
async def media_error(request, error):
    status = {'rate_limited': 429, 'busy': 503, 'not_found': 404,
              'expired': 410, 'session_required': 401, 'not_ready': 409,
              'already_active': 409, 'already_saved': 410}.get(error.code, 400)
    headers = {'Retry-After': '60'} if status in (429, 503) else {}
    return JSONResponse({'error': {'code': error.code, 'message': str(error)}}, status_code=status, headers=headers)


@app.middleware('http')
async def headers(request, call_next):
    # JSON APIs are same-origin; browser cross-site form requests are not accepted.
    if request.url.path.startswith('/api/'):
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'error': {'code': 'cross_origin', 'message': 'Open VidDL directly to download.'}}, status_code=403)
        if request.method in ('POST', 'DELETE'):
            if 'application/json' not in request.headers.get('content-type', ''):
                return JSONResponse({'error': {'code': 'invalid_request', 'message': 'Expected a JSON request.'}}, status_code=415)
            try:
                if int(request.headers.get('content-length', '0')) > 8192:
                    return Response(status_code=413)
            except ValueError:
                return Response(status_code=400)
            # Bound chunked bodies too; Pydantic runs only after this limit.
            body = b''
            async for chunk in request.stream():
                body += chunk
                if len(body) > 8192:
                    return Response(status_code=413)
            request._body = body
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    else:
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    return response


@app.get('/api/health')
async def health():
    location = os.environ.get('FFMPEG_LOCATION')
    suffix = '.exe' if os.name == 'nt' else ''
    ready = all((Path(location) / f'{name}{suffix}').is_file() if location else shutil.which(name)
                for name in ('ffmpeg', 'ffprobe'))
    return JSONResponse({'status': 'ok' if ready else 'setup_required', 'media_tools': bool(ready)}, status_code=200 if ready else 503)


@app.get('/api/config')
async def config(request: Request, response: Response):
    token = request.cookies.get('viddl_session', '')
    if not re.fullmatch('[a-f0-9]{64}', token):
        response.set_cookie('viddl_session', secrets.token_hex(32), httponly=True,
                            secure=os.getenv('RENDER') == 'true', samesite='strict', max_age=86400)
    return {'max_height': MAX_HEIGHT, 'max_bytes': MAX_BYTES, 'downloads_per_day': 10,
            'retention_minutes': 15, 'containers': ['mp4', 'webm']}


@app.post('/api/inspect')
async def inspect_video(data: InspectRequest, request: Request):
    session = owner(request)
    url = validate_url(data.url)
    manager = request.app.state.manager
    manager.cleanup()
    ip = manager.ip_key(request)
    manager.rate(('inspect_minute', ip), 6, 60)
    manager.rate(('inspect_hour', ip), 30, 3600)
    if manager.inspect_waiting >= 3 or len(manager.inspections) >= 128:
        raise MediaError('busy', 'The video checker is busy. Please try again in a moment.')
    manager.inspect_waiting += 1
    try:
        async with asyncio.timeout(45):
            async with manager.inspector:
                result = await manager.worker({'action': 'inspect', 'url': url}, 30)
    except TimeoutError:
        raise MediaError('busy', 'The video checker is busy. Please try again in a moment.') from None
    finally:
        manager.inspect_waiting -= 1
    key = secrets.token_hex(16)
    manager.inspections[key] = {**result, 'url': url, 'owner': session, 'expires': time.monotonic() + TTL}
    return {'inspection_id': key, **result, 'expires_in': TTL}


@app.post('/api/download', status_code=202)
async def download_video(data: DownloadRequest, request: Request):
    session = owner(request)
    manager = request.app.state.manager
    manager.cleanup()
    inspection = manager.inspections.get(data.inspection_id)
    if not inspection or inspection['owner'] != session:
        raise MediaError('expired', 'This video check expired. Paste the link again.')
    if not data.rights_confirmed:
        raise MediaError('permission_required', 'Confirm you own this video or have permission to download it.')
    choice = next((f for f in inspection['formats'] if f['key'] == data.format_key), None)
    if not choice:
        raise MediaError('invalid_format', 'Choose one of this video’s available qualities.')
    ip = manager.ip_key(request)
    if any(j.status in ACTIVE and j.ip == ip for j in manager.jobs.values()):
        raise MediaError('already_active', 'You already have a video processing. Wait for it to finish or cancel it.')
    if sum(j.status in ACTIVE for j in manager.jobs.values()) >= 4 or len(manager.jobs) >= 128:
        raise MediaError('busy', 'The download queue is full. Please try again in a moment.')
    if sum(j.size_bytes for j in manager.jobs.values() if j.status == 'ready') >= 1_000_000_000:
        raise MediaError('busy', 'Temporary storage is full. Please try again in a few minutes.')
    manager.rate(('download_day', ip), 10, 86400)
    key = secrets.token_hex(16)
    directory = manager.directory / key
    directory.mkdir()
    job = Job(key, session, ip, inspection['title'], directory)
    manager.jobs[key] = job
    job.task = asyncio.create_task(manager.perform(job, inspection, choice))
    return {'job_id': key, 'status': 'queued'}


def find_job(request, key):
    manager = request.app.state.manager
    manager.cleanup()
    job = manager.jobs.get(key)
    if not job or job.owner != owner(request):
        raise MediaError('not_found', 'This download expired or no longer exists. Check the video link again.')
    return job


@app.get('/api/jobs/{key}')
async def get_job(key: str, request: Request):
    job = find_job(request, key)
    return {'job_id': job.id, 'status': job.status, 'progress': job.progress,
            'downloaded_bytes': job.downloaded_bytes, 'size_bytes': job.size_bytes,
            'error': job.error, 'expires_in': max(0, int(job.expires - time.monotonic())),
            'file_url': f'/api/jobs/{key}/file' if job.status == 'ready' else None}


@app.delete('/api/jobs/{key}')
async def cancel_job(key: str, request: Request):
    job = find_job(request, key)
    if job.task and not job.task.done():
        job.task.cancel()
        with suppress(asyncio.CancelledError):
            await job.task
    if not job.transfers:
        request.app.state.manager.remove_directory(job.directory)
    job.status, job.expires = 'cancelled', time.monotonic() + TTL
    return {'status': 'cancelled'}


@app.get('/api/jobs/{key}/file')
async def get_file(key: str, request: Request):
    job = find_job(request, key)
    if job.claimed:
        raise MediaError('already_saved', 'This file was already sent. Start another download if you need it again.')
    if job.status != 'ready' or not job.file or not job.file.is_file():
        raise MediaError('not_ready', 'Your video is not ready to save yet.')
    job.claimed, job.transfers = True, 1
    filename = re.sub(r'[^\w .-]', '', job.title, flags=re.ASCII).strip(' .')[:100] or 'video'
    filename += job.file.suffix

    async def chunks():
        try:
            with job.file.open('rb') as handle:
                while chunk := await asyncio.to_thread(handle.read, 64 * 1024):
                    yield chunk
        finally:
            job.transfers = 0
            job.status = 'saved'
            request.app.state.manager.remove_directory(job.directory)

    return StreamingResponse(chunks(), media_type='video/webm' if job.file.suffix == '.webm' else 'video/mp4',
        headers={'Content-Disposition': f'attachment; filename="{filename}"', 'Content-Length': str(job.size_bytes)})


client = ROOT / 'frontend' / 'dist' / 'client'
if client.is_dir():
    app.mount('/', StaticFiles(directory=client, html=True), name='frontend')
else:
    @app.get('/')
    async def missing_build():
        return JSONResponse({'message': 'Frontend not built. Run npm run build in frontend, or open the Vite dev server.'}, status_code=503)
