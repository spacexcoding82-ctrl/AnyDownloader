# Verification results

- Frontend production build: passed, Vite static output packaged for the FastAPI server.
- Backend: **45 tests passed**, including real FFmpeg audio/video merging, exact selected quality, public-network guards, URL validation, session ownership, rate limits, cancellation, expiry and one-time save cleanup. Two dependency deprecation warnings do not affect the result.
- Browser: **10 scenarios verified** on headless Chrome desktop/mobile. Includes UI state tests with mocked metadata, real MDN sample downloads with the actual backend, navigation, validation, console/page errors and 320/390/768/1024 px viewport coverage. Final zoom-equivalent checks passed in a targeted rerun after correcting the test's simulation method.
- Actual sample: `https://developer.mozilla.org/shared-assets/videos/flower.mp4`, 540p, 1,128,375 bytes, audio present. Actual browser filename `flower.mp4` verified on desktop and mobile. The API disallowed reusing the completed file URL and removed the temporary server copy.
- A YouTube extractor test using `BaW_jenozKc` did not extract successfully. That single sample does not establish whether other YouTube videos work. Instagram/TikTok/Pinterest/Facebook/X/Vimeo live downloads have not been verified from a deployed Render IP; their extractors are included on a best-effort basis.
- Design: `design-qa.md` passed, with accepted minor font/icon rendering differences and intentional limit/privacy UI additions.
- Deployment: Dockerfile and Render Free Blueprint provided. Docker is unavailable in this local environment, so no local Docker image build was performed. The GitHub Actions workflow includes a Linux Docker build. The app has not been deployed publicly or tested from a Render data-center IP.

Local preview is a real service, not a mock-only homepage. The test fixtures are confined to the test suite; the production frontend always calls the real same-origin API.
