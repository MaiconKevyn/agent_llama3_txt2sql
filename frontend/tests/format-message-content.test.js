const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const appPath = path.join(__dirname, '..', 'public', 'app.js');

function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (char) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[char]));
}

function createElement() {
    let textValue = '';
    let htmlValue = '';

    return {
        style: {},
        dataset: {},
        classList: {
            add() {},
            remove() {},
            toggle() {},
            contains() { return false; }
        },
        appendChild() {},
        remove() {},
        focus() {},
        select() {},
        setAttribute() {},
        addEventListener() {},
        querySelector() { return null; },
        querySelectorAll() { return []; },
        value: '',
        get textContent() {
            return textValue;
        },
        set textContent(value) {
            textValue = value == null ? '' : String(value);
            htmlValue = escapeHtml(textValue);
        },
        get innerHTML() {
            return htmlValue;
        },
        set innerHTML(value) {
            htmlValue = value == null ? '' : String(value);
            textValue = htmlValue;
        }
    };
}

function loadAppContext(overrides = {}) {
    const source = fs.readFileSync(appPath, 'utf8');
    const body = {
        classList: { add() {}, remove() {} },
        appendChild(element) {
            this.lastAppended = element;
        },
        lastAppended: null
    };
    const documentStub = {
        body,
        hidden: false,
        createElement,
        getElementById() { return createElement(); },
        querySelectorAll() { return []; },
        addEventListener() {},
        execCommand() { return false; }
    };

    const context = {
        console,
        document: documentStub,
        window: {},
        localStorage: {
            getItem() { return null; },
            setItem() {},
            removeItem() {}
        },
        navigator: {
            clipboard: { writeText: async () => {} }
        },
        fetch: async () => { throw new Error('fetch is not available in this test'); },
        setInterval() { return 0; },
        setTimeout() { return 0; },
        clearTimeout() {},
        confirm() { return true; }
    };
    Object.assign(context, overrides);
    if (overrides.document) {
        context.document = { ...documentStub, ...overrides.document };
        context.document.body = overrides.document.body || documentStub.body;
    }
    if (overrides.navigator) {
        context.navigator = overrides.navigator;
    }

    vm.runInNewContext(source, context, { filename: appPath });
    return context;
}

test('formatMessageContent renders Markdown pipe tables as HTML tables', () => {
    const { formatMessageContent } = loadAppContext();
    const markdown = [
        '| Grupo | Internacoes | Mortes | Taxa de mortalidade |',
        '|---|---:|---:|---:|',
        '| Branca | 610.440 | 136.511 | 22,36% |',
        '| Preta | 75.604 | 20.159 | 26,66% |'
    ].join('\n');

    const html = formatMessageContent(markdown);

    assert.match(html, /<table class="markdown-table">/);
    assert.match(html, /<thead>/);
    assert.match(html, /<th>Grupo<\/th>/);
    assert.match(html, /<td class="[^"]*is-numeric[^"]*">610\.440<\/td>/);
    assert.doesNotMatch(html, /\|---\|/);
});

test('database explorer UI is separate from the chat surface', () => {
    const html = fs.readFileSync(path.join(__dirname, '..', 'public', 'index.html'), 'utf8');

    assert.match(html, /id="schemaModal"/);
    assert.match(html, /id="databaseTabExplore"/);
    assert.match(html, /id="databaseTabQuery"/);
    assert.match(html, /id="tableContextBar"/);
    assert.match(html, /Davint Lab/);
    assert.match(html, /TABNET/);
});

test('normalizeQueryLimit clamps direct SQL result limits', () => {
    const { normalizeQueryLimit } = loadAppContext();

    assert.equal(normalizeQueryLimit(''), 100);
    assert.equal(normalizeQueryLimit('0'), 1);
    assert.equal(normalizeQueryLimit('9999'), 500);
    assert.equal(normalizeQueryLimit('25'), 25);
});

test('buildTableContextQuestion creates an editable table-specific prompt', () => {
    const { buildTableContextQuestion } = loadAppContext();

    assert.equal(
        buildTableContextQuestion({ table_schema: 'main', table_name: 'internacoes' }),
        'Quero tirar uma duvida usando a tabela main.internacoes como contexto. Que perguntas posso fazer com esta tabela?'
    );
});

test('createTableContextPayload keeps only trusted table identifiers', () => {
    const { createTableContextPayload } = loadAppContext();

    const payload = createTableContextPayload({
        table_schema: 'main',
        table_name: 'internacoes',
        columns: [{ column_name: 'MORTE' }]
    });

    assert.equal(payload.table_schema, 'main');
    assert.equal(payload.table_name, 'internacoes');
    assert.equal(Object.hasOwn(payload, 'columns'), false);
});

test('server proxy forwards table_context to agent API', () => {
    const server = fs.readFileSync(path.join(__dirname, '..', 'server.js'), 'utf8');

    assert.match(server, /table_context/);
});

test('database modal uses a stable panel stage for tab content', () => {
    const html = fs.readFileSync(path.join(__dirname, '..', 'public', 'index.html'), 'utf8');

    assert.match(html, /class="[^"]*database-panel-stage[^"]*"/);
    assert.match(html, /<div class="database-panel-stage"[^>]*>/);
    assert.match(html, /id="databasePanelExplore"/);
    assert.match(html, /id="databasePanelQuery"/);
    assert.match(html, /id="databasePanelAbout"/);
    assert.match(html, /id="databasePanelFaq"/);

    const stageIndex = html.indexOf('class="database-panel-stage"');
    const exploreIndex = html.indexOf('id="databasePanelExplore"');
    const faqIndex = html.indexOf('id="databasePanelFaq"');

    assert.ok(stageIndex > 0, 'database-panel-stage must exist');
    assert.ok(exploreIndex > stageIndex, 'Explore panel must live inside the stage');
    assert.ok(faqIndex > stageIndex, 'FAQ panel must live inside the stage');
});

test('buildChartFollowupQuestion asks for a chart from the current answer', () => {
    const { buildChartFollowupQuestion } = loadAppContext();

    const question = buildChartFollowupQuestion('Compare os municipios com maior mortalidade e destaque o lider.');

    assert.match(question, /grafico/i);
    assert.match(question, /dessa resposta|ultimo resultado|dados ja retornados/i);
    assert.doesNotMatch(question, /Consulta original:/);
});

test('copyMessage writes the raw assistant response to navigator clipboard', async () => {
    let copiedText = null;
    const button = createElement();
    button.innerHTML = '<i class="fas fa-copy"></i><span>Copiar</span>';
    const { copyMessage } = loadAppContext({
        navigator: {
            clipboard: {
                writeText: async (value) => {
                    copiedText = value;
                }
            }
        },
        setTimeout() { return 0; }
    });

    await copyMessage('Resposta com **markdown** e tabela', button);

    assert.equal(copiedText, 'Resposta com **markdown** e tabela');
    assert.match(button.innerHTML, /Copiado/);
});

test('copyMessage falls back to textarea copy when navigator clipboard is blocked', async () => {
    const appended = [];
    const documentStub = {
        body: {
            classList: { add() {}, remove() {} },
            appendChild(element) {
                appended.push(element);
            }
        },
        hidden: false,
        createElement,
        getElementById() { return createElement(); },
        querySelectorAll() { return []; },
        addEventListener() {},
        execCommand(command) {
            assert.equal(command, 'copy');
            return true;
        }
    };
    const button = createElement();
    button.innerHTML = '<i class="fas fa-copy"></i><span>Copiar</span>';
    const { copyMessage } = loadAppContext({
        console: { ...console, warn() {} },
        document: documentStub,
        navigator: {
            clipboard: {
                writeText: async () => {
                    throw new Error('permission denied');
                }
            }
        },
        setTimeout() { return 0; }
    });

    await copyMessage('Texto para fallback', button);

    assert.equal(appended.length, 1);
    assert.equal(appended[0].value, 'Texto para fallback');
    assert.match(button.innerHTML, /Copiado/);
});

test('server proxy forwards chart_from_last_result to agent API', () => {
    const server = fs.readFileSync(path.join(__dirname, '..', 'server.js'), 'utf8');

    assert.match(server, /chart_from_last_result/);
});

test('database modal CSS keeps shell stable and content scrollable', () => {
    const css = fs.readFileSync(path.join(__dirname, '..', 'public', 'styles.css'), 'utf8');

    assert.match(css, /\.database-modal-content\s*\{[^}]*height:\s*min\(/s);
    assert.match(css, /\.database-modal-content\s*\{[^}]*overflow:\s*hidden/s);
    assert.match(css, /\.database-panel-stage\s*\{[^}]*min-height:\s*0/s);
    assert.match(css, /\.database-panel-stage\s*\{[^}]*overflow:\s*hidden/s);
    assert.match(css, /\.database-panel\.active\s*\{[^}]*height:\s*100%/s);
});

test('database tab panels own internal scroll instead of resizing modal', () => {
    const css = fs.readFileSync(path.join(__dirname, '..', 'public', 'styles.css'), 'utf8');

    assert.match(css, /\.database-browser\s*\{[^}]*height:\s*100%/s);
    assert.match(css, /\.query-console\s*\{[^}]*height:\s*100%/s);
    assert.match(css, /\.info-grid\s*\{[^}]*overflow:\s*auto/s);
    assert.match(css, /\.faq-grid\s*\{[^}]*overflow:\s*auto/s);
    assert.match(css, /\.database-query-result\s*\{[^}]*min-height:\s*0/s);
});

test('database modal has a stable mobile height contract', () => {
    const css = fs.readFileSync(path.join(__dirname, '..', 'public', 'styles.css'), 'utf8');

    assert.match(css, /@media\s*\(max-width:\s*768px\)[\s\S]*\.database-modal-content\s*\{[\s\S]*height:\s*min\(/);
    assert.match(css, /@media\s*\(max-width:\s*768px\)[\s\S]*\.database-browser\s*\{[\s\S]*height:\s*100%/);
    assert.match(css, /@media\s*\(max-width:\s*768px\)[\s\S]*\.database-table-list\s*\{[\s\S]*min-height:/);
});

test('chat loading state gives progressive query feedback', () => {
    const source = fs.readFileSync(appPath, 'utf8');
    const css = fs.readFileSync(path.join(__dirname, '..', 'public', 'styles.css'), 'utf8');

    assert.match(source, /LOADING_STATUS_STEPS/);
    assert.match(source, /Selecionando tabelas e contexto do banco/);
    assert.match(source, /Validando SQL e contratos semanticos/);
    assert.match(source, /Executando no DuckDB e revisando o resultado/);
    assert.match(source, /data-loading-status/);
    assert.match(source, /loadingStatusTimers/);
    assert.match(css, /\.loading-status\s*\{/);
});
