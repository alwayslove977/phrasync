// Exercise the real i18n engine + DOM half with a fake DOM, in the exact order
// static/index.html loads them. No DOM library, no bundler: classic scripts are
// evaluated as separate scripts in one vm context, so `window === globalThis`
// and top-level let/const bindings are shared across files exactly as they are
// in the browser. That makes the boundary between i18n.js and i18n-dom.js
// testable rather than merely asserted in prose.
//
// Usage: node tests/i18n_ui.cjs [exports|language|dom-state|observer|structure|assembled|bidirectional|priority]
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const ROOT = path.join(__dirname, '..');
const read = name => fs.readFileSync(path.join(ROOT, 'static', name), 'utf8');

/* ------------------------------------------------------------------ fake DOM */

class FakeCustomEvent {
  constructor(type, init) { this.type = type; this.detail = init?.detail; }
}

function makeSelect() {
  return {
    dataset: {},
    options: [],
    listeners: [],
    _value: '',
    get value() { return this._value; },
    set value(next) { this._value = String(next); },
    set textContent(_next) { this.options.length = 0; },
    append(option) { this.options.push(option); },
    addEventListener(type, listener) { this.listeners.push({ type, listener }); }
  };
}

/* The selector i18n-dom.js uses to find elements with translatable attributes.
 * The fake DOM answers exactly this one, the way a browser would. */
const ATTRIBUTE_SELECTOR = '[title],[aria-label],[placeholder],[alt]';
const AUTO_ATTRIBUTES = ['title', 'aria-label', 'placeholder', 'alt'];

function descendants(root, found = []) {
  for (const child of root.children || []) {
    if (child.nodeType !== 1) continue;
    found.push(child);
    descendants(child, found);
  }
  return found;
}

/** A minimal but faithful element: textContent owns one text child, children are
 *  an array, attributes a map. Enough to run the real refreshVisualTrackControls()
 *  and checkHealth() through a real i18n pass instead of asserting on source. */
function makeEl(tagName) {
  return {
    nodeType: 1,
    tagName: String(tagName).toUpperCase(),
    dataset: {},
    children: [],
    attributes: {},
    listeners: [],
    parentElement: null,
    classList: { toggle() {}, add() {}, remove() {} },
    get textContent() {
      return this.children.map(child => (child.nodeType === 3 ? child.nodeValue : child.textContent)).join('');
    },
    set textContent(value) {
      this.children.length = 0;
      const text = String(value);
      if (text) this.children.push({ nodeType: 3, nodeValue: text, parentElement: this });
    },
    append(...nodes) {
      for (const node of nodes) { node.parentElement = this; this.children.push(node); }
    },
    replaceChildren(...nodes) { this.children.length = 0; this.append(...nodes); },
    setAttribute(name, value) { this.attributes[name] = String(value); },
    getAttribute(name) { return name in this.attributes ? this.attributes[name] : null; },
    hasAttribute(name) { return name in this.attributes; },
    removeAttribute(name) { delete this.attributes[name]; },
    closest() { return null; },
    querySelectorAll(selector) {
      if (selector !== ATTRIBUTE_SELECTOR) return [];
      return descendants(this).filter(node => AUTO_ATTRIBUTES.some(name => node.hasAttribute(name)));
    },
    addEventListener(type, listener) { this.listeners.push({ type, listener }); }
  };
}

/** Build an isolated page: fresh context, fresh storage, no scripts loaded yet. */
function createHarness({ stored = null } = {}) {
  const select = makeSelect();
  const toggle = { dataset: {}, textContent: '', title: '' };
  const changeEvents = [];
  const store = new Map();
  if (stored !== null) store.set('phrasync.language', stored);

  const body = makeEl('body');
  const byId = new Map();
  const textNodesIn = (node, found = []) => {
    for (const child of node.children || []) {
      if (child.nodeType === 3) found.push(child);
      else textNodesIn(child, found);
    }
    return found;
  };

  const document = {
    nodeType: 9,
    documentElement: { lang: '' },
    body,
    children: [body],
    createElement: tagName => makeEl(tagName),
    createTreeWalker: root => {
      const nodes = textNodesIn(root);
      let index = 0;
      const walker = {
        currentNode: null,
        nextNode() {
          if (index >= nodes.length) return false;
          walker.currentNode = nodes[index];
          index++;
          return true;
        }
      };
      return walker;
    },
    getElementById: id => byId.get(id) || null,
    querySelector: selector => {
      if (selector === '#languageSelect') return select;
      if (selector.startsWith('#')) return byId.get(selector.slice(1)) || null;
      return null;
    },
    querySelectorAll: selector => {
      if (selector === '.language-toggle') return [toggle];
      if (selector === ATTRIBUTE_SELECTOR) {
        return descendants(body).filter(node => AUTO_ATTRIBUTES.some(name => node.hasAttribute(name)));
      }
      return [];
    },
    addEventListener() {},
    dispatchEvent(event) {
      if (event.type === 'phrasync-language-change') changeEvents.push(event.detail);
      return true;
    }
  };

  const localStorage = {
    getItem: key => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: key => store.delete(key),
    raw: store
  };

  const state = { observeCalls: 0, callback: null };
  function MutationObserver(callback) { state.callback = callback; }
  MutationObserver.prototype.observe = function observe() { state.observeCalls++; };

  const sandbox = {
    document,
    localStorage,
    navigator: { languages: ['en'], language: 'en' },
    Node: { ELEMENT_NODE: 1, TEXT_NODE: 3, DOCUMENT_NODE: 9 },
    NodeFilter: { SHOW_TEXT: 4 },
    CustomEvent: FakeCustomEvent,
    MutationObserver,
    console
  };
  const context = vm.createContext(sandbox);
  // In a browser window IS the global object; reproduce that before any script
  // runs so `window.t = …` becomes a global and bare `t()` resolves.
  vm.runInContext('globalThis.window = globalThis;', context);

  const load = name => vm.runInContext(read(name), context, { filename: name });

  const harness = {
    context, sandbox, document, localStorage, select, toggle, changeEvents, state, body,
    loadDictionary: () => load('i18n-zh.js'),
    loadEngine: () => load('i18n.js'),
    loadDom: () => load('i18n-dom.js'),
    /** Evaluate another real module (app-visual-tracks.js, app-workflows.js…). */
    loadScript: name => load(name),
    run: code => vm.runInContext(code, context),
    /** Expose a name to the evaluated scripts, as app-state.js would. */
    setGlobal: (name, value) => { sandbox[name] = value; },
    /** Put an element in the document tree so the real walker and selector reach it. */
    mount: (tagName, id) => {
      const element = makeEl(tagName);
      if (id) byId.set(id, element);
      body.append(element);
      return element;
    },
    mountText: value => {
      const node = { nodeType: 3, nodeValue: String(value), parentElement: body };
      body.children.push(node);
      return node;
    },
    /** Functions and state of the evaluated scripts, read from inside the context. */
    api: () => vm.runInContext(`({
      t: window.t,
      tm: window.tm,
      initI18n: window.initI18n,
      setInterfaceLanguage: window.setInterfaceLanguage,
      toggleInterfaceLanguage: window.toggleInterfaceLanguage,
      formatTranscriptionJob: window.formatTranscriptionJob,
      setCurrentLanguage,
      translateAttributes,
      translateTextNode,
      startObserver,
      translateExact,
      translateMessage,
      translateAttributeText,
      rememberSource,
      language: () => currentLanguage,
      globalCurrentLanguageType: () => typeof window.currentLanguage
    })`, context),
    /** Deliver MutationObserver records through the callback the page registered. */
    deliver: records => state.callback(records)
  };
  return harness;
}

function makeElement(attributes = {}) {
  const values = { ...attributes };
  return {
    nodeType: 1,
    dataset: {},
    closest: () => null,
    getAttribute: name => (name in values ? values[name] : null),
    setAttribute: (name, value) => { values[name] = String(value); },
    read: name => values[name]
  };
}

function makeTextNode(value, source) {
  const node = { nodeType: 3, nodeValue: value, parentElement: { closest: () => null } };
  if (source !== undefined) node.__phrasyncEnglish = source;
  return node;
}

/* ------------------------------------------------------- static source scan */

/** Remove comments and string/template literals so a scan cannot be fooled by
 *  a mention inside prose, and cannot be satisfied by one either. Not a parser:
 *  it cannot see code built by eval() or bracket access, which is why the
 *  behavioural checks below are the primary guard. */
function stripCommentsAndStrings(source) {
  let out = '';
  let i = 0;
  while (i < source.length) {
    const character = source[i];
    const next = source[i + 1];
    if (character === '/' && next === '/') {
      while (i < source.length && source[i] !== '\n') i++;
      continue;
    }
    if (character === '/' && next === '*') {
      i += 2;
      while (i < source.length && !(source[i] === '*' && source[i + 1] === '/')) i++;
      i += 2;
      continue;
    }
    if (character === '"' || character === "'" || character === '`') {
      const quote = character;
      i++;
      while (i < source.length) {
        if (source[i] === '\\') { i += 2; continue; }
        if (source[i] === quote) { i++; break; }
        i++;
      }
      out += '""';
      continue;
    }
    out += character;
    i++;
  }
  return out;
}

const countMatches = (text, pattern) => (text.match(pattern) || []).length;

/* --------------------------------------------------------------------- groups */

const groups = {};

/* The health note the real checkHealth() assembles from three dictionary
 * entries. Kept at module scope: three groups render it, in both directions. */
const NOTE_ZH = '本地 Whisper 已就绪 · CPU 模式. 首次转写会下载模型，并显示进度与预计剩余时间。';
const NOTE_EN = 'Local Whisper ready · CPU mode. The first transcription downloads the model with progress and estimated time remaining.';

groups.exports = () => {
  const page = createHarness({ stored: 'zh-CN' });
  page.loadDictionary();

  // Engine first: the dictionary is read through it, and it must stand alone.
  page.loadEngine();
  assert.equal(typeof page.sandbox.t, 'function', 'window.t must exist once i18n.js has loaded');
  assert.equal(typeof page.sandbox.tm, 'function', 'window.tm must exist once i18n.js has loaded');
  assert.equal(typeof page.sandbox.formatTranscriptionJob, 'function', 'formatTranscriptionJob lives in the engine');
  assert.equal(page.sandbox.initI18n, undefined, 'initI18n must NOT be exposed by the engine');
  assert.equal(page.sandbox.setInterfaceLanguage, undefined, 'setInterfaceLanguage must NOT be exposed by the engine');
  assert.equal(page.sandbox.toggleInterfaceLanguage, undefined, 'toggleInterfaceLanguage must NOT be exposed by the engine');

  const engineT = page.sandbox.t;
  const engineTm = page.sandbox.tm;

  page.loadDom();
  assert.equal(typeof page.sandbox.initI18n, 'function', 'i18n-dom.js must expose initI18n');
  assert.equal(typeof page.sandbox.setInterfaceLanguage, 'function', 'i18n-dom.js must expose setInterfaceLanguage');
  assert.equal(typeof page.sandbox.toggleInterfaceLanguage, 'function', 'i18n-dom.js must expose toggleInterfaceLanguage');
  // Reference identity: the DOM half must not replace the engine's entry points.
  assert.equal(page.sandbox.t, engineT, 'i18n-dom.js must not redefine window.t');
  assert.equal(page.sandbox.tm, engineTm, 'i18n-dom.js must not redefine window.tm');

  // Behaviour that proves which half is in charge, not just which name exists.
  assert.equal(page.api().t('File'), 'File', 't() defaults to English before boot');
  page.api().initI18n();
  assert.equal(page.api().t('File'), '文件', 't() uses the dictionary after boot');
  assert.equal(page.api().t('Zzz not a dictionary key'), 'Zzz not a dictionary key', 'missing entries fall back to the source');
};

groups.language = () => {
  const page = createHarness({ stored: 'zh-CN' });
  page.loadDictionary();
  page.loadEngine();
  page.loadDom();
  const api = page.api();

  api.initI18n();
  const snapshot = () => ({
    state: api.language(),
    htmlLang: page.document.documentElement.lang,
    persisted: page.localStorage.getItem('phrasync.language')
  });
  const expect = (language, label) => {
    const seen = snapshot();
    assert.equal(seen.state, language, `${label}: engine state`);
    assert.equal(seen.htmlLang, language, `${label}: <html lang>`);
    assert.equal(seen.persisted, language, `${label}: localStorage`);
    assert.equal(page.select.value, language, `${label}: #languageSelect value`);
  };

  // Boot honours the stored preference rather than hard-coding English.
  expect('zh-CN', 'boot from stored preference');
  assert.equal(page.localStorage.getItem('phrasync.language.v2'), '2', 'boot records the language version marker');
  assert.deepEqual(page.select.options.map(option => option.value), ['zh-CN', 'en'], 'both languages are offered');
  assert.deepEqual(page.select.options.map(option => option.textContent), ['简体中文', 'English'], 'option labels are the language names');
  assert.ok(page.select.options.every(option => option.dataset.noI18n === ''), 'options opt out of DOM translation');
  assert.equal(page.toggle.title, '切换到英语', 'the toggle advertises the other language, translated');
  assert.equal(page.toggle.dataset.noI18n, '', 'the toggle opts out of DOM translation');
  assert.deepEqual(page.changeEvents, ['zh-CN'], 'boot applies the language and dispatches exactly one change event');

  // Two round trips: state, <html lang> and storage must move together.
  api.toggleInterfaceLanguage();
  expect('en', 'toggle #1');
  assert.equal(page.toggle.title, 'Switch to Chinese', 'the toggle title switches language too');
  api.toggleInterfaceLanguage();
  expect('zh-CN', 'toggle #2');
  api.toggleInterfaceLanguage();
  expect('en', 'toggle #3');
  api.toggleInterfaceLanguage();
  expect('zh-CN', 'toggle #4');
  assert.deepEqual(page.changeEvents, ['zh-CN', 'en', 'zh-CN', 'en', 'zh-CN'], 'one event per switch, in order');

  // Single writer, proved by behaviour: the engine owns the state and the DOM
  // half reads it. If i18n-dom.js kept a private copy, the toggle would flip
  // from its own stale value instead of the one set here.
  api.setCurrentLanguage('en');
  api.toggleInterfaceLanguage();
  assert.equal(api.language(), 'zh-CN', 'toggle reads the engine state, not a private copy');
  api.setCurrentLanguage('zh-CN');
  api.toggleInterfaceLanguage();
  assert.equal(api.language(), 'en', 'toggle reads the engine state in both directions');

  // The only place the state is a bare binding, never a shadow global property.
  assert.equal(api.globalCurrentLanguageType(), 'undefined', 'currentLanguage must not become a window property');

  // persist:false must change the interface without touching the stored choice.
  page.localStorage.setItem('phrasync.language', 'SENTINEL');
  api.setInterfaceLanguage('zh-CN', { persist: false });
  assert.equal(api.language(), 'zh-CN', 'persist:false still switches the interface');
  assert.equal(page.document.documentElement.lang, 'zh-CN', 'persist:false still updates <html lang>');
  assert.equal(page.localStorage.getItem('phrasync.language'), 'SENTINEL', 'persist:false must not write storage');

  // An unsupported code is normalised instead of stored verbatim.
  api.setInterfaceLanguage('it');
  assert.equal(api.language(), 'en', 'unknown languages fall back to English');
};

groups['dom-state'] = () => {
  const page = createHarness({ stored: 'zh-CN' });
  page.loadDictionary();
  page.loadEngine();
  page.loadDom();
  const api = page.api();
  api.initI18n();
  assert.equal(api.language(), 'zh-CN');

  /* Attribute source + rendered state (P1-1), driven through the observer. */
  const field = makeElement({ placeholder: 'One lyric cue per line…' });
  page.deliver([{ type: 'attributes', target: field }]);
  assert.equal(field.read('placeholder'), '每行一句歌词…', 'attribute translated on the first pass');
  assert.equal(field.dataset.phrasyncEnglishPlaceholder, 'One lyric cue per line…', 'the English source is recorded');
  assert.equal(field.dataset.phrasyncRenderedPlaceholder, '每行一句歌词…', 'the value this file wrote is recorded');

  // app-modes.js rewrites the same placeholder when the mode changes.
  field.setAttribute('placeholder', '每行一条字幕…');
  page.deliver([{ type: 'attributes', target: field }]);
  assert.equal(field.read('placeholder'), '每行一条字幕…', 'the rewritten placeholder survives (the old bug overwrote it)');
  assert.equal(field.dataset.phrasyncEnglishPlaceholder, 'One subtitle cue per line…', 'the recorded source follows the rewrite');

  for (let pass = 0; pass < 4; pass++) page.deliver([{ type: 'attributes', target: field }]);
  assert.equal(field.read('placeholder'), '每行一条字幕…', 'repeated callbacks do not churn the value');
  assert.equal(field.dataset.phrasyncEnglishPlaceholder, 'One subtitle cue per line…', 'repeated callbacks do not pollute the source');

  // Back to English restores the current source, not the one seen at boot.
  api.translateAttributes(field, 'en');
  assert.equal(field.read('placeholder'), 'One subtitle cue per line…', 'English restores the current source');
  api.translateAttributes(field, 'zh-CN');
  assert.equal(field.read('placeholder'), '每行一条字幕…', 'and Chinese re-applies it');

  // Project content is never adopted as a translatable source.
  const image = makeElement({ alt: '第一段歌词副歌' });
  page.deliver([{ type: 'attributes', target: image }]);
  assert.equal(image.read('alt'), '第一段歌词副歌', 'Chinese user content is left alone');
  assert.equal(image.dataset.phrasyncEnglishAlt, '', 'user content is never stored as a source');

  /* English-mode text source recording (P1-2), also through the observer. */
  api.setInterfaceLanguage('en');
  const label = makeTextNode('Vertical position ', 'Vertical position ');
  label.nodeValue = 'Ground anchored'; // app-modes.js:97 writes firstChild.nodeValue
  page.deliver([{ type: 'characterData', target: label }]);
  assert.equal(label.__phrasyncEnglish, 'Ground anchored', 'a rewrite in English is recorded as the new source');
  assert.equal(label.nodeValue, 'Ground anchored', 'English mode leaves the DOM untouched');

  api.setInterfaceLanguage('zh-CN');
  page.deliver([{ type: 'characterData', target: label }]);
  assert.equal(label.nodeValue, '锚定地面', 'the next Chinese pass uses the new source, not the boot string');

  // The engine's own translation must never be adopted as an English source.
  for (let pass = 0; pass < 3; pass++) page.deliver([{ type: 'characterData', target: label }]);
  assert.equal(label.__phrasyncEnglish, 'Ground anchored', 'the engine\'s own output is never recorded as the source');
  assert.equal(label.nodeValue, '锚定地面', 'and the value stays stable');

  // Content protection on the text path.
  const lyric = makeTextNode('第一段歌词副歌', '第一段歌词副歌');
  page.deliver([{ type: 'characterData', target: lyric }]);
  assert.equal(lyric.nodeValue, '第一段歌词副歌', 'lyric content is never translated');
};

groups.observer = () => {
  const page = createHarness({ stored: 'zh-CN' });
  page.loadDictionary();
  page.loadEngine();
  page.loadDom();
  const api = page.api();

  api.initI18n();
  assert.equal(page.state.observeCalls, 1, 'boot registers exactly one observer');
  api.startObserver();
  api.startObserver();
  assert.equal(page.state.observeCalls, 1, 'startObserver() is idempotent');
};

groups.structure = () => {
  const engine = stripCommentsAndStrings(read('i18n.js'));
  const dom = stripCommentsAndStrings(read('i18n-dom.js'));

  // Exactly one declaration, in the engine only.
  assert.equal(countMatches(engine, /\b(?:let|const|var)\s+currentLanguage\b/g), 1, 'i18n.js declares currentLanguage once');
  assert.equal(countMatches(dom, /\b(?:let|const|var)\s+currentLanguage\b/g), 0, 'i18n-dom.js must not declare currentLanguage');
  // No assignment either — `currentLanguage = x`, `currentLanguage=x`, but not
  // `===`, `==` or `=>`. Comments and strings are already stripped above.
  assert.equal(countMatches(dom, /\bcurrentLanguage\s*=(?![=>])/g), 0, 'i18n-dom.js must not assign currentLanguage directly');
  assert.equal(countMatches(engine, /\bcurrentLanguage\s*=(?![=>])/g), 2, 'only the engine assigns it (declaration + setCurrentLanguage)');

  // The single writer really is the only channel the DOM half uses.
  assert.ok(/\bsetCurrentLanguage\s*\(/.test(dom), 'i18n-dom.js goes through setCurrentLanguage');

  // Ownership must stay where the tests above expect it: no `window.t =` in the
  // DOM half and no `window.initI18n =` in the engine.
  assert.equal(countMatches(dom, /window\.t\s*=(?![=>])/g), 0, 'i18n-dom.js must not export window.t');
  assert.equal(countMatches(dom, /window\.tm\s*=(?![=>])/g), 0, 'i18n-dom.js must not export window.tm');
  assert.equal(countMatches(engine, /window\.initI18n\s*=(?![=>])/g), 0, 'i18n.js must not export initI18n');
  assert.equal(countMatches(engine, /window\.t\s*=/g), 1, 'i18n.js exports window.t exactly once');
};

/* Assembled sentences: window code joins several t() fragments into one string.
 * Neither the finished Chinese nor the finished English is a dictionary entry,
 * so the module that builds it registers the pair. This group runs the real
 * modules and asserts what is on screen after each switch, both directions. */
groups.assembled = async () => {
  const page = createHarness({ stored: 'zh-CN' });
  page.loadDictionary();
  page.loadEngine();
  page.loadDom();
  const api = page.api();
  api.initI18n();
  assert.equal(api.language(), 'zh-CN', 'the page boots in Chinese');

  /* ---- real app code: the background track selector ---- */
  page.setGlobal('project', { background: { tracks: ['V1', 'V2'], clips: [], effects: { trigger: 'beat' } } });
  const clipTrack = page.mount('select', 'clipTrack');
  const manager = page.mount('div', 'backgroundTrackManager');
  page.mount('input', 'fxTrigger');
  page.loadScript('app-visual-tracks.js');
  page.run('refreshVisualTrackControls(null)');

  const option = index => clipTrack.children[index];
  const removeButton = manager.children[0].children[1];
  assert.equal(clipTrack.children.length, 2, 'one option per background track');
  assert.equal(option(0).textContent, 'V1 · 轨道 1', 'the option label is assembled from t("Track")');
  assert.equal(option(1).textContent, 'V2 · 轨道 2', 'each option carries its own number');
  assert.equal(removeButton.getAttribute('aria-label'), '移除轨道 V1', 'the aria-label is assembled from t("Remove track")');

  // The browser fires childList for each append; replay it through the observer.
  page.deliver([{ type: 'childList', addedNodes: [...clipTrack.children] }]);
  page.deliver([{ type: 'childList', addedNodes: [...manager.children] }]);
  assert.equal(option(0).textContent, 'V1 · 轨道 1', 'the observer must not replace the Chinese option with English');
  assert.equal(removeButton.getAttribute('aria-label'), '移除轨道 V1', 'the observer must not replace the Chinese aria-label');

  /* ---- project content that happens to be Chinese ---- */
  const lyric = page.mountText('第一段歌词副歌');
  page.deliver([{ type: 'characterData', target: lyric }]);
  assert.equal(lyric.nodeValue, '第一段歌词副歌', 'lyric text is never rewritten');

  /* ---- real app code: checkHealth, ready branch ---- */
  const note = page.mount('p', 'transcriptionNote');
  const engineStatus = page.mount('span', 'engineStatus');
  const statusSpan = makeEl('span');
  let healthFails = false;
  page.setGlobal('els', { transcriptionNote: note, engineStatus });
  page.setGlobal('$', () => statusSpan);
  page.setGlobal('toast', () => {});
  page.setGlobal('setAssetStatus', () => {});
  page.setGlobal('health', null);
  page.setGlobal('api', async () => {
    if (healthFails) throw new Error('connect ECONNREFUSED');
    return {
      ffmpeg: { available: true },
      transcription: { available: true, cuda: false, gpu: { reason: null } },
      ocr: { available: true }
    };
  });
  page.loadScript('app-workflows.js');

  await page.run('checkHealth()');
  assert.equal(note.textContent, NOTE_ZH, 'the ready note is assembled from three t() fragments');
  page.deliver([{ type: 'childList', addedNodes: [...note.children] }]);
  assert.equal(note.textContent, NOTE_ZH, 'the observer must not replace the Chinese note with English');

  /* ---- zh-CN -> en ---- */
  api.setInterfaceLanguage('en');
  assert.equal(note.textContent, NOTE_EN, 'the assembled note comes back in English');
  assert.equal(option(0).textContent, 'V1 · Track 1', 'the option comes back in English');
  assert.equal(option(1).textContent, 'V2 · Track 2', 'every option comes back in English');
  assert.equal(removeButton.getAttribute('aria-label'), 'Remove track V1', 'the aria-label comes back in English');
  assert.equal(lyric.nodeValue, '第一段歌词副歌', 'user content is untouched when switching to English');

  /* ---- en -> zh-CN ---- */
  api.setInterfaceLanguage('zh-CN');
  assert.equal(note.textContent, NOTE_ZH, 'Chinese rebuilds the assembled note');
  assert.equal(option(0).textContent, 'V1 · 轨道 1', 'Chinese rebuilds the option');
  assert.equal(removeButton.getAttribute('aria-label'), '移除轨道 V1', 'Chinese rebuilds the aria-label');

  /* ---- /api/health failure: nothing rewrites the note ---- */
  healthFails = true;
  await page.run('checkHealth()');
  assert.equal(note.textContent, NOTE_ZH, 'a failed health check leaves the last text on screen');

  /* ---- en -> zh-CN -> en with the failure branch in play ---- */
  api.setInterfaceLanguage('en');
  assert.equal(note.textContent, NOTE_EN, 'the note still restores after a failed health check');
  api.setInterfaceLanguage('zh-CN');
  assert.equal(note.textContent, NOTE_ZH, 'and is rebuilt in Chinese');
  api.setInterfaceLanguage('en');
  assert.equal(note.textContent, NOTE_EN, 'and restores once more');
  assert.equal(lyric.nodeValue, '第一段歌词副歌', 'user content survives every switch');

  /* ---- a project whose track name is Chinese ---- */
  api.setInterfaceLanguage('zh-CN');
  page.setGlobal('project', { background: { tracks: ['主歌'], clips: [], effects: { trigger: 'beat' } } });
  page.run('refreshVisualTrackControls(null)');
  const cjkOption = clipTrack.children[0];
  page.deliver([{ type: 'childList', addedNodes: [cjkOption] }]);
  assert.equal(cjkOption.textContent, '主歌 · 轨道 1', 'a Chinese track name is rendered once');
  api.setInterfaceLanguage('en');
  assert.equal(cjkOption.textContent, '主歌 · 轨道 1', 'content protection wins over half-translating the label');
};

/* The other direction: a page that boots in English (the default for an English
 * system) renders the assembled sentence first, then switches to Chinese. The
 * pair has to exist from that first render, because the failing branch of
 * checkHealth() never rewrites the note again. */
groups.bidirectional = async () => {
  const readyHealth = {
    ffmpeg: { available: true },
    transcription: { available: true, cuda: false, gpu: { reason: null } },
    ocr: { available: true }
  };

  const build = () => {
    const page = createHarness({ stored: 'en' });
    page.loadDictionary();
    page.loadEngine();
    page.loadDom();
    const api = page.api();
    api.initI18n();
    const note = page.mount('p', 'transcriptionNote');
    const engineStatus = page.mount('span', 'engineStatus');
    const statusSpan = makeEl('span');
    const state = { healthFails: false, healthCalls: 0 };
    page.setGlobal('els', { transcriptionNote: note, engineStatus });
    page.setGlobal('$', () => statusSpan);
    page.setGlobal('toast', () => {});
    page.setGlobal('setAssetStatus', () => {});
    page.setGlobal('health', null);
    page.setGlobal('api', async () => {
      state.healthCalls++;
      if (state.healthFails) throw new Error('connect ECONNREFUSED');
      return readyHealth;
    });
    page.loadScript('app-workflows.js');
    return { page, api, note, state };
  };

  /* ---- render in English, then switch with no further health request ---- */
  {
    const { page, api, note, state } = build();
    assert.equal(api.language(), 'en', 'the page boots in English');
    await page.run('checkHealth()');
    assert.equal(note.textContent, NOTE_EN, 'the note is rendered in English');
    page.deliver([{ type: 'childList', addedNodes: [...note.children] }]);

    const callsBefore = state.healthCalls;
    api.setInterfaceLanguage('zh-CN');
    assert.equal(state.healthCalls, callsBefore, 'switching language does not ask the backend again');
    assert.equal(note.textContent, NOTE_ZH, 'the pair registered while English was active renders Chinese');
    api.setInterfaceLanguage('en');
    assert.equal(note.textContent, NOTE_EN, 'and switches back to English');
    api.setInterfaceLanguage('zh-CN');
    assert.equal(note.textContent, NOTE_ZH, 'and to Chinese again');
  }

  /* ---- the same, but the health check fails and never rewrites the note ---- */
  {
    const { page, api, note, state } = build();
    await page.run('checkHealth()');
    page.deliver([{ type: 'childList', addedNodes: [...note.children] }]);
    assert.equal(note.textContent, NOTE_EN, 'English note on screen');

    state.healthFails = true;
    const callsBefore = state.healthCalls;
    await page.run('checkHealth()');
    assert.equal(state.healthCalls, callsBefore + 1, 'the failing check really ran');
    assert.equal(note.textContent, NOTE_EN, 'the failing branch leaves the note untouched');

    api.setInterfaceLanguage('zh-CN');
    assert.equal(note.textContent, NOTE_ZH, 'the switch still works while /api/health is down');
    api.setInterfaceLanguage('en');
    assert.equal(note.textContent, NOTE_EN, 'and back, without any successful health check');
  }

  /* ---- the same pair, reached from the other side (Chinese first) ---- */
  {
    const page = createHarness({ stored: 'zh-CN' });
    page.loadDictionary();
    page.loadEngine();
    page.loadDom();
    const api = page.api();
    api.initI18n();
    const note = page.mount('p', 'transcriptionNote');
    page.setGlobal('els', { transcriptionNote: note, engineStatus: page.mount('span', 'engineStatus') });
    page.setGlobal('$', () => makeEl('span'));
    page.setGlobal('toast', () => {});
    page.setGlobal('setAssetStatus', () => {});
    page.setGlobal('health', null);
    page.setGlobal('api', async () => readyHealth);
    page.loadScript('app-workflows.js');
    await page.run('checkHealth()');
    page.deliver([{ type: 'childList', addedNodes: [...note.children] }]);
    assert.equal(note.textContent, NOTE_ZH, 'Chinese note on screen');
    api.setInterfaceLanguage('en');
    assert.equal(note.textContent, NOTE_EN, 'switches to English');
    api.setInterfaceLanguage('zh-CN');
    assert.equal(note.textContent, NOTE_ZH, 'and back to Chinese (no regression)');
  }

  /* ---- the same mechanism on the track labels, rendered while English ---- */
  {
    const page = createHarness({ stored: 'en' });
    page.loadDictionary();
    page.loadEngine();
    page.loadDom();
    const api = page.api();
    api.initI18n();
    page.setGlobal('project', { background: { tracks: ['V1', 'V2'], clips: [], effects: { trigger: 'beat' } } });
    const clipTrack = page.mount('select', 'clipTrack');
    const manager = page.mount('div', 'backgroundTrackManager');
    page.mount('input', 'fxTrigger');
    page.loadScript('app-visual-tracks.js');
    page.run('refreshVisualTrackControls(null)');

    const removeButton = manager.children[0].children[1];
    assert.equal(clipTrack.children[0].textContent, 'V1 · Track 1', 'English label while English is active');
    assert.equal(removeButton.getAttribute('aria-label'), 'Remove track V1', 'English aria-label as well');
    page.deliver([{ type: 'childList', addedNodes: [...clipTrack.children] }]);
    page.deliver([{ type: 'childList', addedNodes: [...manager.children] }]);

    api.setInterfaceLanguage('zh-CN');
    assert.equal(clipTrack.children[0].textContent, 'V1 · 轨道 1', 'the English-rendered option becomes Chinese');
    assert.equal(removeButton.getAttribute('aria-label'), '移除轨道 V1', 'and so does the attribute');
    api.setInterfaceLanguage('en');
    assert.equal(clipTrack.children[0].textContent, 'V1 · Track 1', 'and comes back to English');
    assert.equal(removeButton.getAttribute('aria-label'), 'Remove track V1', 'attribute included');
  }
};

/* Order of the four strategies in translateMessage(): exact dictionary entry,
 * then a pattern rule, then a registered assembled rendering, then the raw
 * string. Assertions are on returned text, not on the shape of the tables. */
groups.priority = () => {
  const boot = stored => {
    const page = createHarness({ stored });
    page.loadDictionary();
    page.loadEngine();
    page.loadDom();
    const api = page.api();
    api.initI18n();
    return { page, api };
  };

  /* ---- 1. the dictionary still wins over anything registered ---- */
  {
    const { api } = boot('zh-CN');
    api.rememberSource('!!! wrong rendering !!!', 'File', 'zh-CN');
    assert.equal(api.translateMessage('File'), '文件', 'a registered pair never overrides the dictionary');
    assert.equal(api.translateExact('File'), '文件', 'translateExact stays dictionary-only');
    assert.equal(api.translateAttributeText('File'), '文件', 'and attributes use the same dictionary first');
  }

  /* ---- 2. a pattern wins over a registered pair, in both orders ---- */
  {
    const frame = 'Rendering frame 3/10';
    const expected = '正在渲染第 3/10 帧';

    const early = boot('zh-CN');
    assert.equal(early.api.translateMessage(frame), expected, 'the pattern applies to an unregistered message');
    early.api.rememberSource('错误渲染 3/10', frame, 'zh-CN');
    assert.equal(early.api.translateMessage(frame), expected, 'registering after the pattern changes nothing');

    const late = boot('zh-CN');
    late.api.rememberSource('错误渲染 3/10', frame, 'zh-CN');
    assert.equal(late.api.translateMessage(frame), expected, 'registering before the pattern changes nothing either');
  }

  /* ---- 3. the download note: same text, same punctuation, any order ---- */
  {
    const jobs = [
      ['min + percent', { phase: 'model-download', downloaded_bytes: 1e8, total_bytes: 2e8, eta_seconds: 120 }],
      ['sec + percent', { phase: 'model-download', downloaded_bytes: 1e8, total_bytes: 2e8, eta_seconds: 30 }],
      ['estimating', { phase: 'model-download', downloaded_bytes: 1e8, total_bytes: 2e8, eta_seconds: 0 }],
      ['no total', { phase: 'model-download', downloaded_bytes: 1e8, eta_seconds: 120 }]
    ];

    // The English strings come from a page that renders them, so the test never
    // re-implements formatTranscriptionJob's template.
    const englishPage = boot('en');
    const english = jobs.map(([, job]) => englishPage.api.formatTranscriptionJob(job));
    assert.ok(english.every(text => text.startsWith('Downloading Whisper model: ')), 'English source built');

    jobs.forEach(([label, job], index) => {
      const note = english[index];
      // 登记前：全新上下文，只走了模式规则
      const fresh = boot('zh-CN');
      const before = fresh.api.translateMessage(note);
      assert.equal(before, fresh.api.formatTranscriptionJob(job), `${label}: pattern output equals the rendered note`);
      // 登记后：同一条消息再来一次，结果不变
      assert.equal(fresh.api.translateMessage(note), before, `${label}: registration does not change the result`);
      // 反方向：先渲染（=登记）再 translate，结果仍一致
      const registered = boot('zh-CN');
      const rendered = registered.api.formatTranscriptionJob(job);
      assert.equal(registered.api.translateMessage(note), rendered, `${label}: same text whichever ran first`);
      assert.ok(!/(Downloading|remaining|estimating)/.test(rendered), `${label}: no English words left in ${rendered}`);
      assert.ok(!/模型:/.test(rendered), `${label}: half-width colon is gone (${rendered})`);
    });
  }

  /* ---- 4. unregistered English is never invented into Chinese ---- */
  {
    const { api } = boot('zh-CN');
    const plain = 'A sentence nobody registered anywhere';
    assert.equal(api.translateMessage(plain), plain, 'translateMessage leaves unknown text alone');
    assert.equal(api.tm(plain), plain, 'tm leaves unknown text alone');
    assert.equal(api.t(plain), plain, 't leaves unknown text alone');
    assert.equal(api.translateAttributeText(plain), plain, 'attributes leave unknown text alone');
  }

  /* ---- 5. registered assembled text: round trip, repeats, no late overwrite ---- */
  {
    const { api } = boot('zh-CN');
    const source = 'V1 · Track 1';
    api.rememberSource('V1 · 轨道 1', source, 'zh-CN');
    assert.equal(api.translateMessage(source), 'V1 · 轨道 1', 'a registered assembled label is translated');
    api.rememberSource('V1 · 轨道 1', source, 'zh-CN');
    assert.equal(api.translateMessage(source), 'V1 · 轨道 1', 'registering the same pair twice is stable');
    api.rememberSource('V1 · 轨道 甲', source, 'zh-CN');
    assert.equal(api.translateMessage(source), 'V1 · 轨道 1', 'a later different rendering does not overwrite the first');
    assert.equal(api.t(source), source, 't() does not gain the assembled mapping');

    // 语言切换不清空、也不串味
    api.setCurrentLanguage('en');
    assert.equal(api.translateMessage(source), source, 'English mode returns the source untouched');
    api.setCurrentLanguage('zh-CN');
    assert.equal(api.translateMessage(source), 'V1 · 轨道 1', 'and Chinese is still there afterwards');
  }

  /* ---- 6. real Chinese content is not touched by any of this ---- */
  {
    const { api } = boot('zh-CN');
    const lyric = '第一段歌词副歌';
    assert.equal(api.translateMessage(lyric), lyric, 'lyric text is returned unchanged');
    assert.equal(api.translateAttributeText(lyric), lyric, 'and so is an attribute carrying it');
    api.rememberSource(lyric, 'First chorus', 'zh-CN');
    assert.equal(api.t('First chorus'), 'First chorus', 'a registered pair does not make t() translate content');
  }
};

/* ----------------------------------------------------------------------- main */

const requested = process.argv[2];
const selected = requested ? [requested] : Object.keys(groups);
for (const name of selected) {
  if (!groups[name]) {
    console.error(`unknown group: ${name}`);
    process.exit(2);
  }
}
(async () => {
  try {
    for (const name of selected) {
      await groups[name]();
      console.log(`PASS ${name}`);
    }
  } catch (error) {
    console.error(error);
    process.exitCode = 1;
  }
})();
