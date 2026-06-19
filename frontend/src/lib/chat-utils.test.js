import { describe, expect, it } from "vitest";

import {
  buildUserFacingError,
  createMessage,
  createSessionId,
  normalizeQueryResponse,
  trimPersistedHistory
} from "./chat-utils";

describe("chat-utils", () => {
  it("creates a message with deterministic timestamp and id factory", () => {
    const now = new Date("2026-06-19T12:34:56.000Z");

    expect(
      createMessage("Resposta pronta", {
        type: "assistant",
        metadata: { executionTime: 1.25 },
        now,
        idFactory: () => "message-1"
      })
    ).toEqual({
      id: "message-1",
      content: "Resposta pronta",
      type: "assistant",
      timestamp: "2026-06-19T12:34:56.000Z",
      metadata: { executionTime: 1.25 }
    });
  });

  it("trims persisted history by removing errors and keeping the last 20 messages", () => {
    const messages = Array.from({ length: 25 }, (_, index) => ({
      id: `message-${index}`,
      type: index % 5 === 0 ? "error" : index % 2 === 0 ? "assistant" : "user",
      content: `Mensagem ${index}`
    }));

    const trimmed = trimPersistedHistory(messages);

    expect(trimmed).toHaveLength(20);
    expect(trimmed.every((message) => message.type !== "error")).toBe(true);
    expect(trimmed.map((message) => message.id)).toEqual(
      messages.filter((message) => message.type !== "error").slice(-20).map((message) => message.id)
    );
  });

  it("normalizes successful query responses with debug metadata when enabled", () => {
    const result = normalizeQueryResponse(
      {
        success: true,
        conversational_response: "Consulta concluida.",
        execution_time: 2.5,
        sql_query: "select 1",
        chart: { requested: true },
        debug: { route: "sql" },
        metadata: { tables_used: ["tb_cid"] }
      },
      true
    );

    expect(result).toEqual({
      type: "assistant",
      content: "Consulta concluida.",
      metadata: {
        executionTime: 2.5,
        sql: "select 1",
        chart: { requested: true },
        debug: { route: "sql" },
        agentMetadata: { tables_used: ["tb_cid"] }
      }
    });
  });

  it("normalizes failed query responses without debug metadata when disabled", () => {
    const result = normalizeQueryResponse(
      {
        success: false,
        answer: "Nao encontrei dados suficientes.",
        execution_time: Number.NaN,
        sql: "select * from missing",
        debug: { route: "sql" },
        metadata: { tables_used: [] }
      },
      false
    );

    expect(result).toEqual({
      type: "error",
      content: "Nao encontrei dados suficientes.",
      metadata: {
        sql: "select * from missing",
        chart: null
      }
    });
  });

  it("builds user-facing errors for common connection and HTTP cases", () => {
    expect(buildUserFacingError(new Error("Failed to fetch"))).toBe(
      "Nao foi possivel conectar ao agent do DataVisSUS. Confirme se o servico esta rodando e tente novamente."
    );
    expect(buildUserFacingError(new Error("NetworkError when attempting to fetch resource."))).toBe(
      "Nao foi possivel conectar ao agent do DataVisSUS. Confirme se o servico esta rodando e tente novamente."
    );
    expect(buildUserFacingError(new Error("HTTP 429: Too Many Requests"))).toBe(
      "Muitas consultas em pouco tempo. Aguarde alguns segundos antes de tentar novamente."
    );
    expect(buildUserFacingError(new Error("HTTP 503: Service Unavailable"))).toBe(
      "O agent retornou erro interno. Tente novamente em alguns instantes ou refine o recorte da consulta."
    );
    expect(buildUserFacingError(new Error("HTTP 400: Bad Request"))).toBe(
      "Erro de conexao: HTTP 400: Bad Request"
    );
  });

  it("creates a session id with crypto.randomUUID when available", () => {
    expect(
      createSessionId({
        crypto: {
          randomUUID: () => "uuid-123"
        }
      })
    ).toBe("uuid-123");
  });
});
