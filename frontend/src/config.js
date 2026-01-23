// src/config.js
// Конфигурация окружения - автоматически определяет dev/prod по VITE_IS_DEV

const IS_DEV = import.meta.env.VITE_IS_DEV === 'true';
const SERVER_HOST = IS_DEV ? 'localhost' : '10.109.50.250';

export const config = {
    IS_DEV,
    SERVER_HOST,

    // API адреса
    API_URL: `http://${SERVER_HOST}:8000/api`,

    // Внешние сервисы
    RAG_BOT_URL: `http://10.109.50.250:5111`,
    VKS_SUMMARY_URL: `http://10.109.50.250:5000`,
};

export default config;
