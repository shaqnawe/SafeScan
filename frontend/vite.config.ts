import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// BUILD_TARGET=native disables the service worker so Capacitor handles offline.
const isNativeBuild = process.env.BUILD_TARGET === 'native'

export default defineConfig({
  plugins: [
    react(),
    !isNativeBuild && VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['ingrediq-icon.svg', 'ingrediq-wordmark.svg', 'ingrediq-app-icon.svg', 'ingrediq-app-icon-dark.svg'],
      manifest: {
        name: 'IngrediQ — Barcode Safety Scanner',
        short_name: 'IngrediQ',
        description: "Scan any product. Know exactly what's inside.",
        theme_color: '#d97706',
        background_color: '#FDF6EE',
        display: 'standalone',
        orientation: 'portrait',
        start_url: '/',
        // Single SVG serves every install context — modern browsers + iOS 16+
        // honor "any maskable" + size="any" for vector icons. If raster sizes
        // become necessary for older Androids, regenerate from
        // ingrediq-app-icon.svg via a one-off script.
        icons: [
          {
            src: 'ingrediq-app-icon.svg',
            sizes: 'any',
            type: 'image/svg+xml',
            purpose: 'any maskable',
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/api/scan'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'api-scan-cache',
              expiration: {
                maxEntries: 50,
                maxAgeSeconds: 60 * 60 * 24 * 7,
              },
              networkTimeoutSeconds: 10,
            },
          },
        ],
      },
    }),
  ].filter(Boolean),
  server: {
    port: 5173,
    host: true,
    allowedHosts: ['.loca.lt'],
  },
})
