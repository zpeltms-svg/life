"""Exercise the pinned real SDK over an in-memory transport. No live requests."""
import json
import os
import sys
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for parent in ROOT.parents:
    if (parent/'.sdk-tools/openai').exists():sys.path.insert(0,str(parent/'.sdk-tools'));break

import openai
import httpx2 as httpx
from api import guide

def main():
    assert openai.__version__=='3.8.0'
    seen=[]
    def transport(request):
        body=json.loads(request.content);seen.append(body)
        assert request.url.path.endswith('/responses')
        assert body['store'] is False
        assert body['text']['format']['type']=='json_schema'
        assert body['text']['format']['strict'] is True
        assert set(body['text']['format']['schema']['properties'])=={'service_ids'}
        return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':0,'status':'completed','model':'gpt-5-mini','output':[{'id':'msg_test','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':'{"service_ids":["MOVE-001"]}','annotations':[]}]}]})
    real_client=openai.OpenAI
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        with mock.patch.dict(os.environ,{'OPENAI_API_KEY':'test-only','OPENAI_BASE_URL':'https://local-transport.invalid/v1'}),mock.patch.object(openai,'OpenAI',side_effect=lambda **kw:real_client(http_client=client,**kw)):
            result=guide.ai_select('전입신고',guide.load_services())
    assert result['service_ids']==['MOVE-001'] and len(seen)==1
    print(json.dumps({'ok':True,'sdk':openai.__version__,'live_requests':0,'in_memory_requests':len(seen)}))

if __name__=='__main__':main()
