FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tini ca-certificates libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY --from=frontend /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend/
COPY --from=frontend /build/dist/client ./frontend/dist/client
RUN useradd --create-home --uid 10001 viddl && chown -R viddl:viddl /app
USER viddl
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "backend.serve"]
