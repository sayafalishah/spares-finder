const C='spares-v3';
const SHELL=['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png'];
let isUpdate=false;
self.addEventListener('install',e=>{
  e.waitUntil((async()=>{isUpdate=await caches.has(C);const c=await caches.open(C);await c.addAll(SHELL.map(u=>new Request(u,{cache:'reload'})))})());
  self.skipWaiting();
});
self.addEventListener('activate',e=>{
  e.waitUntil((async()=>{
    for(const k of await caches.keys())if(k!==C)await caches.delete(k);
    await self.clients.claim();
    if(isUpdate)(await self.clients.matchAll({type:'window'})).forEach(c=>c.postMessage('app-updated'));
  })());
});
const keep=(req,r)=>{if(r.status===200){const c2=r.clone();caches.open(C).then(c=>c.put(req,c2)).catch(()=>{})}return r};
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=='GET'||u.origin!==location.origin||/\/(data(-\w+)?|docs|secure)\.json$/.test(u.pathname)||u.pathname.includes('/secure/'))return;
  if(u.pathname.includes('/docs/')){
    e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request).then(r=>keep(e.request,r))));
    return;
  }
  // The app page: ask the network first (revalidating, never a stale browser copy) so a new version
  // appears on the very next open; use the saved copy when offline or slower than 3.5 s.
  if(e.request.mode==='navigate'||u.pathname.endsWith('/')||u.pathname.endsWith('index.html')){
    e.respondWith((async()=>{
      const cached=await caches.match(e.request,{ignoreSearch:true});
      const nu=new URL(e.request.url);nu.searchParams.set('_',Date.now());
      const net=fetch(nu.href,{cache:'no-store'});net.catch(()=>{});
      try{
        const r=cached?await Promise.race([net,new Promise((_,rej)=>setTimeout(rej,3500))]):await net;
        return keep(e.request,r);
      }catch(err){return cached||Response.error()}
    })());
    return;
  }
  e.respondWith(caches.match(e.request,{ignoreSearch:true}).then(hit=>{
    const net=fetch(e.request).then(r=>keep(e.request,r)).catch(()=>hit);
    e.waitUntil(net.catch(()=>{}));
    return hit||net;
  }));
});
