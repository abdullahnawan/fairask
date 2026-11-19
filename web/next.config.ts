import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // The browser talks to /api on this origin; Next.js forwards it to FastAPI,
  // so the API needs no CORS setup.
  rewrites: async () => [
    { source: "/api/:path*", destination: `${process.env.API_URL ?? "http://localhost:8000"}/:path*` },
  ],
};

export default nextConfig;
