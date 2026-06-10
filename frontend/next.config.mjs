/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export served by FastAPI as plain files (PLAN.md §3).
  output: "export",
  // Emits index.html per route so FastAPI can serve directories directly.
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
