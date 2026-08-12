import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.pixelgarage.editor",
  appName: "픽셀 정비소",
  webDir: "dist",
  server: {
    androidScheme: "https",
  },
};

export default config;
