/**
 * OLYMPUS private Beta gateway. Public requests land ONLY here.
 * Credentials are injected by Railway secret references, not embedded in code.
 * Edge HttpOnly session cookie avoids clobbering the OLYMPUS Bearer token.
 */
import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

const UPSTREAM = "http://olympus-cloud-frontend.railway.internal:3000";
const COOKIE_NAME = "__Host-olympus_edge";
const SESSION_SECONDS = 4 * 60 * 60;
const MAX_BODY_BYTES = 12 * 1024 * 1024;
const IGNORE_REQ = new Set(["host", "connection", "proxy-authorization", "proxy-connection",
  "keep-alive", "transfer-encoding", "upgrade", "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"]);
const IGNORE_RES = new Set(["connection", "keep-alive", "transfer-encoding",
  "content-encoding", "content-length", "upgrade"]);

function equals(a, b) {
  const x = Buffer.from(String(a), "utf8"), y = Buffer.from(String(b), "utf8");
  return x.length === y.length && timingSafeEqual(x, y);
}
function signingKey() { return Bun.env.OLYMPUS_CLOUD_EDGE_SESSION_SECRET || ""; }
function signature(input) {
  return createHmac("sha256", signingKey()).update(input).digest("hex");
}
function validCookie(request) {
  const raw = request.headers.get("cookie") || "";
  const segment = raw.split(/;\s*/).find(x => x.startsWith(COOKIE_NAME + "="));
  if (!segment) return false;
  const value = segment.slice(COOKIE_NAME.length + 1);
  const match = /^(\d{10,12})\.([A-Za-z0-9_-]{22,64})\.([a-f0-9]{64})$/.exec(value);
  if (!match) return false;
  const expire = Number(match[1]);
  const now = Math.floor(Date.now()/1000);
  if (expire <= now || expire > now + SESSION_SECONDS) return false;
  return equals(signature(match[1]+"."+match[2]), match[3]);
}
function setCookie() {
  const expiration = Math.floor(Date.now()/1000) + SESSION_SECONDS;
  const nonce = randomBytes(20).toString("base64url");
  const input = String(expiration) + "." + nonce;
  return COOKIE_NAME + "=" + input + "." + signature(input) +
    "; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=" + SESSION_SECONDS;
}
function validBasic(request) {
  const user = Bun.env.OLYMPUS_CLOUD_EDGE_USER || "";
  const password = Bun.env.OLYMPUS_CLOUD_EDGE_PASSWORD || "";
  const auth = request.headers.get("authorization") || "";
  if (!user || user.includes(":") || password.length < 20 || !auth.startsWith("Basic ")) return false;
  try {
    const decoded = Buffer.from(auth.slice(6).trim(), "base64").toString("utf8");
    const i = decoded.indexOf(":");
    return i > 0 && equals(decoded.slice(0,i),user) && equals(decoded.slice(i+1),password);
  } catch { return false; }
}
function denial(status,message,challenge=false) {
  const headers = {"Content-Type":"text/plain; charset=utf-8","Cache-Control":"no-store",
    "X-Content-Type-Options":"nosniff","Referrer-Policy":"no-referrer"};
  if (challenge) headers["WWW-Authenticate"]='Basic realm="OLYMPUS Cloud Beta", charset="UTF-8"';
  return new Response(message,{status,headers});
}
function sameOrigin(request, allowedOrigin) {
  if (["GET","HEAD"].includes(request.method.toUpperCase())) return true;
  const site = request.headers.get("sec-fetch-site");
  const origin = request.headers.get("origin");
  if (site === "cross-site" || site === "same-site") return false;
  return origin === allowedOrigin || (!origin && site === "same-origin");
}
function appCookieOnly(originalCookie) {
  return (originalCookie||"").split(/;\s*/)
    .filter(v=>v && !v.startsWith(COOKIE_NAME+"=")).join("; ");
}
Bun.serve({
  hostname:"0.0.0.0",port:Number(Bun.env.PORT||"8080"),idleTimeout:255,
  maxRequestBodySize:MAX_BODY_BYTES,
  async fetch(request) {
    const origin=(Bun.env.OLYMPUS_CLOUD_PUBLIC_ORIGIN||"").replace(/\/$/,"");
    const key=signingKey();
    if (!/^https:\/\/[a-z0-9-]+\.up\.railway\.app$/.test(origin) || key.length < 48)
      return denial(503,"Private beta gateway not configured");
    const url=new URL(request.url);
    if (url.host !== new URL(origin).host) return denial(421,"Host mismatch");
    const hasBasic=validBasic(request);
    const hasSession=validCookie(request);
    if (!hasBasic && !hasSession) return denial(401,"Authentication required",true);
    if (!sameOrigin(request,origin)) return denial(403,"Cross-origin request denied");
    if (request.headers.get("upgrade")) return denial(426,"WebSocket upgrade is not supported");
    const size=Number(request.headers.get("content-length")||"0");
    if (!Number.isFinite(size)||size>MAX_BODY_BYTES) return denial(413,"Request too large");
    const method=request.method.toUpperCase();
    if (!["GET","HEAD","POST","PUT","PATCH","DELETE"].includes(method))
      return denial(405,"Method not allowed");
    const headers=new Headers(request.headers);
    for(const h of IGNORE_REQ) headers.delete(h);
    const auth=headers.get("authorization")||"";
    // Forward API Bearer credentials, never forward the Basic edge credentials.
    if (auth.startsWith("Basic ")) headers.delete("authorization");
    const appCookie=appCookieOnly(request.headers.get("cookie"));
    if(appCookie)headers.set("cookie",appCookie);else headers.delete("cookie");
    try {
      const upstream=await fetch(UPSTREAM+url.pathname+url.search,{
        method,headers,body:["GET","HEAD"].includes(method)?undefined:request.body,
        redirect:"manual",signal:request.signal
      });
      const out=new Headers(upstream.headers);
      for (const h of IGNORE_RES) out.delete(h);
      const location=out.get("location");
      if (location&&location.startsWith(UPSTREAM+"/"))
        out.set("location",origin+location.slice(UPSTREAM.length));
      out.set("Cache-Control","no-store");
      out.set("X-Content-Type-Options","nosniff");
      out.set("Referrer-Policy","no-referrer");
      out.set("X-Frame-Options","DENY");
      out.set("X-Robots-Tag","noindex, nofollow, noarchive");
      if (hasBasic && !hasSession) out.append("Set-Cookie",setCookie());
      return new Response(method==="HEAD"?null:upstream.body,{status:upstream.status,headers:out});
    } catch {
      return denial(502,"Private OLYMPUS frontend unavailable");
    }
  }
});
