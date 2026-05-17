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
