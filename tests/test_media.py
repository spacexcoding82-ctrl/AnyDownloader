"""Real yt-dlp + FFmpeg with generated local media, no social-platform dependency."""
from copy import deepcopy
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading

import pytest
from backend import worker


def tool(name):
    suffix = '.exe' if os.name == 'nt' else ''
    location = os.getenv('FFMPEG_LOCATION')
    return str(Path(location) / (name + suffix)) if location else shutil.which(name)


@pytest.fixture
def media(tmp_path):
    binary = tool('ffmpeg')
    if not binary:
        pytest.skip('FFmpeg not installed')
    for quality in (360, 720):
        subprocess.run([binary, '-v', 'error', '-f', 'lavfi', '-i', f'color=c=blue:s={quality * 16 // 9}x{quality}:r=5',
            '-t', '1', '-an', '-c:v', 'libx264', '-threads', '1', '-preset', 'ultrafast', str(tmp_path / f'{quality}.mp4')], check=True)
    subprocess.run([binary, '-v', 'error', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
        '-c:a', 'aac', '-threads', '1', str(tmp_path / 'audio.m4a')], check=True)
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield tmp_path, f'http://127.0.0.1:{server.server_address[1]}'
    server.shutdown()
    server.server_close()
    thread.join()


def test_exact_selected_quality_and_real_audio_video_merge(media, monkeypatch, capsys):
    directory, origin = media
    output = directory / 'output'
    output.mkdir()
    info = {'id': 'test', 'title': 'Generated fixture', 'extractor': 'fixture', 'extractor_key': 'Fixture',
            'webpage_url': 'https://fixture.example/video', 'formats': [
        {'format_id': str(q), 'url': f'{origin}/{q}.mp4', 'ext': 'mp4', 'width': q * 16 // 9,
         'height': q, 'vcodec': 'avc1', 'acodec': 'none', 'protocol': 'http'} for q in (360, 720)] + [
        {'format_id': 'audio', 'url': f'{origin}/audio.m4a', 'ext': 'm4a', 'vcodec': 'none',
         'acodec': 'mp4a', 'protocol': 'http', 'abr': 128}]}
    # Only the controlled fixture test disables public-network enforcement.
    # Production code has no flag, URL exception or environment bypass for this.
    monkeypatch.setattr(worker, 'install_network_guard', lambda: None)
    original = worker.make_downloader
    def downloader(progress=None):
        ydl = original(progress)
        monkeypatch.setattr(ydl, 'extract_info', lambda *a, **kw: deepcopy(info))
        return ydl
    monkeypatch.setattr(worker, 'make_downloader', downloader)
    worker.run({'action': 'download', 'url': 'https://fixture.example/video',
                'choice': {'key': '360+audio', 'height': 360, 'container': 'mp4'}, 'directory': str(output)})
    saved = output / 'video.mp4'
    assert saved.is_file()
    probe = worker.probe_file(saved)
    assert {s['codec_type'] for s in probe['streams']} == {'video', 'audio'}
    assert next(s['height'] for s in probe['streams'] if s['codec_type'] == 'video') == 360
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert any(e.get('status') == 'merging' for e in events)
    assert events[-1]['event'] == 'result'
