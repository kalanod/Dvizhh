import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, process.cwd(), "");

    return {
        plugins: [react(), tailwindcss()],
        build: {
            // Сборка кладётся внутрь Python-пакета: её отдаёт FastAPI-сервис web-app.
            outDir: "../src/dvizh_web/static",
            emptyOutDir: true,
        },
        server: {
            // IPv4 явно: на Windows "localhost" может привязаться только к ::1, а он бывает недоступен.
            host: "127.0.0.1",
            port: 5173,
            proxy: {
                "/api": env.BACKEND_URL || "http://localhost:8000",
            },
        },
    };
});
