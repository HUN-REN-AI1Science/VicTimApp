import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend runs on 8000; proxying /api keeps the frontend origin-clean in dev
// and means no CORS configuration is needed beyond the allowance already in app.py.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
