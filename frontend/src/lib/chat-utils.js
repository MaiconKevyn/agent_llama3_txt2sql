import { MAX_HISTORY_MESSAGES } from "./constants";

function getDefaultEnvironment() {
  if (typeof window !== "undefined") return window;
  return globalThis;
}

function getNow(environment) {
  return typeof environment?.now === "function" ? environment.now() : Date.now();
}

function getRandom(environment) {
  return typeof environment?.random === "function" ? environment.random() : Math.random();
}

export function createSessionId(environment = getDefaultEnvironment()) {
  if (typeof environment?.crypto?.randomUUID === "function") {
    return environment.crypto.randomUUID();
  }

  const now = getNow(environment);
  const random = getRandom(environment);
  return `web-${now}-${random.toString(16).slice(2)}`;
}

export function createMessageId(environment = getDefaultEnvironment()) {
  const now = getNow(environment);
  const random = getRandom(environment);
  return `msg-${now}-${random.toString(16).slice(2)}`;
}

export function createMessage(content, options = {}) {
  const normalizedOptions = typeof options === "string" ? { type: options } : options ?? {};
  const {
    type = "assistant",
    metadata = null,
    now = new Date(),
    idFactory = createMessageId
  } = normalizedOptions;
  const timestamp = now instanceof Date ? now.toISOString() : new Date(now).toISOString();

  return {
    id: idFactory(),
    content,
    type,
    timestamp,
    metadata
  };
}

export function trimPersistedHistory(messages) {
  if (!Array.isArray(messages)) return [];

  return messages
    .filter((message) => message?.type !== "error")
    .slice(-MAX_HISTORY_MESSAGES);
}

function buildQueryMetadata(data, debugEnabled) {
  const metadata = {
    sql: data?.sql || data?.sql_query || null,
    chart: data?.chart || null
  };

  if (Number.isFinite(data?.execution_time)) {
    metadata.executionTime = data.execution_time;
  }

  if (debugEnabled) {
    metadata.debug = data?.debug || null;
    metadata.agentMetadata = data?.metadata || {};
  }

  return metadata;
}

export function normalizeQueryResponse(data, debugEnabled = false) {
  const success = data?.success === true;

  return {
    type: success ? "assistant" : "error",
    content: success
      ? data?.response || data?.conversational_response || data?.answer || "Consulta processada com sucesso."
      : data?.error_message || data?.answer || data?.response || "Nao foi possivel processar a consulta.",
    metadata: buildQueryMetadata(data, debugEnabled)
  };
}

export function buildUserFacingError(error) {
  const message = error?.message || String(error);

  if (message.includes("Failed to fetch") || message.includes("NetworkError")) {
    return "Nao foi possivel conectar ao agent do DataVisSUS. Confirme se o servico esta rodando e tente novamente.";
  }
  if (message.includes("HTTP 429")) {
    return "Muitas consultas em pouco tempo. Aguarde alguns segundos antes de tentar novamente.";
  }
  if (message.includes("HTTP 5")) {
    return "O agent retornou erro interno. Tente novamente em alguns instantes ou refine o recorte da consulta.";
  }
  return `Erro de conexao: ${message}`;
}
