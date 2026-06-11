/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.FRIDAY_API || "http://localhost:8080"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
