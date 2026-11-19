const C='spares-v3';
const SHELL=['./','index.html','manifest.webmanifest','icon-192.png','icon-512.png'];
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(SHELL)));self.skipWaiting()});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(k=>Promise.all(k.filter(x=>x!==C).map(x=>caches.delete(x)))).then(()=>self.clients.claim()))});
const keep=(req,r)=>{if(r.status===200){const c2=r.clone();caches.open(C).then(c=>c.put(req,c2)).catch(()=>{})}return r};
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=='GET'||u.origin!==location.origin||/\/(data(-\w+)?|docs)\.json$/.test(u.pathname))return;
  if(u.pathname.includes('/docs/')){
    e.respondWith(caches.match(e.request).then(hit=>hit||fetch(e.request).then(r=>keep(e.request,r))));
    return;
  }
  // The app page itself: always try the network first so a new version shows up on the very next open;
  // fall back to the saved copy when offline or when the network is slow (3.5 s).
  if(e.request.mode==='navigate'||u.pathname.endsWith('/')||u.pathname.endsWith('index.html')){
    e.respondWith((async()=>{
      const cached=await caches.match(e.request,{ignoreSearch:true});
      const net=fetch(e.request);net.catch(()=>{});
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
