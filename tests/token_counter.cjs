// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
// Führt die echte Zählerlogik mit zwei unabhängigen DOM-Zielen aus.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(`${__dirname}/../static/app.js`, 'utf8');
const block = source.slice(source.indexOf('const taskTokens ='), source.indexOf('function updateControlCenter()'));
function panel() {
  const fields = {};
  const classes = new Set();
  return { fields, classes, classList: { toggle(k, on) { on ? classes.add(k) : classes.delete(k); } },
    querySelector(selector) {
      const name = selector.match(/"([^"]+)"/)[1];
      return fields[name] ||= { textContent: '' };
    } };
}
const chat = panel(), joshi = panel();
const context = vm.createContext({
  window: { setInterval() { return 1; }, clearInterval() {} },
  document: { querySelector() { return joshi; } },
  $(s) { return s === '#task-tokens' ? chat : chat.fields[s.slice(1)] ||= { textContent: '' }; },
  formatTokenCount(n) { return String(n); }, Date, assert, chat, joshi,
});
vm.runInContext(block + `
  resetTaskTokens();
  addTaskTokens('abcdefghijkl');
  joshiTokenstand({
    tokens: 100, sekunden: 2, laufend: true,
    output_tokens_actual: 0, output_tokens_estimated: 100,
    usage_status: 'estimated', rate_geschaetzt: true,
  });
  assert.equal(chat.fields['task-tokens-value'].textContent, '3');
  assert.equal(joshi.fields['task-tokens-value'].textContent, '≈ 100');
  assert.equal(taskTokenRate(joshiTokens), 50);
  assert.match(joshi.fields['task-tokens-speed'].textContent, /≈/);
  assert.match(joshi.fields['task-tokens-note'].textContent, /≈ 100 geschätzt/);
  addTaskTokens('abcd');
  assert.equal(joshi.fields['task-tokens-value'].textContent, '≈ 100');
  finishTaskTokens(9999, 7);
  joshiTokenstand({
    tokens: 120, sekunden: 3, aufrufe: 2,
    tokens_actual: 120, output_tokens_actual: 120, input_tokens_actual: 900,
    output_tokens_estimated: 0, output_tokens_incomplete: 0, usage_status: 'actual',
  });
  assert.equal(chat.fields['task-tokens-value'].textContent, '7');
  assert.equal(joshi.fields['task-tokens-value'].textContent, '120');
  assert.equal(joshi.fields['task-tokens-speed'].textContent, 'Ø 40 Tok/s');
  assert.match(joshi.fields['task-tokens-note'].textContent, /120 bestätigt/);
  assert.match(joshi.fields['task-tokens-note'].textContent, /900 Eingabe bestätigt/);
  joshiTokenstand({
    tokens: 203000, sekunden: 47.2, aufrufe: 3,
    tokens_actual: 15573, output_tokens_actual: 15573, input_tokens_actual: 23929,
    output_tokens_estimated: 188, output_tokens_incomplete: 187239, usage_status: 'incomplete',
  });
  assert.equal(joshi.fields['task-tokens-value'].textContent, '≈ 203000');
  assert.match(joshi.fields['task-tokens-note'].textContent, /15573 Ausgabe/);
  assert.match(joshi.fields['task-tokens-note'].textContent, /187239 unvollständig/);
  assert.match(joshi.fields['task-tokens-speed'].textContent, /≈/);
  resetTaskTokens();
  renderJoshiTokens();
  assert.equal(joshi.fields['task-tokens-value'].textContent, '≈ 203000');
  joshiTokenstand({});
  assert.equal(joshi.fields['task-tokens-value'].textContent, '0');
`, context);
console.log('Paralleler Chat, JOSHI, bestätigte und geschätzte Tokens, Abschluss und Produktwechsel: OK');
