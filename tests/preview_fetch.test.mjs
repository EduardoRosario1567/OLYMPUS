import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { fetchPreview, validateRequest } from '../containers/preview-fetch.mjs';

async function withServer(handler, run) {
  const server=http.createServer(handler);
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  try { await run(server.address().port); }
  finally { server.closeAllConnections(); await new Promise(resolve=>server.close(resolve)); }
}

test('Rejects traversal, nested encoding, malformed paths and control characters',()=>{
  for(const target of ['http://evil','//evil','/../secret','/%2e%2e/secret','/%252e%252e/secret',
    '/a\\b','/x%00','/x\n','/x?query','/x%zz']) assert.throws(()=>validateRequest(target));
  assert.throws(()=>validateRequest('/','a=1\r\nAuthorization: bad'));
  assert.equal(validateRequest('/with%20space','v=1'),'/with%20space?v=1');
});

test('Live HTTP bridge preserves binary, query and status without authentication headers',async()=>{
  await withServer((request,response)=>{
    assert.equal(request.url,'/asset?v=1');
    assert.equal(request.headers.authorization,undefined);
    assert.equal(request.headers.cookie,undefined);
    response.writeHead(201,{'Content-Type':'image/png'}); response.end(Buffer.from([0,255,1]));
  },async port=>{
    const result=await fetchPreview('/asset','v=1',{port});
    assert.equal(result.status,201);
    assert.equal(result.content_type,'image/png');
    assert.deepEqual(Buffer.from(result.body,'base64'),Buffer.from([0,255,1]));
  });
});

test('Redirects are returned and never followed',async()=>{
  let requests=0;
  await withServer((request,response)=>{
    requests++; response.writeHead(302,{Location:'http://127.0.0.1:1/never'}); response.end();
  },async port=>{
    const result=await fetchPreview('/','',{port});
    assert.equal(result.status,302); assert.equal(requests,1);
    assert.equal(result.location,'http://127.0.0.1:1/never');
  });
});

test('Oversized live response is refused',async()=>{
  await withServer((request,response)=>response.end(Buffer.alloc(4096)),async port=>{
    await assert.rejects(fetchPreview('/','',{port,maxBytes:64}),/exceeds limit/);
  });
});

test('Absolute deadline refuses a stalled live server',async()=>{
  await withServer(()=>{},async port=>{
    await assert.rejects(fetchPreview('/','',{port,timeoutMs:50}),/deadline/);
  });
});

test('Aborted live responses are refused',async()=>{
  await withServer((request,response)=>{
    response.writeHead(200,{'Content-Length':'100'});response.write('x');
    setTimeout(()=>response.destroy(),10);
  },async port=>{
    await assert.rejects(fetchPreview('/','',{port}),/aborted|reset|hang up/i);
  });
});
