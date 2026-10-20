/** @type {import('next').NextConfig} */
const developmentScriptPolicy = process.env.NODE_ENV === "development" ? " 'unsafe-eval'" : "";
const securityHeaders = [
  { key: "Content-Security-Policy", value: `default-src 'self'; script-src 'self' 'unsafe-inline'${developmentScriptPolicy}; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 https:; frame-src 'self' http://localhost:8000 http://127.0.0.1:8000; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'` },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const CLOUD_PROXY_ENABLED = process.env.OLYMPUS_FRONTEND_CLOUD_PROXY === "1";
const CLOUD_BACKEND_ORIGIN = process.env.OLYMPUS_BACKEND_INTERNAL_URL
  || "http://olympus-cloud-backend.railway.internal:8000";
if (CLOUD_PROXY_ENABLED && !/^http:\/\/(?:[a-z0-9-]+\.railway\.internal|127\.0\.0\.1|localhost)(?::\d{2,5})?$/.test(CLOUD_BACKEND_ORIGIN)) {
  throw new Error("OLYMPUS_BACKEND_INTERNAL_URL must be an internal backend");
}

const nextConfig = {
  async rewrites() {
    return CLOUD_PROXY_ENABLED ? [{
      source: "/api/olympus/:path*",
      destination: CLOUD_BACKEND_ORIGIN + "/:path*",
    }] : [];
  },
  async headers() {
    return [{ source: "/(.*)", headers: securityHeaders }];
  },
};

export default nextConfig;
