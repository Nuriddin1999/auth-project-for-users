export const config = {
  apiUrl: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
  googleClientId: import.meta.env.VITE_GOOGLE_CLIENT_ID || "",
  facebookAppId: import.meta.env.VITE_FACEBOOK_APP_ID || "",
  facebookGraphVersion: import.meta.env.VITE_FACEBOOK_GRAPH_VERSION || "v21.0",
  telegramBotName: import.meta.env.VITE_TELEGRAM_BOT_NAME || "",
  // Test mode: providers without keys sign in fake users (backend needs SOCIAL_AUTH_MOCK=True)
  mockAuth: import.meta.env.VITE_MOCK_AUTH === "true",
} as const;
