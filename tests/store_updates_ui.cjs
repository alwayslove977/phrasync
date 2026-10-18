// Exercise the real update controller with a fake DOM/network, never the Store.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element extends EventTarget {
  hidden = false; disabled = false; textContent = ''; open = false; returnValue = '';
  click() { this.dispatchEvent(new Event('click')); }
  showModal() { assert.equal(this.open, false); this.open = true; }
  close(value = '') { this.returnValue = value; this.open = false; this.dispatchEvent(new Event('close')); }
}
const elements = new Map();
const $ = id => { if (!elements.has(id)) elements.set(id, new Element()); return elements.get(id); };
const document = new EventTarget(); document.getElementById = $;
let installCalls = 0, storeCalls = 0, nextState = 'completed', completeInstall;
const fetch = async path => {
  let data;
  if (path.endsWith('/status')) data = {packaged: true, version: '0.4.7'};
  else if (path.endsWith('/check')) data = {available: true};
  else {
    installCalls++;
    await new Promise(resolve => { completeInstall = resolve; });
    data = {state: nextState};
  }
  return {ok: true, json: async () => data};
};
const window = {t: value => value, pywebview: {api: {open_store_updates: async () => { storeCalls++; }}}};
vm.runInNewContext(fs.readFileSync('static/store-updates.js', 'utf8'), {document, window, fetch});
const tick = () => new Promise(resolve => setImmediate(resolve));
async function run() {
  document.dispatchEvent(new Event('DOMContentLoaded'));
  $('settingsButton').click(); await tick();
  assert.equal($('storeUpdateVersion').textContent, 'Phrasync 0.4.7');
  $('storeUpdateCheck').click(); await tick();
  assert.equal($('storeUpdateInstall').hidden, false);
  for (const choice of ['cancel', '']) {
    $('storeUpdateInstall').click(); await tick();
    assert.equal($('storeUpdateConfirm').open, true);
    assert.equal(installCalls, 0);
    $('storeUpdateConfirm').close(choice); await tick();
    assert.equal(installCalls, 0); // Not now / Escape never install.
    assert.equal($('storeUpdateCheck').disabled, false);
  }
  $('storeUpdateInstall').click(); $('storeUpdateInstall').click(); await tick();
  $('storeUpdateConfirm').close('install'); await tick();
  assert.equal(installCalls, 1);
  assert.equal($('storeUpdateCheck').disabled, true);
  $('settingsButton').click(); $('storeUpdateInstall').click(); await tick();
  assert.equal(installCalls, 1); // Reopening Settings or double click cannot duplicate.
  completeInstall(); await tick();
  assert.match($('storeUpdateMessage').textContent, /Update installed/);
  assert.equal($('storeUpdateInstall').hidden, true);
  for (const state of ['canceled', 'low-battery', 'wifi-required', 'other-error']) {
    $('storeUpdateCheck').click(); await tick();
    $('storeUpdateInstall').click(); await tick();
    $('storeUpdateConfirm').close('install'); await tick();
    nextState = state; completeInstall(); await tick();
    assert.doesNotMatch($('storeUpdateMessage').textContent, /Update installed/);
    assert.equal($('storeUpdateOpen').hidden, false);
  }
  $('storeUpdateOpen').click(); await tick();
  assert.equal(storeCalls, 1);
  console.log('PASS branded consent, cancel/Escape, duplicate prevention, outcomes and explicit Store fallback');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
