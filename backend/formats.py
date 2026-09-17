"""Only offer real video formats; never upscale or silently change quality."""
from .security import MediaError

MAX_BYTES = 500_000_000
MAX_HEIGHT = 1080
ALLOWED_PROTOCOLS = {'http', 'https', 'm3u8_native', 'http_dash_segments'}


def reject_unavailable(info):
    if not info or info.get('_type') in ('playlist', 'multi_video') or 'entries' in info:
        raise MediaError('single_video_only', 'Paste a single video link, not a playlist or collection.')
    if info.get('is_live') or info.get('live_status') in ('is_live', 'is_upcoming', 'post_live'):
        raise MediaError('live_not_supported', 'Live and upcoming streams are not supported. Try a completed video.')
    if info.get('has_drm'):
        raise MediaError('protected_video', 'This video is protected and cannot be downloaded.')
    if info.get('availability') in ('private', 'premium_only', 'subscriber_only', 'needs_auth'):
        raise MediaError('login_required', 'This video requires an account or is not public.')


def safe_format(f):
    return (not f.get('has_drm') and f.get('url')
            and f.get('protocol', 'https') in ALLOWED_PROTOCOLS)


def size_of(f):
    return f.get('filesize') or f.get('filesize_approx')


def build_formats(info):
    reject_unavailable(info)
    source = [f for f in info.get('formats', [info]) if safe_format(f)]
    audio = [f for f in source if f.get('vcodec') == 'none' and f.get('acodec') not in ('none', None)]
    audio.sort(key=lambda f: f.get('abr') or f.get('tbr') or 0, reverse=True)
    choices = {}
    for video in source:
        if video.get('vcodec') in ('none', None):
            continue
        # For portrait videos, the shorter dimension is the quality (1080x1920 = 1080p).
        dimensions = [n for n in (video.get('width'), video.get('height')) if n]
        quality = min(dimensions) if dimensions else None
        if not quality or quality > MAX_HEIGHT:
            continue  # Unknown quality cannot safely satisfy a strict 1080p cap.
        ext = video.get('ext')
        if ext not in ('mp4', 'webm'):
            continue
        paired = None
        if video.get('acodec') == 'none':
            paired = next((a for a in audio if (
                a.get('ext') in ('m4a', 'mp4') if ext == 'mp4' else a.get('ext') == 'webm'
            )), None)
        selected = [video] + ([paired] if paired else [])
        known_sizes = [size_of(f) for f in selected]
        estimate = int(sum(known_sizes)) if all(known_sizes) else None
        if any((f.get('filesize') or 0) > MAX_BYTES for f in selected) or (estimate and estimate > MAX_BYTES):
            continue
        ids = [str(f.get('format_id', '')) for f in selected]
        if not all(ids):
            continue
        has_audio = video.get('acodec') not in ('none', None) or paired is not None
        choice = {
            'key': '+'.join(ids), 'label': f'{int(quality)}p', 'height': int(quality),
            'container': ext, 'fps': video.get('fps'), 'size_bytes': estimate,
            'size_is_estimate': any(not f.get('filesize') for f in selected),
            'has_audio': has_audio, 'merge': paired is not None,
        }
        group = (int(quality), ext)
        rank = (has_audio, video.get('fps') or 0, video.get('tbr') or 0)
        if group not in choices or rank > choices[group][0]:
            choices[group] = (rank, choice)
    result = [item[1] for item in choices.values()]
    result.sort(key=lambda f: (-f['height'], f['container'] != 'mp4'))
    if not result:
        raise MediaError('no_formats', 'No downloadable MP4 or WebM quality within 1080p / 500 MB was found.')
    return result
