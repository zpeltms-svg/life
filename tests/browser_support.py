import os
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
# Optional workspace-local tooling. Normal installations use requirements-dev.txt.
for parent in ROOT.parents:
    if (parent/'.test-tools/playwright').exists():
        sys.path.insert(0,str(parent/'.test-tools'))
        os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(parent/'.test-browsers'))
        break

@contextmanager
def preview_server():
    from local_preview import PreviewHandler, ThreadingHTTPServer
    from api._common import _RATE_BUCKETS
    _RATE_BUCKETS.clear()
    with patch.dict(os.environ, {key:'' for key in ('OPENAI_API_KEY','PUBLIC_DATA_SERVICE_KEY','NCP_MAPS_CLIENT_ID','NCP_MAPS_CLIENT_SECRET','VERCEL')}):
        server=ThreadingHTTPServer(('127.0.0.1',0),PreviewHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try: yield f'http://127.0.0.1:{server.server_port}'
        finally: server.shutdown();server.server_close();thread.join(3)

def launch(pw):
    options={'headless':True}
    if os.environ.get('CHROMIUM_PATH'): options['executable_path']=os.environ['CHROMIUM_PATH']
    return pw.chromium.launch(**options)
