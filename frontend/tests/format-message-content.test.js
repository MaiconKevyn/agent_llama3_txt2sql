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
        setAttribute() {},
        addEventListener() {},
        querySelector() { return null; },
        querySelectorAll() { return []; },
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

function loadAppContext() {
    const source = fs.readFileSync(appPath, 'utf8');
    const documentStub = {
        body: { classList: { add() {}, remove() {} } },
        hidden: false,
        createElement,
        getElementById() { return createElement(); },
        querySelectorAll() { return []; },
        addEventListener() {}
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

test('buildChartFollowupQuestion preserves original query as hidden chart request', () => {
    const { buildChartFollowupQuestion } = loadAppContext();

    const question = buildChartFollowupQuestion('existe relacao entre idade e diagnostico de doenca respiratoria?');

    assert.match(question, /Gere um grafico adequado/);
    assert.match(question, /Mantenha exatamente o mesmo recorte/);
    assert.match(question, /Consulta original: existe relacao entre idade/);
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
