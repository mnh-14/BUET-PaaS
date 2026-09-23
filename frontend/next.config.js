/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  // Next's built-in gzip compression buffers proxied responses until they
  // close, which breaks the SSE build/deploy log and status streams (they're
  // rewritten through this server) — nothing shows until the stream ends.
  compress: false,
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backend}/api/v1/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
