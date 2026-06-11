/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  eslint: {
    // ESLint is not part of this build pipeline; type safety enforced via tsc.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;
