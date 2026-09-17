"""One managed service; one process owns the in-memory queue and rate limits."""
import os
import uvicorn

if __name__ == '__main__':
    uvicorn.run('backend.main:app', host='0.0.0.0', port=int(os.getenv('PORT', '8000')),
                workers=1, proxy_headers=os.getenv('RENDER') == 'true',
                forwarded_allow_ips='*' if os.getenv('RENDER') == 'true' else '127.0.0.1',
                access_log=False, limit_concurrency=64, timeout_keep_alive=5)
