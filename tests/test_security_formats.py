import socket
import pytest
from backend.security import MediaError, public_ip, validate_url, install_network_guard
from backend.formats import build_formats
from backend.worker import make_downloader, public_error


@pytest.mark.parametrize('url', [
    'file:///etc/passwd', 'ftp://example.com/a', 'http://127.0.0.1/a', 'http://[::1]/',
    'http://169.254.169.254/latest/meta-data', 'http://10.0.0.1', 'http://localhost/a',
    'http://service.internal/a', 'https://user:password@example.com/a', 'https://example.com:444/a',
    'https://example.com/\nabc', 'https://example.com\\@127.0.0.1',
])
def test_rejects_unsafe_urls(url):
    with pytest.raises(MediaError):
        validate_url(url)


@pytest.mark.parametrize('address', ['0.0.0.0', '127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.1.1',
    '169.254.169.254', '::1', 'fc00::1', '::ffff:127.0.0.1', '64:ff9b::7f00:1', '2002:7f00:1::', '224.0.0.1'])
def test_private_and_translation_addresses(address):
    assert not public_ip(address)


def test_public_url_and_ip():
    assert validate_url(' https://www.youtube.com/watch?v=abc#part ') == 'https://www.youtube.com/watch?v=abc'
    assert public_ip('8.8.8.8')


def test_socket_guard_checks_dns_and_connection(monkeypatch):
    original_resolver, original_connect, original_ex = socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))])
    try:
        install_network_guard()
        with pytest.raises(OSError):
            socket.getaddrinfo('rebinding.example.com', 443)
        with socket.socket() as sock, pytest.raises(OSError):
            sock.connect(('8.8.8.8', 443))
    finally:
        socket.getaddrinfo, socket.socket.connect, socket.socket.connect_ex = original_resolver, original_connect, original_ex


def fmt(key='720', height=720, **kw):
    return {'format_id': key, 'url': 'https://media.example.com/video.mp4', 'vcodec': 'avc1',
            'acodec': 'mp4a', 'height': height, 'width': height * 16 // 9 if height else None,
            'ext': 'mp4', 'protocol': 'https', 'filesize': 1_000_000, **kw}


def test_real_resolutions_no_upscale_no_unknown_or_oversize():
    result = build_formats({'formats': [fmt(), fmt('4k', 2160), fmt('large', 1080, filesize=500_000_001), fmt('unknown', None, width=None)]})
    assert [f['label'] for f in result] == ['720p']


def test_portrait_1080_is_allowed():
    result = build_formats({'formats': [fmt(height=1920, width=1080)]})
    assert result[0]['height'] == 1080


def test_pair_audio_and_video_with_combined_size():
    result = build_formats({'formats': [fmt('v', 1080, acodec='none'), fmt('a', 0, vcodec='none', ext='m4a', abr=128)]})
    assert result[0]['key'] == 'v+a'
    assert result[0]['merge'] and result[0]['has_audio']
    assert result[0]['size_bytes'] == 2_000_000


def test_webm_stays_webm_and_silent_video_is_labelled():
    result = build_formats({'formats': [fmt(ext='webm', acodec='none', vcodec='vp9')]})
    assert result[0]['container'] == 'webm' and not result[0]['has_audio']


@pytest.mark.parametrize('info', [{'_type': 'playlist'}, {'entries': []}, {'is_live': True}, {'has_drm': True}, {'availability': 'private'}])
def test_restricted_content(info):
    with pytest.raises(MediaError):
        build_formats({**info, 'formats': [fmt()]})


def test_native_only_and_no_external_fallback():
    from yt_dlp.downloader.external import FFmpegFD
    with make_downloader() as ydl:
        assert set(ydl._request_director.handlers) == {'Urllib'}
        assert ydl.params['proxy'] == ''
        with pytest.raises(MediaError):
            FFmpegFD(ydl, ydl.params).real_download('file.mp4', {})


def test_errors_do_not_leak_source_tokens():
    error = Exception('HTTP Error 403: Forbidden https://example.com?token=secret')
    assert 'secret' not in public_error(error)[1]
