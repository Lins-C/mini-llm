// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
// Führt die echten, zustandsfreien Stufen-Helfer aus static/joshi.js aus.
// Der Test bildet den Fehlerfall ab: Schritt 1 ist fertig, während Schritt 2
// erzeugt oder geprüft wird. Beide Zustände müssen gleichzeitig sichtbar sein.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync(`${__dirname}/../static/joshi.js`, 'utf8');
const statusStart = source.indexOf('  const STUFEN_ZUSTAENDE');
const statusEnd = source.indexOf('  const STATUSTEXT');
const helperStart = source.indexOf('  // ------------------------------------------------ Gestufter Fortschritt');
const helperEnd = source.indexOf('  function zeichneLivekarte()');
assert.ok(statusStart >= 0 && statusEnd > statusStart, 'Stufen-Zustandsmapping fehlt');
assert.ok(helperStart >= 0 && helperEnd > helperStart, 'Stufen-Helfer fehlen');

function element(tag, className = '', textContent = '') {
  return {
    tag, className, textContent, children: [], dataset: {},
    append(...children) { this.children.push(...children); },
  };
}

const context = vm.createContext({
  assert, element,
  SCHRITT_ZEICHEN: { offen: '○', aktiv: '●', fertig: '✓', fehler: '✕', reparatur: '↻', unbewiesen: '?' },
});

vm.runInContext(source.slice(statusStart, statusEnd) + source.slice(helperStart, helperEnd) + `
  const live = { stufen: [], stufenVon: 0, fortschritt: 'Alter Fortschritt' };
  uebernehmeStufenplan(live, {
    von: 3,
    stufen: [
      { nummer: 1, titel: 'Zellmodell', zustand: 'planned' },
      { nummer: 2, titel: 'Neuberechnung', zustand: 'planned' },
      { nummer: 3, titel: 'Fehlerwerte', zustand: 'planned' },
    ],
  });
  assert.equal(live.stufenVon, 3);
  assert.deepEqual(live.stufen.map((s) => s.zustand), ['planned', 'planned', 'planned']);

  uebernehmeStufe(live, { nummer: 1, von: 3, titel: 'Zellmodell', zustand: 'passed' });
  uebernehmeStufe(live, { nummer: 2, von: 3, titel: 'Neuberechnung', zustand: 'generating' });
  assert.deepEqual(live.stufen.map((s) => s.zustand), ['passed', 'generating', 'planned']);
  assert.equal(aktuelleStufe(live).nummer, 2);
  assert.match(stufenZusammenfassung(live), /Schritt 2 von 3.*Neuberechnung.*Änderung wird erstellt/);
  let liste = stufenListe(live);
  assert.equal(liste.children[0].className, 'is-fertig');
  assert.equal(liste.children[0].children[0].textContent, '✓');
  assert.equal(liste.children[1].className, 'is-aktiv');
  assert.equal(liste.children[1].children[0].textContent, '●');

  live.fortschritt = 'Schritt 2 von 3 · 14.000 Zeichen';
  uebernehmeStufe(live, { nummer: 2, von: 3, titel: 'Neuberechnung', zustand: 'validating' });
  assert.equal(live.fortschritt, '');
  assert.match(stufenZusammenfassung(live), /Schritt 2 von 3.*Änderung wird geprüft/);

  uebernehmeStufe(live, { nummer: 2, von: 3, titel: 'Neuberechnung', zustand: 'passed' });
  uebernehmeStufe(live, { nummer: 3, von: 3, titel: 'Fehlerwerte', zustand: 'generating' });
  assert.deepEqual(live.stufen.map((s) => s.zustand), ['passed', 'passed', 'generating']);
  liste = stufenListe(live);
  assert.equal(liste.children.map((e) => e.className).join(','), 'is-fertig,is-fertig,is-aktiv');
  assert.match(stufenZusammenfassung(live), /Schritt 3 von 3.*Fehlerwerte/);

  uebernehmeStufe(live, { nummer: 3, von: 3, titel: 'Fehlerwerte', zustand: 'not_proven' });
  liste = stufenListe(live);
  assert.equal(liste.children[2].className, 'is-unbewiesen');
  assert.match(stufenZusammenfassung(live), /Nicht nachweisbar/);

  const vorFehler = live.stufen.length;
  uebernehmeStufe(live, { zustand: 'generating' });
  assert.equal(live.stufen.length, vorFehler);
`, context);

console.log('Stufenplan, Generierung, Prüfung, Checkpoint und NOT_PROVEN: OK');
