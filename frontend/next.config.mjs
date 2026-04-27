import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Proxy /api/* to the backend (replaces Vite dev proxy + Vercel rewrites).
  // In production, NEXT_PUBLIC_API_URL is typically set so the client calls
  // the API server directly; this rewrite keeps relative `/api` calls working
  // when no env var is set (e.g. local dev against the FastAPI on :8000).
  async rewrites() {
    const apiTarget =
      process.env.API_PROXY_TARGET ?? "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
    ];
  },
};

export default withNextIntl(nextConfig);
