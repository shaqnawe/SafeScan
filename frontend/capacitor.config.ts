import type { CapacitorConfig } from '@capacitor/cli';

// When CAPACITOR_SERVER_URL is set (e.g. during live-reload dev), the WebView
// loads from that URL instead of the bundled dist/. Leave unset for production.
const serverUrl = process.env.CAPACITOR_SERVER_URL;

const config: CapacitorConfig = {
  appId: 'com.safescan.app',
  appName: 'SafeScan',
  webDir: 'dist',
  ...(serverUrl ? { server: { url: serverUrl, cleartext: true } } : {}),
  plugins: {
    SplashScreen: {
      launchShowDuration: 1500,
      backgroundColor: '#34c759',
      showSpinner: false,
      androidScaleType: 'CENTER_CROP',
    },
    StatusBar: {
      style: 'DARK',
      backgroundColor: '#00000000',
      overlaysWebView: true,
    },
  },
};

export default config;
