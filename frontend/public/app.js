const API_BASE_URL = '/api';
const SESSION_STORAGE_KEY = 'chatSessionId';
const CHAT_HISTORY_KEY = 'chatHistory';
const THEME_KEY = 'theme';
const MAX_CONVERSATION_TURNS = 10;
const MAX_HISTORY_MESSAGES = MAX_CONVERSATION_TURNS * 2;
const MAX_MESSAGE_LENGTH = 1000;

let isLoading = false;
let messageHistory = [];
let schemaTriggerElement = null;

const elements = {
    messageInput: document.getElementById('messageInput'),
    sendBtn: document.getElementById('sendBtn'),
    chatMessages: document.getElementById('chatMessages'),
    schemaModal: document.getElementById('schemaModal'),
    schemaBtn: document.getElementById('schemaBtn'),
    closeSchemaModal: document.getElementById('closeSchemaModal'),
    clearBtn: document.getElementById('clearBtn'),
    statusIndicator: document.getElementById('statusIndicator'),
    statusText: document.getElementById('statusText'),
    errorToast: document.getElementById('errorToast'),
    schemaContent: document.getElementById('schemaContent'),
    exampleBtns: document.querySelectorAll('.example-btn'),
    themeToggle: document.getElementById('themeToggle'),
    charCounter: document.getElementById('charCounter')
};

document.addEventListener('DOMContentLoaded', function() {
    initializeTheme();
    initializeApp();
    setupEventListeners();
    checkServerStatus();
});

function initializeApp() {
    ensureSessionId();
    loadMessageHistory();
    autoResizeTextarea();
    updateInputState();
}

function setupEventListeners() {
    elements.messageInput.addEventListener('input', updateInputState);
    elements.messageInput.addEventListener('keydown', handleInputKeyDown);
    elements.sendBtn.addEventListener('click', sendMessage);
    elements.schemaBtn.addEventListener('click', showSchemaModal);
    elements.closeSchemaModal.addEventListener('click', hideSchemaModal);
    elements.clearBtn.addEventListener('click', clearChat);
    elements.themeToggle.addEventListener('click', toggleTheme);

    elements.schemaModal.addEventListener('click', function(event) {
        if (event.target === elements.schemaModal) {
            hideSchemaModal();
        }
    });

    const loadSchemaBtn = document.getElementById('loadSchemaBtn');
    if (loadSchemaBtn) {
        loadSchemaBtn.addEventListener('click', loadSelectedSchema);
    }

    elements.exampleBtns.forEach((button) => {
        button.addEventListener('click', function() {
            const question = this.getAttribute('data-question') || '';
            fillQuestion(question);
        });
    });

    const toastClose = elements.errorToast.querySelector('.toast-close');
    if (toastClose) {
        toastClose.addEventListener('click', hideErrorToast);
    }

    document.addEventListener('keydown', function(event) {
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            if (!isLoading && elements.messageInput.value.trim()) {
                sendMessage();
            }
        }

        if (event.key === 'Escape') {
            if (elements.schemaModal.classList.contains('show')) {
                hideSchemaModal();
            }
            if (elements.errorToast.classList.contains('show')) {
                hideErrorToast();
            }
        }
    });
}

function fillQuestion(question) {
    elements.messageInput.value = question;
    elements.messageInput.focus();
    elements.messageInput.setSelectionRange(question.length, question.length);
    updateInputState();
}

function autoResizeTextarea() {
    const textarea = elements.messageInput;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 140)}px`;
}

function updateInputState() {
    autoResizeTextarea();
    const value = elements.messageInput.value;
    const hasText = value.trim().length > 0;
    elements.sendBtn.disabled = !hasText || isLoading;
    elements.charCounter.textContent = `${value.length}/${MAX_MESSAGE_LENGTH}`;
    elements.charCounter.classList.toggle('limit-warning', value.length > MAX_MESSAGE_LENGTH * 0.9);
}

function handleInputKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if (!isLoading && elements.messageInput.value.trim()) {
            sendMessage();
        }
    }
}

async function sendMessage() {
    const message = elements.messageInput.value.trim();
    if (!message || isLoading) return;

    isLoading = true;
    addMessage(message, 'user');
    elements.messageInput.value = '';
    updateInputState();

    const loadingMessageId = addLoadingMessage();

    try {
        const response = await fetch(`${API_BASE_URL}/query`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include',
            mode: 'cors',
            cache: 'no-cache',
            body: JSON.stringify({
                question: message,
                session_id: getSessionId()
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        if (data.session_id) {
            localStorage.setItem(SESSION_STORAGE_KEY, data.session_id);
        }

        removeLoadingMessage(loadingMessageId);

        if (data.success) {
            addMessage(data.response || data.conversational_response || 'Consulta processada com sucesso.', 'assistant', {
                executionTime: data.execution_time,
                sql: data.sql || data.sql_query || null
            });
        } else {
            addMessage(data.error_message || 'Nao foi possivel processar a consulta.', 'error');
        }

        setServerStatus('online');
    } catch (error) {
        console.error('Error sending message:', error);
        removeLoadingMessage(loadingMessageId);
        setServerStatus('offline');

        const errorMessage = buildUserFacingError(error);
        addMessage(errorMessage, 'error');
        showErrorToast('Nao foi possivel concluir a consulta. Verifique o agent e tente novamente.');
    } finally {
        isLoading = false;
        updateInputState();
        elements.messageInput.focus();
    }
}

function buildUserFacingError(error) {
    if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
        return 'Nao foi possivel conectar ao servidor do DataVisSUS. Confirme se o agent esta rodando e tente novamente.';
    }
    if (error.message.includes('HTTP 429')) {
        return 'Muitas consultas em pouco tempo. Aguarde alguns segundos antes de tentar novamente.';
    }
    if (error.message.includes('HTTP 5')) {
        return 'O servidor retornou erro interno. Tente novamente em alguns instantes.';
    }
    return `Erro de conexao: ${error.message}`;
}

function addMessage(content, type = 'assistant', metadata = null) {
    const messageData = {
        id: createMessageId(),
        content,
        type,
        timestamp: new Date().toISOString(),
        metadata
    };

    messageHistory.push(messageData);
    saveMessageHistory();
    elements.chatMessages.appendChild(createMessageElement(messageData));
    scrollToBottom();
}

function createMessageElement(messageData) {
    const { content, type, timestamp, metadata, id } = messageData;
    const message = document.createElement('div');
    message.className = `message ${type}-message`;
    message.dataset.messageId = id || createMessageId();

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.setAttribute('aria-hidden', 'true');
    avatar.innerHTML = `<i class="${getMessageIcon(type)}"></i>`;

    const contentWrap = document.createElement('div');
    contentWrap.className = 'message-content';

    const text = document.createElement('div');
    text.className = 'message-text';
    text.innerHTML = type === 'error'
        ? `<strong>Erro:</strong> ${escapeHtml(content)}`
        : formatMessageContent(content);

    const meta = document.createElement('div');
    meta.className = 'message-meta';

    const time = document.createElement('span');
    time.className = 'message-time';
    time.textContent = formatTime(timestamp);
    meta.appendChild(time);

    if (metadata && Number.isFinite(metadata.executionTime)) {
        const execution = document.createElement('span');
        execution.className = 'execution-time';
        execution.innerHTML = `<i class="fas fa-clock" aria-hidden="true"></i> ${metadata.executionTime.toFixed(2)}s`;
        meta.appendChild(execution);
    }

    if (type === 'assistant') {
        const copyButton = document.createElement('button');
        copyButton.type = 'button';
        copyButton.className = 'message-action';
        copyButton.innerHTML = '<i class="fas fa-copy" aria-hidden="true"></i><span>Copiar</span>';
        copyButton.setAttribute('aria-label', 'Copiar resposta');
        copyButton.addEventListener('click', () => copyMessage(content, copyButton));
        meta.appendChild(copyButton);
    }

    contentWrap.appendChild(text);
    contentWrap.appendChild(meta);
    message.appendChild(avatar);
    message.appendChild(contentWrap);
    return message;
}

function getMessageIcon(type) {
    if (type === 'user') return 'fas fa-user';
    if (type === 'error') return 'fas fa-triangle-exclamation';
    return 'fas fa-robot';
}

async function copyMessage(content, button) {
    try {
        await navigator.clipboard.writeText(content);
        const original = button.innerHTML;
        button.innerHTML = '<i class="fas fa-check" aria-hidden="true"></i><span>Copiado</span>';
        setTimeout(() => {
            button.innerHTML = original;
        }, 1600);
    } catch (error) {
        console.warn('Clipboard unavailable:', error);
        showErrorToast('Nao foi possivel copiar a resposta.');
    }
}

function formatMessageContent(content) {
    let formatted = escapeHtml(content);
    formatted = formatted.replace(/```([\s\S]*?)```/g, '<pre><code>$1</code></pre>');
    formatted = formatted.replace(/`([^`]+)`/g, '<code>$1</code>');
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
    formatted = formatted.replace(/\n/g, '<br>');
    return formatted;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMins = Math.floor((now - date) / 60000);

    if (diffMins < 1) return 'Agora';
    if (diffMins < 60) return `${diffMins}m atras`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h atras`;

    return date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function scrollToBottom() {
    elements.chatMessages.scrollTop = elements.chatMessages.scrollHeight;
}

function addLoadingMessage() {
    const loadingId = `loading-${Date.now()}`;
    const loading = document.createElement('div');
    loading.className = 'message assistant-message loading-message';
    loading.id = loadingId;
    loading.innerHTML = `
        <div class="message-avatar" aria-hidden="true">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="message-text">
                <div class="inline-loading">
                    <span class="inline-spinner" aria-hidden="true"></span>
                    <span>Consultando dados e preparando a resposta...</span>
                </div>
            </div>
        </div>
    `;
    elements.chatMessages.appendChild(loading);
    scrollToBottom();
    return loadingId;
}

function removeLoadingMessage(loadingId) {
    const loading = document.getElementById(loadingId);
    if (loading) loading.remove();
}

async function showSchemaModal() {
    schemaTriggerElement = document.activeElement;
    elements.schemaModal.classList.add('show');
    document.body.classList.add('modal-open');
    elements.closeSchemaModal.focus();
    setSchemaState('empty', 'Selecione uma tabela e clique em "Carregar schema".');
    await loadSchemaTables();
}

function hideSchemaModal() {
    elements.schemaModal.classList.remove('show');
    document.body.classList.remove('modal-open');
    if (schemaTriggerElement && typeof schemaTriggerElement.focus === 'function') {
        schemaTriggerElement.focus();
    }
}

async function loadSelectedSchema() {
    const tableSelect = document.getElementById('tableSelect');
    const loadSchemaBtn = document.getElementById('loadSchemaBtn');
    const selectedTable = tableSelect.value;

    try {
        loadSchemaBtn.disabled = true;
        loadSchemaBtn.innerHTML = '<i class="fas fa-spinner fa-spin" aria-hidden="true"></i><span>Carregando...</span>';
        setSchemaState('loading', 'Carregando schema da tabela selecionada...');

        let url = `${API_BASE_URL}/schema`;
        if (selectedTable) {
            url += `?table=${encodeURIComponent(selectedTable)}`;
        }

        const response = await fetch(url, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include',
            mode: 'cors',
            cache: 'no-cache'
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        renderSchema(data.schema || 'Schema indisponivel para esta selecao.');
    } catch (error) {
        console.error('Error loading schema:', error);
        setSchemaState('error', `Erro ao carregar schema: ${error.message}`);
        showErrorToast('Erro ao carregar o schema do banco de dados.');
    } finally {
        loadSchemaBtn.disabled = false;
        loadSchemaBtn.innerHTML = '<i class="fas fa-sync-alt" aria-hidden="true"></i><span>Carregar schema</span>';
    }
}

function setSchemaState(state, message) {
    elements.schemaContent.className = `schema-content ${state}-state`;
    elements.schemaContent.textContent = message;
}

function renderSchema(schema) {
    elements.schemaContent.className = 'schema-content loaded-state';
    if (schema.includes('<div class="sample-data-table">') || schema.includes('class="schema-table"')) {
        elements.schemaContent.innerHTML = schema;
        setTimeout(initializeTableSearch, 50);
    } else {
        elements.schemaContent.classList.add('text-content');
        elements.schemaContent.textContent = schema;
    }
}

function clearChat() {
    if (!confirm('Limpar toda a conversa e iniciar uma nova sessao?')) {
        return;
    }
    elements.chatMessages.innerHTML = '';
    messageHistory = [];
    resetSessionId();
    localStorage.removeItem(CHAT_HISTORY_KEY);
    addWelcomeMessage();
    elements.messageInput.focus();
}

function addWelcomeMessage() {
    const welcome = {
        id: createMessageId(),
        content: 'Ola! Eu ajudo a consultar dados de saude publica em linguagem natural. Experimente perguntar por rankings de municipios, medias por grupo demografico ou recortes de mortalidade.',
        type: 'assistant',
        timestamp: new Date().toISOString(),
        metadata: null
    };
    elements.chatMessages.appendChild(createMessageElement(welcome));
    scrollToBottom();
}

async function checkServerStatus() {
    setServerStatus('checking');
    try {
        const webResponse = await fetch(`${API_BASE_URL}/health`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include',
            mode: 'cors',
            cache: 'no-cache'
        });

        if (!webResponse.ok) {
            setServerStatus('offline');
            return;
        }

        const agentResponse = await fetch(`${API_BASE_URL}/agent-health`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include',
            mode: 'cors',
            cache: 'no-cache'
        });

        if (!agentResponse.ok) {
            setServerStatus('offline');
            return;
        }

        const agentData = await agentResponse.json();
        setServerStatus(agentData.agent_status === 'online' ? 'online' : 'offline');
    } catch (error) {
        console.error('Server health check failed:', error);
        setServerStatus('offline');
    }
}

function setServerStatus(status) {
    elements.statusIndicator.classList.remove('status-checking', 'status-online', 'status-offline');
    elements.statusIndicator.classList.add(`status-${status}`);

    const labels = {
        checking: 'Verificando...',
        online: 'Online',
        offline: 'Agent offline'
    };
    elements.statusText.textContent = labels[status] || labels.offline;
}

function showErrorToast(message) {
    document.getElementById('errorText').textContent = message;
    elements.errorToast.classList.add('show');
    setTimeout(hideErrorToast, 5000);
}

function hideErrorToast() {
    elements.errorToast.classList.remove('show');
}

function saveMessageHistory() {
    try {
        const persistable = messageHistory
            .filter((message) => message.type !== 'error')
            .slice(-MAX_HISTORY_MESSAGES);
        localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(persistable));
    } catch (error) {
        console.warn('Failed to save message history:', error);
    }
}

function loadMessageHistory() {
    try {
        const saved = localStorage.getItem(CHAT_HISTORY_KEY);
        if (!saved) {
            addWelcomeMessage();
            return;
        }

        messageHistory = JSON.parse(saved);
        elements.chatMessages.innerHTML = '';

        if (messageHistory.length >= MAX_HISTORY_MESSAGES) {
            const separator = document.createElement('div');
            separator.className = 'context-separator';
            separator.innerHTML = '<span><i class="fas fa-brain" aria-hidden="true"></i> Inicio do contexto da IA</span>';
            elements.chatMessages.appendChild(separator);
        }

        messageHistory.forEach((messageData) => {
            elements.chatMessages.appendChild(createMessageElement(messageData));
        });
        scrollToBottom();
    } catch (error) {
        console.warn('Failed to load message history:', error);
        elements.chatMessages.innerHTML = '';
        messageHistory = [];
        addWelcomeMessage();
    }
}

function createSessionId() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
        return window.crypto.randomUUID();
    }
    return `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function createMessageId() {
    return `msg-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function ensureSessionId() {
    if (!localStorage.getItem(SESSION_STORAGE_KEY)) {
        localStorage.setItem(SESSION_STORAGE_KEY, createSessionId());
    }
}

function getSessionId() {
    ensureSessionId();
    return localStorage.getItem(SESSION_STORAGE_KEY);
}

function resetSessionId() {
    localStorage.setItem(SESSION_STORAGE_KEY, createSessionId());
}

async function loadSchemaTables() {
    const tableSelect = document.getElementById('tableSelect');
    if (!tableSelect) return;

    try {
        const response = await fetch(`${API_BASE_URL}/schema`, {
            method: 'GET',
            headers: {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'include',
            mode: 'cors',
            cache: 'no-cache'
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        const selectedValue = tableSelect.value;
        tableSelect.innerHTML = '';

        const allOption = document.createElement('option');
        allOption.value = '';
        allOption.textContent = 'Esquema completo';
        tableSelect.appendChild(allOption);

        (data.tables || []).forEach((tableName) => {
            const option = document.createElement('option');
            option.value = tableName;
            option.textContent = tableName;
            tableSelect.appendChild(option);
        });

        if (selectedValue && (data.tables || []).includes(selectedValue)) {
            tableSelect.value = selectedValue;
        }
    } catch (error) {
        console.error('Error loading schema tables:', error);
    }
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), wait);
    };
}

function initializeTheme() {
    const savedTheme = localStorage.getItem(THEME_KEY) || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateThemeIcon(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', newTheme);
    localStorage.setItem(THEME_KEY, newTheme);
    updateThemeIcon(newTheme);
}

function updateThemeIcon(theme) {
    const icon = elements.themeToggle.querySelector('i');
    if (theme === 'dark') {
        icon.className = 'fas fa-moon';
        elements.themeToggle.title = 'Alternar para tema claro';
        elements.themeToggle.setAttribute('aria-label', 'Alternar para tema claro');
    } else {
        icon.className = 'fas fa-sun';
        elements.themeToggle.title = 'Alternar para tema escuro';
        elements.themeToggle.setAttribute('aria-label', 'Alternar para tema escuro');
    }
}

function initializeTableSearch() {
    const searchInputs = document.querySelectorAll('.column-filter');
    const table = document.getElementById('schema-data-table');
    if (!table || !searchInputs.length) return;

    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));

    searchInputs.forEach((input, columnIndex) => {
        input.addEventListener('input', debounce(() => {
            filterTable();
            highlightSearchTerms();
        }, 200));

        input.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                input.value = '';
                filterTable();
                highlightSearchTerms();
            }
            if (event.key === 'ArrowRight' && event.ctrlKey) {
                event.preventDefault();
                const nextInput = searchInputs[columnIndex + 1];
                if (nextInput) nextInput.focus();
            }
            if (event.key === 'ArrowLeft' && event.ctrlKey) {
                event.preventDefault();
                const prevInput = searchInputs[columnIndex - 1];
                if (prevInput) prevInput.focus();
            }
        });
    });

    function filterTable() {
        let visibleCount = 0;
        rows.forEach((row) => {
            let showRow = true;
            searchInputs.forEach((input, columnIndex) => {
                const searchTerm = input.value.toLowerCase().trim();
                if (!searchTerm) return;

                const cell = row.cells[columnIndex];
                if (cell && !cell.textContent.toLowerCase().includes(searchTerm)) {
                    showRow = false;
                }
            });

            row.classList.toggle('hidden-row', !showRow);
            row.classList.toggle('highlight-match', showRow && hasActiveFilter());
            if (showRow) visibleCount++;
        });
        updateFilterCount(visibleCount, rows.length);
    }

    function hasActiveFilter() {
        return Array.from(searchInputs).some((input) => input.value.trim().length > 0);
    }

    function updateFilterCount(visible, total) {
        const filteredRecords = document.querySelector('.filtered-records');
        const filteredCount = document.querySelector('.filtered-count');
        if (!filteredRecords) return;

        filteredRecords.style.display = visible !== total ? 'flex' : 'none';
        if (filteredCount) {
            filteredCount.textContent = visible.toLocaleString('pt-BR');
        }
    }

    function highlightSearchTerms() {
        rows.forEach((row) => {
            Array.from(row.cells).forEach((cell) => {
                if (cell.dataset.originalText) {
                    cell.innerHTML = cell.dataset.originalText;
                    delete cell.dataset.originalText;
                }
            });
        });

        searchInputs.forEach((input, columnIndex) => {
            const searchTerm = input.value.trim();
            if (searchTerm.length <= 1) return;

            rows.forEach((row) => {
                if (row.classList.contains('hidden-row')) return;
                const cell = row.cells[columnIndex];
                if (!cell || cell.querySelector('.null-value')) return;

                cell.dataset.originalText = cell.innerHTML;
                const regex = new RegExp(`(${searchTerm.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
                cell.innerHTML = cell.dataset.originalText.replace(regex, '<mark>$1</mark>');
            });
        });
    }

    function clearAllFilters() {
        searchInputs.forEach((input) => {
            input.value = '';
        });
        rows.forEach((row) => {
            row.classList.remove('hidden-row', 'highlight-match');
            Array.from(row.cells).forEach((cell) => {
                if (cell.dataset.originalText) {
                    cell.innerHTML = cell.dataset.originalText;
                    delete cell.dataset.originalText;
                }
            });
        });
        updateFilterCount(rows.length, rows.length);
        searchInputs[0].focus();
    }

    const filterBar = document.querySelector('.filter-bar');
    if (filterBar && !filterBar.querySelector('.clear-filters-btn')) {
        const clearButton = document.createElement('button');
        clearButton.className = 'clear-filters-btn';
        clearButton.type = 'button';
        clearButton.innerHTML = '<i class="fas fa-eraser" aria-hidden="true"></i>';
        clearButton.title = 'Limpar todos os filtros';
        clearButton.setAttribute('aria-label', 'Limpar todos os filtros');
        clearButton.addEventListener('click', clearAllFilters);

        const clearWrapper = document.createElement('div');
        clearWrapper.className = 'clear-filters-wrapper';
        clearWrapper.appendChild(clearButton);
        filterBar.appendChild(clearWrapper);
    }
}

setInterval(checkServerStatus, 30000);

document.addEventListener('visibilitychange', function() {
    if (!document.hidden) {
        checkServerStatus();
    }
});

window.ChatApp = {
    sendMessage,
    clearChat,
    showSchemaModal,
    checkServerStatus,
    toggleTheme,
    initializeTableSearch
};
