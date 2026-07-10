/** @type {import('next').NextConfig} */

// The frontend talks to the FastAPI backend same-origin under /api. Next proxies
// those requests server-side to the backend over the docker network, so the
// browser never needs to know the backend's (tailnet) host. Overridable for
// local dev via BACKEND_INTERNAL_URL.
const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL ?? "http://backend:8000";

const nextConfig = {
  // Emit a self-contained server bundle for a slim production Docker image.
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${BACKEND_INTERNAL_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
