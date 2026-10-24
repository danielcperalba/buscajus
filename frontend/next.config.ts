import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Gera .next/standalone para a imagem Docker (ver Dockerfile).
  output: "standalone",
};

export default nextConfig;
