// src/config.js
// Конфигурация окружения - автоматически определяет dev/prod по VITE_IS_DEV

const IS_DEV = import.meta.env.VITE_IS_DEV === 'true';
const SERVER_HOST = IS_DEV ? 'localhost' : '10.109.50.250';

export const config = {
    IS_DEV,
    SERVER_HOST,

    // API адреса
    // Используем относительный путь, чтобы запросы шли через Vite Proxy (на порт 8090 -> 5173 -> api:8000)
    API_URL: '/api',

    // Keycloak
    // Keycloak
    // Keycloak
    KEYCLOAK_URL: import.meta.env.VITE_KEYCLOAK_URL || 'https://auth.nir.center',
    KEYCLOAK_REALM: import.meta.env.VITE_KEYCLOAK_REALM || 'platform',
    KEYCLOAK_CLIENT_ID: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'agent-kp',

    // Внешние сервисы
    RAG_BOT_URL: `http://10.109.50.250:5111`,
    VKS_SUMMARY_URL: `http://10.109.50.250:5000`,
    ANONYMIZER_URL: `http://10.109.50.250:5053`,
    DOC_COMPARE_URL: `https://compare.nir.center/`,
};

export default config;
