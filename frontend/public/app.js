const API_BASE_URL = '/api';
const SESSION_STORAGE_KEY = 'chatSessionId';
const CHAT_HISTORY_KEY = 'chatHistory';
const THEME_KEY = 'theme';
const DEBUG_MODE_KEY = 'debugModeEnabled';
const MAX_CONVERSATION_TURNS = 10;
const MAX_HISTORY_MESSAGES = MAX_CONVERSATION_TURNS * 2;
const MAX_MESSAGE_LENGTH = 1000;

let isLoading = false;
let isDebugEnabled = false;
let messageHistory = [];
let schemaTriggerElement = null;

const elements = {
    messageInput: document.getElementById('messageInput'),
    sendBtn: document.getElementById('sendBtn'),
    chatMessages: document.getElementById('chatMessages'),
    chatWelcome: document.getElementById('chatWelcome'),
    schemaModal: document.getElementById('schemaModal'),
    schemaBtn: document.getElementById('schemaBtn'),
    closeSchemaModal: document.getElementById('closeSchemaModal'),
    clearBtn: document.getElementById('clearBtn'),
    statusIndicator: document.getElementById('statusIndicator'),
    statusText: document.getElementById('statusText'),
    errorToast: document.getElementById('errorToast'),
    schemaContent: document.getElementById('schemaContent'),
    questionButtons: document.querySelectorAll('[data-question]'),
    themeToggle: document.getElementById('themeToggle'),
    debugToggle: document.getElementById('debugToggle'),
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
    initializeDebugMode();
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
    if (elements.debugToggle) {
        elements.debugToggle.addEventListener('click', toggleDebugMode);
    }

    elements.schemaModal.addEventListener('click', function(event) {
        if (event.target === elements.schemaModal) {
            hideSchemaModal();
        }
    });

    const loadSchemaBtn = document.getElementById('loadSchemaBtn');
    if (loadSchemaBtn) {
        loadSchemaBtn.addEventListener('click', loadSelectedSchema);
    }

    elements.questionButtons.forEach((button) => {
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
                session_id: getSessionId(),
                debug: isDebugEnabled
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
                sql: data.sql || data.sql_query || null,
                chart: data.chart || null,
                debug: isDebugEnabled ? data.debug || null : null,
                agentMetadata: isDebugEnabled ? data.metadata || {} : null
            });
        } else {
            const errorMessage = data.error_message || data.answer || data.response || 'Nao foi possivel processar a consulta.';
            addMessage(errorMessage, 'error', {
                executionTime: data.execution_time,
                sql: data.sql || data.sql_query || null,
                debug: isDebugEnabled ? data.debug || null : null,
                agentMetadata: isDebugEnabled ? data.metadata || {} : null
            });
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
        return 'Nao foi possivel conectar ao agent do DataVisSUS. Confirme se o servico esta rodando e tente novamente.';
    }
    if (error.message.includes('HTTP 429')) {
        return 'Muitas consultas em pouco tempo. Aguarde alguns segundos antes de tentar novamente.';
    }
    if (error.message.includes('HTTP 5')) {
        return 'O agent retornou erro interno. Tente novamente em alguns instantes ou refine o recorte da consulta.';
    }
    return `Erro de conexao: ${error.message}`;
}

function showWelcomeState() {
    if (elements.chatWelcome) {
        elements.chatWelcome.style.display = '';
        elements.chatWelcome.querySelectorAll('.welcome-steps li').forEach(el => {
            el.style.animation = 'none';
            void el.offsetHeight;
            el.style.animation = '';
        });
    }
    elements.chatMessages.style.display = 'none';
}

function hideWelcomeState() {
    if (elements.chatWelcome) elements.chatWelcome.style.display = 'none';
    elements.chatMessages.style.display = '';
}

function addMessage(content, type = 'assistant', metadata = null) {
    hideWelcomeState();

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
    if (metadata && metadata.chart) {
        const chartElement = createChartElement(metadata.chart);
        if (chartElement) {
            message.classList.add('message-has-chart');
            contentWrap.appendChild(chartElement);
        }
    }
    if (metadata && metadata.debug) {
        const debugPanel = createDebugPanel(metadata);
        if (debugPanel) {
            message.classList.add('message-has-debug');
            contentWrap.appendChild(debugPanel);
        }
    }
    contentWrap.appendChild(meta);
    message.appendChild(avatar);
    message.appendChild(contentWrap);
    return message;
}

function initializeDebugMode() {
    isDebugEnabled = localStorage.getItem(DEBUG_MODE_KEY) === 'true';
    updateDebugToggle();
}

function toggleDebugMode() {
    isDebugEnabled = !isDebugEnabled;
    localStorage.setItem(DEBUG_MODE_KEY, String(isDebugEnabled));
    updateDebugToggle();
}

function updateDebugToggle() {
    if (!elements.debugToggle) return;
    elements.debugToggle.classList.toggle('active', isDebugEnabled);
    elements.debugToggle.setAttribute('aria-pressed', String(isDebugEnabled));
    elements.debugToggle.title = isDebugEnabled ? 'Debug ativo' : 'Debug inativo';
}

function createDebugPanel(metadata) {
    const debugPayload = metadata.debug;
    if (!debugPayload || !Array.isArray(debugPayload.steps)) return null;

    const panel = document.createElement('details');
    panel.className = 'debug-panel';
    panel.open = true;

    const summary = document.createElement('summary');
    summary.className = 'debug-summary';
    summary.innerHTML = '<i class="fas fa-bug" aria-hidden="true"></i><span>Debug</span>';

    const count = document.createElement('span');
    count.className = 'debug-count';
    count.textContent = `${debugPayload.steps.length} nodes`;
    summary.appendChild(count);
    panel.appendChild(summary);

    const body = document.createElement('div');
    body.className = 'debug-body';

    if (metadata.sql) {
        appendDebugCodeSection(body, 'SQL final', metadata.sql);
    }

    const agentMetadata = metadata.agentMetadata || {};
    appendDebugFacts(body, [
        ['Modelo', agentMetadata.current_model && agentMetadata.current_model.model_name],
        ['Rota', agentMetadata.query_route],
        ['Tabelas', formatDebugInline(agentMetadata.tables_used)],
        ['Retries', agentMetadata.retry_count],
        ['Erros', agentMetadata.error_count]
    ]);

    const stepsList = document.createElement('div');
    stepsList.className = 'debug-steps';
    debugPayload.steps.forEach((step) => {
        stepsList.appendChild(createDebugStep(step));
    });
    body.appendChild(stepsList);
    panel.appendChild(body);

    return panel;
}

function createDebugStep(step) {
    const item = document.createElement('details');
    item.className = `debug-step debug-step-${step.status || 'completed'}`;

    const summary = document.createElement('summary');
    summary.className = 'debug-step-summary';

    const label = document.createElement('span');
    label.className = 'debug-step-label';
    label.textContent = `${step.index}. ${step.title || step.node}`;
    summary.appendChild(label);

    const node = document.createElement('code');
    node.textContent = step.node;
    summary.appendChild(node);
    item.appendChild(summary);

    const data = step.data || {};
    const body = document.createElement('div');
    body.className = 'debug-step-body';

    if (data.generated_sql) {
        appendDebugCodeSection(body, 'SQL gerada', data.generated_sql);
    }
    if (data.validated_sql && data.validated_sql !== data.generated_sql) {
        appendDebugCodeSection(body, 'SQL validada', data.validated_sql);
    }
    if (data.final_response) {
        appendDebugTextSection(body, 'Resposta final', data.final_response);
    }

    const remaining = { ...data };
    delete remaining.generated_sql;
    delete remaining.validated_sql;
    delete remaining.final_response;
    if (Object.keys(remaining).length > 0) {
        appendDebugJsonSection(body, 'Estado', remaining);
    }

    item.appendChild(body);
    return item;
}

function appendDebugFacts(container, facts) {
    const visibleFacts = facts.filter(([, value]) => value !== null && value !== undefined && value !== '');
    if (visibleFacts.length === 0) return;

    const grid = document.createElement('div');
    grid.className = 'debug-facts';
    visibleFacts.forEach(([label, value]) => {
        const item = document.createElement('div');
        item.className = 'debug-fact';
        const labelEl = document.createElement('span');
        labelEl.textContent = label;
        const valueEl = document.createElement('strong');
        valueEl.textContent = String(value);
        item.appendChild(labelEl);
        item.appendChild(valueEl);
        grid.appendChild(item);
    });
    container.appendChild(grid);
}

function appendDebugCodeSection(container, title, code) {
    const section = createDebugSection(title);
    const pre = document.createElement('pre');
    const codeEl = document.createElement('code');
    codeEl.textContent = code;
    pre.appendChild(codeEl);
    section.appendChild(pre);
    container.appendChild(section);
}

function appendDebugTextSection(container, title, value) {
    const section = createDebugSection(title);
    const text = document.createElement('p');
    text.textContent = value;
    section.appendChild(text);
    container.appendChild(section);
}

function appendDebugJsonSection(container, title, value) {
    const section = createDebugSection(title);
    const pre = document.createElement('pre');
    const codeEl = document.createElement('code');
    codeEl.textContent = JSON.stringify(value, null, 2);
    pre.appendChild(codeEl);
    section.appendChild(pre);
    container.appendChild(section);
}

function createDebugSection(title) {
    const section = document.createElement('section');
    section.className = 'debug-section';
    const heading = document.createElement('h3');
    heading.textContent = title;
    section.appendChild(heading);
    return section;
}

function formatDebugInline(value) {
    if (Array.isArray(value)) return value.join(', ');
    if (value && typeof value === 'object') return JSON.stringify(value);
    return value;
}

function createChartElement(chartPayload) {
    const spec = chartPayload && chartPayload.spec;
    const echartsOption = chartPayload && chartPayload.echarts;
    if (!chartPayload.requested || !spec) return null;

    const container = document.createElement('div');
    container.className = 'chart-panel';

    const header = document.createElement('div');
    header.className = 'chart-header';

    const title = document.createElement('div');
    title.className = 'chart-title';
    title.textContent = spec.title || chartTypeLabel(spec.chart_type);
    header.appendChild(title);

    const badge = document.createElement('div');
    badge.className = 'chart-type-badge';
    badge.textContent = shortChartTypeLabel(spec.chart_type);
    header.appendChild(badge);
    container.appendChild(header);

    if (!spec.chartable) {
        const empty = document.createElement('div');
        empty.className = 'chart-empty';
        empty.textContent = spec.reason || 'Nao foi possivel gerar um grafico validado para esse resultado.';
        container.appendChild(empty);
        return container;
    }

    if (echartsOption && window.echarts && typeof window.echarts.init === 'function') {
        renderECharts(container, echartsOption, spec);
    } else {
        // Fallback when ECharts is unavailable or the spec is a plain table.
        renderTableChart(container, spec);
    }

    if (Array.isArray(spec.warnings) && spec.warnings.length > 0) {
        const warnings = document.createElement('div');
        warnings.className = 'chart-warnings';
        warnings.textContent = spec.warnings.map(w => w.message).join(' ');
        container.appendChild(warnings);
    }

    return container;
}

function renderECharts(container, echartsOption, spec) {
    const target = document.createElement('div');
    target.className = `echarts-chart echarts-chart-${spec.chart_type || 'default'}`;
    target.setAttribute('role', 'img');
    target.setAttribute('aria-label', buildChartAriaLabel(spec));
    container.appendChild(target);

    try {
        const chart = window.echarts.init(target, null, { renderer: 'svg' });
        chart.setOption(echartsOption, true);
        if (typeof ResizeObserver === 'function') {
            const resizeObserver = new ResizeObserver(() => chart.resize());
            resizeObserver.observe(target);
            target.__echartsResizeObserver = resizeObserver;
        } else {
            window.addEventListener('resize', () => chart.resize(), { passive: true });
        }
    } catch (error) {
        console.warn('Failed to render ECharts chart, falling back to table:', error);
        target.remove();
        renderFallbackTable(container, spec);
        return;
    }

    renderPerItemLegend(container, echartsOption);
}

function renderPerItemLegend(container, echartsOption) {
    const legendData = echartsOption._legend;
    if (!Array.isArray(legendData) || legendData.length === 0) return;

    const legend = document.createElement('div');
    const hasMetrics = legendData.some(item => item.value !== undefined || item.percent !== undefined);
    legend.className = hasMetrics ? 'chart-legend chart-legend-detailed' : 'chart-legend';

    legendData.forEach((legendItem) => {
        const { name, color } = legendItem;
        const item = document.createElement('div');
        item.className = 'chart-legend-item';

        const label = document.createElement('span');
        label.className = 'chart-legend-label';

        const swatch = document.createElement('span');
        swatch.className = 'chart-swatch';
        swatch.style.background = color;
        label.appendChild(swatch);

        const labelText = document.createElement('span');
        labelText.className = 'chart-legend-name';
        labelText.textContent = name;
        label.appendChild(labelText);
        item.appendChild(label);

        if (hasMetrics) {
            const metric = document.createElement('span');
            metric.className = 'chart-legend-metric';
            metric.textContent = formatLegendMetric(legendItem);
            item.appendChild(metric);
        }

        legend.appendChild(item);
    });

    container.appendChild(legend);
}

function formatLegendMetric(item) {
    const parts = [];
    if (typeof item.value === 'number' && Number.isFinite(item.value)) {
        parts.push(item.value.toLocaleString('pt-BR'));
    }
    if (typeof item.percent === 'number' && Number.isFinite(item.percent)) {
        parts.push(`${item.percent.toLocaleString('pt-BR', {
            minimumFractionDigits: item.percent < 10 ? 1 : 0,
            maximumFractionDigits: 1
        })}%`);
    }
    return parts.join(' / ');
}

function renderFallbackTable(container, spec) {
    if (Array.isArray(spec.data) && spec.data.length > 0) {
        renderTableChart(container, spec);
    } else {
        const empty = document.createElement('div');
        empty.className = 'chart-empty';
        empty.textContent = 'Nao foi possivel renderizar o grafico.';
        container.appendChild(empty);
    }
}

function renderTableChart(container, spec) {
    const rows = Array.isArray(spec.data) ? spec.data.slice(0, 12) : [];
    const table = document.createElement('table');
    table.className = 'chart-table';
    if (rows.length === 0) {
        container.appendChild(table);
        return;
    }
    const columns = Object.keys(rows[0]);
    const thead = document.createElement('thead');
    const headRow = document.createElement('tr');
    columns.forEach(column => {
        const th = document.createElement('th');
        th.textContent = formatFieldLabel(column);
        headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    rows.forEach(row => {
        const tr = document.createElement('tr');
        columns.forEach(column => {
            const td = document.createElement('td');
            td.textContent = formatTableCell(row[column]);
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    container.appendChild(table);
}

function chartTypeLabel(type) {
    const labels = {
        bar: 'Grafico de barras',
        line: 'Grafico de linha',
        area: 'Grafico de area',
        scatter: 'Grafico de dispersao',
        pie: 'Grafico de proporcao',
        donut: 'Grafico de proporcao',
        kpi: 'Indicador',
        table: 'Tabela'
    };
    return labels[type] || 'Grafico';
}

function shortChartTypeLabel(type) {
    const labels = {
        bar: 'Barras',
        line: 'Linha',
        area: 'Area',
        scatter: 'Dispersao',
        pie: 'Pizza',
        donut: 'Donut',
        kpi: 'KPI',
        table: 'Tabela'
    };
    return labels[type] || 'Grafico';
}

function formatTableCell(value) {
    if (value === null || value === undefined) return '-';
    if (typeof value === 'number' && Number.isFinite(value)) {
        return value.toLocaleString('pt-BR');
    }
    return String(value);
}

function formatFieldLabel(field) {
    if (!field) return '';
    return String(field)
        .replace(/_/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
        .replace(/\b\w/g, char => char.toUpperCase());
}

function buildChartAriaLabel(spec) {
    const title = spec.title || chartTypeLabel(spec.chart_type);
    const x = formatFieldLabel(spec.x);
    const y = formatFieldLabel(spec.y);
    return `${title}. Eixo X: ${x}. Eixo Y: ${y}.`;
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
                <div class="thinking-dots" role="status" aria-label="Processando consulta">
                    <span class="thinking-dot"></span>
                    <span class="thinking-dot"></span>
                    <span class="thinking-dot"></span>
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
    showWelcomeState();
    elements.messageInput.focus();
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
            showWelcomeState();
            return;
        }

        messageHistory = JSON.parse(saved);
        if (!messageHistory.length) {
            showWelcomeState();
            return;
        }

        elements.chatMessages.innerHTML = '';
        hideWelcomeState();

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
        showWelcomeState();
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
