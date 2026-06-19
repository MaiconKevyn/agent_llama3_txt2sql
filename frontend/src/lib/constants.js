export const API_BASE_URL = "/api";

export const STORAGE_KEYS = {
  sessionId: "chatSessionId",
  chatHistory: "chatHistory",
  theme: "theme",
  debugMode: "debugModeEnabled"
};

export const MAX_CONVERSATION_TURNS = 10;
export const MAX_HISTORY_MESSAGES = MAX_CONVERSATION_TURNS * 2;
export const MAX_MESSAGE_LENGTH = 1000;

export const EXAMPLE_QUESTIONS = [
  "Quais perguntas o schema atual consegue responder melhor?",
  "Mostre uma consulta agregada por ano com uma visualizacao simples.",
  "Compare os principais indicadores disponiveis no banco.",
  "Quais tabelas parecem mais relevantes para analises epidemiologicas?"
];

export const SERVER_STATUS_LABELS = {
  checking: "Verificando...",
  online: "Online",
  offline: "Agent offline"
};
