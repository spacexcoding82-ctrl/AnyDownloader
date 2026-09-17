# VidDL — video downloads without a VPS

A real React frontend, FastAPI API, yt-dlp extractor, and FFmpeg media processor in **one Render Docker web service**. The supplied `ui.jpeg` is preserved as the visual reference. No VPS, database, paid downloader API, Redis, or separate frontend host is required.

## Deploy on Render Free

1. Put this project in your own GitHub repository. Keep `Dockerfile`, `render.yaml`, `backend/`, `requirements.txt`, and `frontend/` (including `package-lock.json`). Do not upload `.venv`, `.tools`, `.cache`, or `node_modules`.
2. In [Render](https://dashboard.render.com/), choose **New → Blueprint** and connect that repository.
3. Render reads `render.yaml`. Confirm the **Free** instance. It builds the frontend, installs FFmpeg and the extractor, and starts the API automatically.
4. Open the resulting `https://<service-name>.onrender.com` address. HTTPS and the subdomain are provided by Render. No domain purchase or server administration is needed.
5. Check `/api/health` returns `{"status":"ok","media_tools":true}`, then test one of your own video links.

Alternatively use **New → Web Service**, select **Docker**, **Free**, and health-check path `/api/health`. Leave Docker context at the repository root. Do not choose Static Site: the downloader needs the Python service.

No deployment has been made or paid resource created by this checkout. Connect your own Render/GitHub account to publish it.

### Free hosting reality

Render Free [sleeps after 15 minutes without traffic](https://render.com/docs/free), has cold starts, monthly bandwidth limits, and can suspend services with unusually high service-initiated traffic. It is a small public demo, not unlimited hosting. Without a payment method, Render suspends free services rather than charging for overages. Review Render's current plan before adding billing details. This app cannot guarantee unlimited or always-on free downloads.

## What works

- Paste a public video link; see the actual formats and source resolutions.
- Up to **1080p / 500,000,000 bytes (500 MB)**. Portrait 1080×1920 counts as 1080p. No upscaling, fake qualities, or CPU-heavy conversion.
- MP4 and WebM, with compatible audio merged when necessary. Silent sources are labelled. MP3 conversion is not part of this MVP.
- Available platform extractors include YouTube, Instagram, TikTok, Pinterest, Facebook, X, Vimeo, and more. **Extractor availability is not a guarantee a particular video works.** Platform login gates, datacenter-IP blocks, geography and changes can prevent downloads. No cookies, accounts, proxies, or protection bypass are supported. YouTube is experimental; this is not a YouTube Data API integration.
- Direct MP4/WebM links: bounded range reads inspect actual dimensions. If dimensions cannot be established, the source is rejected instead of pretending it satisfies the resolution cap.
- Processing queue, progress, cancellation, browser save, and useful errors.
- 10 processing requests per IP per rolling 24-hour window, one active job per IP. Inspection and download/merge tasks share one worker slot to stay within free-host memory limits. Failed and cancelled starts count toward the limit. Three inspection requests may be in flight/queued. Inspection is capped at 6/minute and 30/hour per IP; a busy checker returns a retry message rather than running indefinitely.
- Maximum four active/queued jobs, 30-second extraction limit, 10-minute download limit, 320 MiB worker-process-tree memory budget, bounded temporary storage.
- Files are sent once and deleted when transfer ends, including disconnect. Unclaimed files expire after roughly 15 minutes. Re-download requires preparing another copy. No download resumption in this MVP.
- Jobs, rate counters and inspection results are in memory. They reset when the service restarts. Do **not** increase Uvicorn workers or instance count without introducing shared job/rate storage.

Only download content you own or have permission to save. A public URL alone is not permission. Platform terms still apply. In particular [YouTube's API developer policies](https://developers.google.com/youtube/terms/developer-policies) prohibit API clients from facilitating offline downloads without approval; do not market this as an officially authorized YouTube service. Review platform terms before a public launch.

## Local development

Requires Python 3.12+, Node.js 22+, and FFmpeg + FFprobe. On this Windows machine, Python can be run from `C:\Users\skr12\AppData\Local\Python\pythoncore-3.14-64\python.exe` if the Windows `python` alias does not work.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd frontend
npm ci
npm run build
cd ..
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup-media.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

Open `http://localhost:8000`. `setup-media.ps1` downloads the Windows build linked from ffmpeg.org, verifies its published SHA-256, and keeps it inside ignored `.tools/`. It does not change the system PATH. For an existing FFmpeg installation, put both binaries on PATH or set `FFMPEG_LOCATION` to their directory.

For live frontend edits run `npm run dev` in `frontend/`. Vite proxies `/api` to `127.0.0.1:8000`. Production always uses same-origin requests.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
cd frontend
npm run build
npm run test:e2e
```

FFmpeg must be on PATH or configured for the real merge test. Without it, pytest reports that test as skipped. Browser tests expect the built API service at port 8000; `VIDDL_TEST_URL` overrides it. Windows tests use headless installed Chrome with an isolated profile. On Linux run `npx playwright install --with-deps chromium` first.

Most browser tests use explicitly mocked API responses for predictable UI states. The optional real test uses MDN's downloadable flower example and the actual API, extractor, disk cleanup and browser download:

```powershell
$env:VIDDL_LIVE_TEST='1'
npm run test:e2e
```

From the repository root, `python scripts/smoke-download.py --base-url http://127.0.0.1:8000` also tests the live API end to end. It saves the verified sample under ignored `.cache/`. Tests never include user cookies or platform account credentials.

## API and security boundaries

| Endpoint | Behavior |
| --- | --- |
| `GET /api/config` | Establishes an HTTP-only SameSite session; returns limits. |
| `POST /api/inspect` | `{url}` → temporary inspection ID, title, thumbnail, duration, real formats. |
| `POST /api/download` | `{inspection_id, format_key, rights_confirmed}` → job ID. |
| `GET /api/jobs/{id}` | Progress, status, sanitized errors and ready-file URL. |
| `DELETE /api/jobs/{id}` | Cancels and cleans up. Send a JSON body `{}`. |
| `GET /api/jobs/{id}/file` | One-time streamed file attachment, scoped to the browser session. |
| `GET /api/health` | Media dependency health; used by Render. |

Requests are bounded JSON, same-origin, with no CORS wildcard. Jobs are session-scoped; IDs and local paths cannot be supplied as file targets. Python workers enforce public-IP/port checks at DNS **and socket-connect** time, including redirects and media fragments. Only guarded urllib/native download transports are allowed; external downloader fallbacks are disabled. FFmpeg receives local input with a restricted protocol whitelist. Final media dimensions and size are verified. Worker timeout/cancellation kills the process tree.

Only the Render launcher trusts forwarded client addresses, because Render terminates the public connection. Do not set `RENDER=true` for an directly exposed unmanaged server. The app disables HTTP access logging and does not retain source URLs on disk. Your hosting provider may retain its own logs.

## Maintenance

yt-dlp is pinned to the version verified in this checkout. When a platform changes, update that pin, run the tests and redeploy; runtime auto-updates are deliberately disabled. Docker packages FFmpeg at build time. A service restart loses active jobs; the UI asks users to retry expired work. Monitor Render's health, memory and bandwidth usage. Keep the Free plan explicit in `render.yaml`.

The bundled frontend starter includes Sites compatibility files. They are preserved, but **the intended full-stack deployment is Render**; publishing only the frontend does not provide video downloads.
