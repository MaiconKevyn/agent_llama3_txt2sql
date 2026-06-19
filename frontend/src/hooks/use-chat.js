import { useCallback, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { sendQuery } from "../lib/api";
import { MAX_MESSAGE_LENGTH, STORAGE_KEYS } from "../lib/constants";
import {
  buildUserFacingError,
  createMessage,
  createSessionId,
  normalizeQueryResponse,
  trimPersistedHistory
} from "../lib/chat-utils";
import {
  readJsonStorage,
  readStorage,
  removeStorage,
  writeJsonStorage,
  writeStorage
} from "../lib/storage";

function ensureSessionId() {
  const storedSessionId = readStorage(STORAGE_KEYS.sessionId, "");
  if (storedSessionId) return storedSessionId;

  const nextSessionId = createSessionId();
  writeStorage(STORAGE_KEYS.sessionId, nextSessionId);
  return nextSessionId;
}

function readInitialMessages() {
  const storedMessages = readJsonStorage(STORAGE_KEYS.chatHistory, []);
  return Array.isArray(storedMessages) ? storedMessages : [];
}

export function useChat({ debugEnabled = false, onServerStatusChange } = {}) {
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState(ensureSessionId);
  const [messages, setMessages] = useState(readInitialMessages);
  const messagesRef = useRef(messages);

  const hasMessages = messages.length > 0;
  const canSend = input.trim().length > 0 && input.length <= MAX_MESSAGE_LENGTH && !isLoading;

  const persistMessages = useCallback((nextMessages) => {
    writeJsonStorage(STORAGE_KEYS.chatHistory, trimPersistedHistory(nextMessages));
  }, []);

  const replaceMessages = useCallback((nextMessages) => {
    messagesRef.current = nextMessages;
    setMessages(nextMessages);
  }, []);

  const addMessage = useCallback(
    (message) => {
      const nextMessages = [...messagesRef.current, message];
      messagesRef.current = nextMessages;
      persistMessages(nextMessages);
      setMessages(nextMessages);
    },
    [persistMessages]
  );

  const fillQuestion = useCallback((question) => {
    setInput(question);
  }, []);

  const clearChat = useCallback(() => {
    const nextSessionId = createSessionId();

    replaceMessages([]);
    setSessionId(nextSessionId);
    writeStorage(STORAGE_KEYS.sessionId, nextSessionId);
    removeStorage(STORAGE_KEYS.chatHistory);
  }, [replaceMessages]);

  const submitMessage = useCallback(async () => {
    const question = input.trim();

    if (!question || isLoading || input.length > MAX_MESSAGE_LENGTH) {
      return;
    }

    setIsLoading(true);
    setInput("");
    addMessage(createMessage(question, { type: "user" }));

    try {
      const response = await sendQuery({ question, sessionId, debug: debugEnabled });

      if (response?.session_id) {
        setSessionId(response.session_id);
        writeStorage(STORAGE_KEYS.sessionId, response.session_id);
      }

      const normalizedResponse = normalizeQueryResponse(response, debugEnabled);
      addMessage(
        createMessage(normalizedResponse.content, {
          type: normalizedResponse.type,
          metadata: normalizedResponse.metadata
        })
      );
      onServerStatusChange?.("online");
    } catch (error) {
      onServerStatusChange?.("offline");
      addMessage(createMessage(buildUserFacingError(error), { type: "error" }));
      toast.error("Nao foi possivel concluir a consulta. Verifique o agent e tente novamente.");
    } finally {
      setIsLoading(false);
    }
  }, [addMessage, debugEnabled, input, isLoading, onServerStatusChange, sessionId]);

  return useMemo(
    () => ({
      input,
      setInput,
      isLoading,
      sessionId,
      messages,
      hasMessages,
      canSend,
      fillQuestion,
      clearChat,
      submitMessage
    }),
    [
      canSend,
      clearChat,
      fillQuestion,
      hasMessages,
      input,
      isLoading,
      messages,
      sessionId,
      submitMessage
    ]
  );
}
