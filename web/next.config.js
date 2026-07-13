/** @type {import('next').NextConfig} */

const apiProxyTarget =
  process.env.NEXT_API_PROXY_TARGET ||
  process.env.API_PROXY_TARGET ||
  (process.env.NODE_ENV === 'development' ? 'http://localhost:8001' : '')

const normalizedApiProxyTarget = apiProxyTarget.replace(/\/$/, '')

const lubanImmutableAssetHeaders = [
  {
    key: 'Cache-Control',
    value: 'public, max-age=31536000, immutable',
  },
]

const lubanStableAssetHeaders = [
  {
    key: 'Cache-Control',
    value: 'public, max-age=86400, stale-while-revalidate=604800',
  },
]

const lubanRevalidatedAssetHeaders = [
  {
    key: 'Cache-Control',
    value: 'public, max-age=3600, stale-while-revalidate=86400',
  },
]

const nextConfig = {
  // Standalone output: self-contained server.js + minimal node_modules
  // This eliminates the need to copy the full node_modules into Docker production images
  output: 'standalone',

  // Next.js 16 dev-server cross-origin gate: requests whose Host header
  // does not match the bound hostname trigger a console warning and skip
  // some HMR / React hydration wiring on the affected host. Default `npm
  // run dev` binds to all interfaces, so a Playwright/QA call via
  // 127.0.0.1 against a `localhost`-bound process (or vice versa) made
  // every onClick handler look "frozen". Whitelisting both loopback
  // names plus 0.0.0.0 keeps QA automation reliable without forcing
  // every caller to remember `--hostname 127.0.0.1`. Dev-only — does
  // not affect production behavior.
  allowedDevOrigins: ['127.0.0.1', 'localhost', '0.0.0.0'],

  // Move dev indicator to bottom-right corner
  devIndicators: {
    position: 'bottom-right',
  },

  // Luban cards are build-time public assets. Next.js otherwise serves public/
  // with max-age=0, forcing WeChat web-view to revalidate every MP3/font/image.
  // Audio URLs carry the publisher's audioVersion query, while shared fonts and
  // logos are release assets; cache those aggressively. HTML remains the fresh
  // entry pointer and unversioned JS/CSS get a short stale-while-revalidate TTL.
  async headers() {
    return [
      {
        source: '/luban-preview/:path*.mp3',
        headers: lubanImmutableAssetHeaders,
      },
      {
        source: '/luban-preview/:path*.woff2',
        headers: lubanStableAssetHeaders,
      },
      {
        source: '/luban-preview/:path*.png',
        headers: lubanStableAssetHeaders,
      },
      {
        source: '/luban-preview/:path*.js',
        headers: lubanRevalidatedAssetHeaders,
      },
      {
        // Versioned shared runtime: this later match intentionally overrides
        // the generic short-JS cache policy above.
        source: '/luban-preview/vendor/:path*',
        headers: lubanImmutableAssetHeaders,
      },
      {
        source: '/luban-preview/:path*.css',
        headers: lubanRevalidatedAssetHeaders,
      },
      {
        source: '/luban-preview/:path*.html',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=0, must-revalidate',
          },
        ],
      },
    ]
  },

  // Transpile mermaid and related packages for proper ESM handling
  transpilePackages: ['mermaid'],

  async rewrites() {
    if (!normalizedApiProxyTarget) {
      return []
    }

    return [
      {
        source: '/api/v1/:path*',
        destination: `${normalizedApiProxyTarget}/api/v1/:path*`,
      },
      {
        source: '/api/attachments/:path*',
        destination: `${normalizedApiProxyTarget}/api/attachments/:path*`,
      },
    ]
  },

  // Turbopack configuration (used when running `npm run dev:turbo`)
  turbopack: {
    resolveAlias: {
      // Fix for mermaid's cytoscape dependency - use CJS version
      cytoscape: 'cytoscape/dist/cytoscape.cjs.js',
    },
  },

  // Webpack configuration (used for production builds - next build)
  webpack: config => {
    const path = require('path')
    config.resolve.alias = {
      ...config.resolve.alias,
      cytoscape: path.resolve(__dirname, 'node_modules/cytoscape/dist/cytoscape.cjs.js'),
    }
    return config
  },
}

module.exports = nextConfig
