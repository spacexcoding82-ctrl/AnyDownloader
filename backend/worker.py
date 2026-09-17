"""Isolated, killable extraction worker. JSON in; bounded JSON events out."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from .formats import MAX_BYTES, build_formats
from .security import MediaError, install_network_guard, validate_url


def emit(event, **data):
    print(json.dumps({'event': event, **data}, ensure_ascii=True), flush=True)


class QuietLogger:
    def debug(self, message):
        pass

    warning = debug
    error = debug


def public_error(error):
    if isinstance(error, MediaError):
        return error.code, str(error)
    message = str(error).lower()
    if any(s in message for s in ('sign in', 'log in', 'login', 'cookies', 'private video', 'authentication')):
        return 'login_required', 'This platform requires a login or blocked this request. Try another public video.'
    if 'drm' in message:
        return 'protected_video', 'This video is protected and cannot be downloaded.'
    if 'unsupported url' in message:
        return 'unsupported_url', 'This link is not supported. Use a direct link to a public video.'
    if any(s in message for s in ('429', '403', 'blocked', 'bot', 'forbidden')):
        return 'platform_blocked', 'The platform blocked this request. Please try later or use its official download option.'
    if 'too large' in message or 'max-filesize' in message:
        return 'too_large', 'This file exceeds the free 500 MB limit. Choose a smaller quality.'
    if 'timed out' in message:
        return 'timeout', 'The platform took too long to respond. Please try again.'
    return 'extraction_failed', 'Could not read this video. It may be unavailable, restricted, or temporarily unsupported.'


def make_downloader(progress=None):
    import yt_dlp
    from yt_dlp.networking._urllib import UrllibRH
    from yt_dlp.downloader.external import ExternalFD

    def reject_external(*args, **kwargs):
        raise MediaError('unsupported_stream', 'This stream requires an unsupported download method.')

    # An HLS extractor can fall back to FFmpeg even with hls_prefer_native.
    # Forbid that escape route: network IO must stay behind the socket guard.
    ExternalFD.real_download = reject_external
    params = {
        'quiet': True, 'no_warnings': True, 'logger': QuietLogger(),
        'noplaylist': True, 'playlistend': 1, 'skip_download': True,
        'socket_timeout': 12, 'retries': 1, 'fragment_retries': 1,
        'extractor_retries': 1, 'cachedir': False, 'proxy': '',
        'enable_file_urls': False, 'usenetrc': False,
        'geo_bypass': False, 'external_downloader': 'native',
        'hls_prefer_native': True, 'concurrent_fragment_downloads': 1,
        'max_filesize': MAX_BYTES, 'buffersize': 64 * 1024,
        'http_chunk_size': 4 * 1024 * 1024, 'noprogress': True,
        'js_runtimes': {'node': {}}, 'remote_components': [],
        'postprocessor_args': {'ffmpeg_i': ['-protocol_whitelist', 'file,crypto,data'],
                               'ffmpeg_o': ['-threads', '1']},
    }
    if os.environ.get('FFMPEG_LOCATION'):
        params['ffmpeg_location'] = os.environ['FFMPEG_LOCATION']
    if progress:
        params['progress_hooks'] = [progress]
        params['postprocessor_hooks'] = [lambda d: emit('progress', status='merging', progress=96)]
    downloader = yt_dlp.YoutubeDL(params)
    # Explicitly retain only the Python HTTP implementation covered by the guard.
    downloader._request_director = downloader.build_request_director([UrllibRH])
    return downloader


def verify_file(path: Path):
    streams = probe_file(path).get('streams', [])
    videos = [s for s in streams if s.get('codec_type') == 'video']
    if not videos or any(not s.get('width') or not s.get('height') or min(s['width'], s['height']) > 1080 for s in videos):
        raise MediaError('quality_limit', 'This stream exceeds the 1080p limit or has no valid video track.')


def probe_file(path: Path):
    location = os.environ.get('FFMPEG_LOCATION')
    probe = str(Path(location) / ('ffprobe.exe' if os.name == 'nt' else 'ffprobe')) if location else shutil.which('ffprobe')
    if not probe or not Path(probe).is_file():
        raise MediaError('server_setup', 'The download service is missing its media tools.')
    result = subprocess.run([
        probe, '-v', 'error', '-protocol_whitelist', 'file,crypto,data',
        '-show_entries', 'stream=codec_type,codec_name,width,height:format=duration', '-of', 'json', str(path),
    ], capture_output=True, text=True, timeout=20, check=False)
    if result.returncode:
        raise MediaError('invalid_media', 'The downloaded file could not be verified as a video.')
    return json.loads(result.stdout)


def enrich_direct_video(ydl, info):
    """Probe at most 8 MB from a direct MP4/WebM, without handing a URL to FFmpeg.

    Range reads cover both fast-start and tail-moov MP4s. Unknown quality is never
    guessed. Sparse local files keep the full-file offsets intact for ffprobe.
    """
    from yt_dlp.networking import Request
    if info.get('_type') in ('playlist', 'multi_video') or 'entries' in info:
        return
    formats = info.get('formats') or [info]
    for item in formats:
        if item.get('height') or item.get('protocol') not in ('http', 'https') or item.get('ext') not in ('mp4', 'webm'):
            continue
        # Only the generic direct-file extractor needs this. Avoid probing every
        # adaptive format from a platform that failed to report its dimensions.
        if str(info.get('extractor_key', '')).lower() != 'generic':
            continue
        url = validate_url(item['url'])
        chunk_size = 4 * 1024 * 1024
        headers = {**info.get('http_headers', {}), 'Range': f'bytes=0-{chunk_size - 1}'}
        with tempfile.TemporaryDirectory(prefix='viddl-probe-') as temp:
            path = Path(temp) / f"probe.{item['ext']}"
            with ydl.urlopen(Request(url, headers=headers)) as response:
                content_range = response.headers.get('Content-Range', '')
                total = content_range.rsplit('/', 1)[-1] if '/' in content_range else response.headers.get('Content-Length', '')
                size = int(total) if total.isdigit() else None
                if size and size > MAX_BYTES:
                    raise MediaError('too_large', 'This file exceeds the free 500 MB limit.')
                first = response.read(chunk_size)
            with path.open('wb') as output:
                output.write(first)
                if size and size > len(first):
                    start = max(len(first), size - chunk_size)
                    with ydl.urlopen(Request(url, headers={**headers, 'Range': f'bytes={start}-{size - 1}'})) as response:
                        if response.status == 206 and response.headers.get('Content-Range', '').startswith(f'bytes {start}-'):
                            output.seek(start)
                            output.write(response.read(chunk_size))
            details = probe_file(path)
        video = next((s for s in details.get('streams', []) if s['codec_type'] == 'video'), None)
        if not video:
            continue
        audio = next((s for s in details['streams'] if s['codec_type'] == 'audio'), None)
        item.update(width=video.get('width'), height=video.get('height'), vcodec=video['codec_name'],
                    acodec=audio['codec_name'] if audio else 'none', filesize=size)
        if details.get('format', {}).get('duration'):
            info['duration'] = float(details['format']['duration'])


def run(payload):
    url = validate_url(payload['url'])
    install_network_guard()
    last_progress = 0.0
    transferred = {}

    def progress(data):
        nonlocal last_progress
        transferred[str(data.get('filename', 'video'))] = data.get('downloaded_bytes', 0)
        total = sum(transferred.values())
        if total > MAX_BYTES:
            raise MediaError('too_large', 'This file exceeds the free 500 MB limit. Choose a smaller quality.')
        now = time.monotonic()
        if now - last_progress > 0.5 or data.get('status') == 'finished':
            last_progress = now
            estimated = payload.get('choice', {}).get('size_bytes')
            percent = min(95, round(total / estimated * 95)) if estimated else None
            emit('progress', status='downloading', progress=percent, downloaded_bytes=total)

    with make_downloader(progress if payload['action'] == 'download' else None) as ydl:
        info = ydl.extract_info(url, download=False)
        enrich_direct_video(ydl, info)
        choices = build_formats(info)
        if payload['action'] == 'inspect':
            thumbnail = info.get('thumbnail')
            try:
                thumbnail = validate_url(thumbnail) if thumbnail else None
            except MediaError:
                thumbnail = None
            emit('result', data={
                'title': str(info.get('title') or 'Untitled video')[:240],
                'platform': str(info.get('extractor_key') or 'Video')[:60],
                'duration': info.get('duration'), 'thumbnail': thumbnail,
                'formats': choices,
            })
            return

        expected = payload['choice']
        choice = next((f for f in choices if f['key'] == expected['key'] and f['height'] == expected['height']
                       and f['container'] == expected['container']), None)
        if not choice:
            raise MediaError('format_expired', 'This quality is no longer available. Check the video link again.')
        directory = Path(payload['directory']).resolve()

        def selector(context):
            keys = choice['key'].split('+')
            selected = [next(f for f in context['formats'] if str(f['format_id']) == key) for key in keys]
            if len(selected) == 1:
                yield selected[0]
            else:
                yield {'format_id': choice['key'], 'ext': choice['container'],
                       'requested_formats': selected,
                       'protocol': '+'.join(f['protocol'] for f in selected)}

        ydl.format_selector = selector
        ydl.params.update({'skip_download': False, 'format': selector,
                           'outtmpl': {**ydl.params['outtmpl'], 'default': str(directory / 'video.%(ext)s')},
                           'merge_output_format': choice['container'],
                           'overwrites': False})
        ydl.process_ie_result(info, download=True)
        path = directory / f"video.{choice['container']}"
        if not path.is_file():
            raise MediaError('download_failed', 'The platform did not return a complete video file.')
        if path.stat().st_size > MAX_BYTES:
            raise MediaError('too_large', 'This file exceeds the free 500 MB limit. Choose a smaller quality.')
        verify_file(path)
        emit('result', data={'filename': path.name, 'size_bytes': path.stat().st_size})


if __name__ == '__main__':
    try:
        run(json.loads(sys.stdin.readline()))
    except Exception as error:
        code, message = public_error(error)
        emit('error', code=code, message=message)
        sys.exit(1)
