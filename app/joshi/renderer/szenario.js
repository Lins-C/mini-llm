// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
// Aktionsproben und Szenarien: Arrange → Act → Assert in der isolierten
// Prüfseite. Der Python-Teil setzt davor `const __auftrag = {…}`:
//   { aktionen: ["speichern", "laden", …] }            – feste Aktionsproben
//   { schritte: [{art, ziel, wert, ms}, …], id: "…" } – ein Szenario (eine Phase)
// Die Schritte sind Daten, kein Code: Hier gibt es kein eval, keine neuen
// Rechte. Was diese Umgebung nicht nachstellen kann (zweite Sitzung,
// Offline), meldet sie als „nicht_beweisbar“ — nie als bestanden.
const J = window.__joshi || { fehler: [], dialoge: [], exporte: [] };
const A = typeof __auftrag === "object" && __auftrag ? __auftrag : {};
const warte = (ms) => new Promise((r) => setTimeout(r, ms));
const sichtbar = (el) => {
  if (!el || !el.getBoundingClientRect || !el.isConnected) return false;
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
};
const kurz = (t, n = 80) => String(t || "").replace(/\s+/g, " ").trim().slice(0, n);
// „1.500,00 €“, „1500 €“ und „1.500 EUR“ sind derselbe Betrag (29.09.2026: das
// Budget-Szenario scheiterte an „1.500,00 €“ gegen „1.500 €“).
const geld = (t) => t.replace(/(\d)[.\u00a0\u202f' ](?=\d{3}(?!\d))/g, "$1").replace(/[.,]00(?!\d)/g, "")
  .replace(/\s*(?:€|eur\b|euro\b)/g, " €");
// Erwartete Werte mit „jetzt“ (heutiges Datum, Uhrzeit um die aktuelle Zeit)
// veralten, während das Szenario läuft (Fall 06.10.2026: erwartet „22:17“,
// gemessen 22:18:31). Nur solche Stellen werden zur Form „irgendein Datum /
// irgendeine Uhrzeit“; feste Werte wie ein eingegebener Termin bleiben exakt.
function jetztMuster(erwartet) {
  const jetzt = new Date();
  const minuten = jetzt.getHours() * 60 + jetzt.getMinutes();
  let gelockert = false;
  const teile = String(erwartet).split(/(\d{1,2}:\d{2}(?::\d{2})?|\d{1,2}\.\d{1,2}\.\d{2,4})/);
  const muster = teile.map((teil, i) => {
    if (i % 2 === 0) return teil.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (teil.includes(":")) {
      const [h, m] = teil.split(":").map(Number);
      const abstand = Math.abs(h * 60 + m - minuten);
      if (Math.min(abstand, 1440 - abstand) <= 180) { gelockert = true; return "\\d{1,2}:\\d{2}(?::\\d{2})?"; }
    } else {
      const [t, mo, j] = teil.split(".").map(Number);
      const datum = new Date(j < 100 ? 2000 + j : j, mo - 1, t);
      if (Math.abs(datum - jetzt) <= 2 * 86400000) { gelockert = true; return "\\d{1,2}\\.\\d{1,2}\\.\\d{2,4}"; }
    }
    return teil.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }).join("");
  return gelockert ? new RegExp(muster) : null;
}

const norm = (t) => geld(String(t == null ? "" : t).toLowerCase().replace(/\s+/g, " ")).replace(/(\d),(\d)/g, "$1.$2").trim();
const fehlerStart = (J.fehler || []).length;

let downloads = 0;
let dateiDialog = false;
try {
  const ankerKlick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.hasAttribute("download") || /^(blob|data):/i.test(this.getAttribute("href") || "")) downloads++;
    return ankerKlick.apply(this, arguments);
  };
  const feldKlick = HTMLInputElement.prototype.click;
  HTMLInputElement.prototype.click = function () {
    if ((this.type || "").toLowerCase() === "file") { dateiDialog = true; return undefined; }
    return feldKlick.apply(this, arguments);
  };
} catch (e) { /* ohne Zählung */ }

// ------------------------------------------------------------ Elemente finden
const KNOEPFE = "button,input[type=button],input[type=submit],[role=button],a[href]";
const FELDER = "input:not([type=hidden]):not([type=button]):not([type=submit]):not([type=file]),select,textarea,[contenteditable=true],[contenteditable='']";
const beschriftung = (el) => {
  const text = kurz(el.innerText || el.value, 60);
  const zusatz = kurz(el.getAttribute("aria-label") || el.title, 60);
  return zusatz && text.length <= 2 ? kurz(zusatz + (text ? ` (${text})` : ""), 60) : (text || zusatz);
};
const feldBeschriftung = (el) => {
  if (el.id) {
    const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (l) return kurz(l.innerText);
  }
  const huelle = el.closest && el.closest("label");
  if (huelle) return kurz(huelle.innerText);
  return kurz(el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || el.title || "");
};
function finde(ziel, art) {
  const z = norm(ziel);
  if (!z) return null;
  const liste = [...document.querySelectorAll(art === "knopf" ? KNOEPFE : `${FELDER},${KNOEPFE},[id],[data-cell],[data-id]`)]
    .filter((el) => sichtbar(el) || art === "feld");
  const merkmale = (el) => [el.id, el.getAttribute("name"), el.getAttribute("data-cell"), el.getAttribute("data-id"),
    el.getAttribute("aria-label"), el.getAttribute("placeholder"), el.title,
    // Knöpfe heißen nach ihrer Beschriftung — auch bei sichtbar/unsichtbar-Prüfungen
    // (art ""), sonst war „Knopf Neustart ist sichtbar“ nie nachweisbar (08.10.2026).
    art === "knopf" || (art !== "feld" && el.matches(KNOEPFE)) ? beschriftung(el) : feldBeschriftung(el)]
    .map(norm).filter(Boolean);
  const passend = liste.filter((el) => (art !== "feld" || el.matches(FELDER)) && merkmale(el).includes(z));
  if (passend.length) return passend.find(sichtbar) || passend[0];
  const teilweise = liste.filter((el) => (art !== "feld" || el.matches(FELDER)) && merkmale(el).some((m) => m.includes(z)));
  return teilweise.find(sichtbar) || teilweise[0] || null;
}
// Alle Elemente (auch ausgeblendete), die genau so heißen — für sichtbar/unsichtbar.
// 08.10.2026, Kolibri Jump: Nach „Start“ war der Start-Knopf korrekt ausgeblendet;
// die Suche sah nur Sichtbares und griff zu „Neustart“ — „Start ist noch sichtbar“.
function findeExakt(ziel) {
  const z = norm(ziel);
  if (!z) return [];
  return [...document.querySelectorAll(`${FELDER},${KNOEPFE},[id],[data-cell],[data-id]`)].filter((el) =>
    [el.id, el.getAttribute("aria-label"), el.title, beschriftung(el)].map(norm).filter(Boolean).includes(z));
}
const wertVon = (el) => {
  if (!el) return "";
  if (el.isContentEditable) return el.textContent;
  if (el.type === "checkbox" || el.type === "radio") return String(el.checked);
  return String(el.value == null ? "" : el.value);
};
async function setze(el, wert) {
  el.focus && el.focus();
  if (el.isContentEditable) el.textContent = wert;
  else if (el.type === "checkbox" || el.type === "radio") el.checked = /^(1|true|ja|an)$/i.test(String(wert));
  else el.value = wert;
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", bubbles: true }));
  el.blur && el.blur();
  el.dispatchEvent(new FocusEvent("focusout", { bubbles: true }));
  await warte(60);
}
const bearbeitbar = () => [...document.querySelectorAll(FELDER)].filter((el) => sichtbar(el) && !el.disabled && !el.readOnly
  && !["checkbox", "radio", "range", "color", "date", "time", "month", "datetime-local"].includes((el.type || "").toLowerCase())
  && el.tagName !== "SELECT");
const markierung = (el, zeichen, n) => ((el.type || "").toLowerCase() === "number" ? String(70 + n + zeichen.charCodeAt(0) % 20) : `JOSHI-${zeichen}-${n}`);
async function fuelle(zeichen, grenze = 4) {
  const felder = bearbeitbar().slice(0, grenze);
  for (let i = 0; i < felder.length; i++) await setze(felder[i], markierung(felder[i], zeichen, i));
  return felder.length;
}
const werte = () => bearbeitbar().slice(0, 200).map(wertVon);
const speicher = () => {
  try { const s = window.localStorage; return s && typeof s.__werte === "function" ? JSON.stringify(s.__werte()) : ""; } catch (e) { return ""; }
};
const text = () => (document.body ? document.body.innerText : "");

// ------------------------------------------------------------ Aktionsproben
const LEX = {
  speichern: /speicher|sichern|\bsave\b|💾/i,
  laden: /\bladen\b|\bload\b|öffnen|importier|wiederherstellen/i,
  neu: /^\s*(?:\+\s*)?neu\b|\bneue[sr]?\b|zurücksetz|\breset\b|leeren|\bclear\b|\bnew\b/i,
  rueckgaengig: /rückgängig|\bundo\b|↶|⟲|↩/i,
  wiederholen: /\bwiederholen\b|\bredo\b|↷|⟳|↪/i,
};
const knopfFuer = (aktion) => [...document.querySelectorAll("button,input[type=button],[role=button]")]
  .find((el) => sichtbar(el) && !el.disabled && LEX[aktion].test(beschriftung(el) + " " + (el.title || "") + " " + (el.getAttribute("aria-label") || "")))
  || null;
const ergebnis = (aktion, knopf, art, belege, grund) => ({ aktion, knopf: knopf ? beschriftung(knopf) : "", ergebnis: art, belege: belege || [], grund: grund || "" });
const anteilGleich = (a, b) => {
  if (!a.length) return 0;
  let gleich = 0;
  for (let i = 0; i < a.length; i++) if (a[i] === b[i]) gleich++;
  return gleich / a.length;
};

// ------------------------------------------------------------- Ziehprobe
// Karten verschieben: per Touch (Pointer-Events mit pointerType „touch“,
// TouchEvents, wo es sie gibt), per Antippen → Ziel antippen, und — nur auf dem
// Desktop — per HTML5-Drag&Drop. Gemessen wird, ob der Text des Elements danach
// in einem anderen Behälter steht. HTML5-draggable allein reagiert auf Touch-
// Geräten nicht; das meldet die Probe ausdrücklich.
const ZIEHBAR = "[draggable=true],[data-drag],[data-draggable],.draggable,.ziehbar";
const mitte = (el) => { const r = el.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + Math.min(r.height / 2, 20) }; };
function zeiger(el, typ, punkt, touch) {
  const optionen = { bubbles: true, cancelable: true, composed: true, clientX: punkt.x, clientY: punkt.y,
    pointerId: 7, pointerType: touch ? "touch" : "mouse", isPrimary: true, button: 0,
    buttons: typ === "pointerup" ? 0 : 1 };
  try { el.dispatchEvent(new PointerEvent(typ, optionen)); } catch (e) { /* ohne PointerEvent */ }
  const maus = { pointerdown: "mousedown", pointermove: "mousemove", pointerup: "mouseup" }[typ];
  if (!touch && maus) el.dispatchEvent(new MouseEvent(maus, optionen));
  if (touch && typeof Touch === "function" && typeof TouchEvent === "function") {
    const name = { pointerdown: "touchstart", pointermove: "touchmove", pointerup: "touchend" }[typ];
    try {
      const beruehrung = new Touch({ identifier: 7, target: el, clientX: punkt.x, clientY: punkt.y });
      el.dispatchEvent(new TouchEvent(name, { bubbles: true, cancelable: true,
        touches: typ === "pointerup" ? [] : [beruehrung], targetTouches: typ === "pointerup" ? [] : [beruehrung],
        changedTouches: [beruehrung] }));
    } catch (e) { /* TouchEvent nicht konstruierbar */ }
  }
}
const behaelterVon = (el) => {
  let knoten = el.parentElement;
  while (knoten && knoten !== document.body) {
    if (knoten.children.length && knoten.getBoundingClientRect().height >= 30) return knoten;
    knoten = knoten.parentElement;
  }
  return document.body;
};
// Der Behälter mit eigener Überschrift (etwa ein Tag im Wochenplan) und
// seine gleichartigen Nachbarn sind die natürlichen Ziele — der nächste zuerst.
const artVon = (el) => el.tagName + "." + (typeof el.className === "string" ? el.className.split(" ")[0] : "");
const tagesBehaelter = (el) => {
  let k = el.parentElement;
  while (k && k !== document.body) {
    if ([...k.querySelectorAll("h1,h2,h3,h4,h5")].some((h) => !el.contains(h) && sichtbar(h))) return k;
    k = k.parentElement;
  }
  return null;
};
function ziele(element) {
  const eigen = behaelterVon(element);
  const tag = tagesBehaelter(element);
  let kandidaten = tag && tag.parentElement
    ? [...tag.parentElement.children].filter((k) => k !== tag && sichtbar(k) && artVon(k) === artVon(tag)) : [];
  if (!kandidaten.length) {
    kandidaten = [...document.querySelectorAll("[data-drop],[data-dropzone],.dropzone,.drop,.drop-zone,.ablage")];
    document.querySelectorAll(ZIEHBAR).forEach((el) => { const b = behaelterVon(el); if (!kandidaten.includes(b)) kandidaten.push(b); });
    if (eigen && eigen.parentElement) [...eigen.parentElement.children].forEach((k) => { if (!kandidaten.includes(k)) kandidaten.push(k); });
    kandidaten = kandidaten.filter((k) => k !== eigen && !k.contains(eigen) && !eigen.contains(k) && sichtbar(k));
  }
  const oben = element.getBoundingClientRect().top;
  return kandidaten.sort((a, b) => Math.abs(a.getBoundingClientRect().top - oben) - Math.abs(b.getBoundingClientRect().top - oben));
}
// Wo steht ein Element? Unter welcher Überschrift (Tag, Spalte, Liste)? Die
// Anwendung darf beim Verschieben alles neu zeichnen — gemessen wird deshalb
// die Verteilung nach Überschriften, nicht ein bestimmtes Element.
const KARTE = ZIEHBAR + ",li,[class*=chip],[class*=card],[class*=karte],[class*=item],[class*=uebung],[class*=slot]";
const flach = (el) => kurz(el.innerText, 600);
const kennText = (el) => (String(el.innerText || "").split("\n").map((z) => z.trim())
  .find((z) => /[A-Za-zÄÖÜäöüß]{3,}/.test(z)) || "").replace(/^[^A-Za-zÄÖÜäöüß0-9]+/, "").slice(0, 40).trim();
const ueberschriftVon = (el) => {
  let k = el.parentElement;
  while (k && k !== document.body) {
    const kopf = [...k.querySelectorAll("h1,h2,h3,h4,h5")].find((h) => !el.contains(h) && sichtbar(h) && kurz(h.innerText, 60));
    if (kopf) return kurz(kopf.innerText, 60);
    k = k.parentElement;
  }
  return "";
};
const verteilung = (text) => {
  const treffer = [...document.querySelectorAll(KARTE)].filter((el) => sichtbar(el) && flach(el).includes(text));
  const innerste = treffer.filter((el) => !treffer.some((k) => k !== el && el.contains(k)));
  const karte = new Map();
  innerste.forEach((el) => { const u = ueberschriftVon(el); karte.set(u, (karte.get(u) || 0) + 1); });
  return karte;
};
const summe = (karte) => [...karte.values()].reduce((a, b) => a + b, 0);
function beobachter(element, text) {
  const herkunft = ueberschriftVon(element);
  const vorher = verteilung(text);
  return () => {
    const jetzt = verteilung(text);
    return (jetzt.get(herkunft) || 0) < (vorher.get(herkunft) || 0) && summe(jetzt) >= summe(vorher);
  };
}
// Verschieben per Menü: ein Knopf „verschieben/⇄“ am Element öffnet eine Zielauswahl.
const VERSCHIEBEN = /verschieb|umsetzen|\bmove\b|⇄|↔|⇆/i;
const menueKnopf = (bereich) => [...(bereich || document).querySelectorAll("button,[role=button]")]
  .find((b) => sichtbar(b) && VERSCHIEBEN.test(beschriftung(b) + " " + (b.getAttribute("aria-label") || "") + " " + (b.title || "")));
const klickbar = () => [...document.querySelectorAll("button,[role=button],[role=menuitem],[role=option],option,li[data-tag],li[data-day]")]
  .filter(sichtbar);
async function perMenue(aktion, element, text) {
  const knopf = menueKnopf(element) || menueKnopf(element.parentElement);
  if (!knopf) return null;
  const bewegt = beobachter(element, text);
  const herkunft = ueberschriftVon(element);
  const vorher = new Set(klickbar());
  const vorherAuswahl = new Set([...document.querySelectorAll("select")].filter(sichtbar));
  knopf.click(); await warte(140);
  // Eine Zielauswahl als <select> („– Ziel wählen – / Montag / Dienstag …“)
  const auswahl = [...document.querySelectorAll("select")].find((s) => sichtbar(s) && !vorherAuswahl.has(s));
  if (auswahl) {
    const option = [...auswahl.options].find((o) => o.value && !/wähl|auswahl|–|—/i.test(o.text)
      && kurz(o.text, 40) !== herkunft && !herkunft.startsWith(kurz(o.text, 40)));
    if (option) {
      auswahl.value = option.value;
      auswahl.dispatchEvent(new Event("input", { bubbles: true }));
      auswahl.dispatchEvent(new Event("change", { bubbles: true }));
      await warte(180);
      const bestaetigen = klickbar().find((b) => !vorher.has(b) && b !== knopf && /verschieb|ok|übernehm|bestätig/i.test(kurz(b.innerText, 30)));
      if (!bewegt() && bestaetigen) { bestaetigen.click(); await warte(180); }
      if (bewegt()) return ergebnis(aktion, knopf, "bestanden", ["menu_move", `„${text}“ nach „${kurz(option.text, 30)}“ verschoben`]);
    }
  }
  const neu = klickbar().filter((b) => !vorher.has(b) && b !== knopf && kurz(b.innerText || b.value, 40).length <= 30
    && kurz(b.innerText || b.value, 40) !== herkunft);
  for (const ziel of neu.slice(0, 3)) {
    if (!sichtbar(ziel)) continue;
    const name = kurz(ziel.innerText || ziel.value, 40);
    ziel.click(); await warte(180);
    if (bewegt()) return ergebnis(aktion, knopf, "bestanden", ["menu_move", `„${text}“ über „${name}“ verschoben`]);
  }
  return ergebnis(aktion, knopf, "gescheitert", [], `Der Knopf „${beschriftung(knopf)}“ öffnete keine Zielauswahl, die „${text}“ verschob.`);
}
async function allesAufklappen() {
  // Zugeklappte Bereiche (mobil oft der Standard) zuerst öffnen, sonst gibt es nichts zu ziehen.
  document.querySelectorAll("details:not([open])").forEach((d) => { d.open = true; });
  const zu = [...document.querySelectorAll("[aria-expanded=false]")].filter(sichtbar)
    .filter((k) => !/info|detail/i.test(beschriftung(k) + " " + (k.getAttribute("aria-label") || ""))).slice(0, 20);
  for (const knopf of zu) { try { knopf.click(); } catch (e) { /* weiter */ } }
  if (zu.length) await warte(160);
}
// Ein Griff (⠿) am Element: Viele Anwendungen reagieren nur dort auf den Finger.
const GRIFF = "[data-grip],[data-handle],[data-drag-handle],[class*=grip],[class*=handle],[class*=griff]";
function ziehbar() {
  const direkt = [...document.querySelectorAll(ZIEHBAR)].find(sichtbar);
  if (direkt) return { element: direkt, griff: [...direkt.querySelectorAll(GRIFF)].find(sichtbar) || direkt };
  const griff = [...document.querySelectorAll(GRIFF)].find(sichtbar);
  if (!griff) return null;
  const element = griff.parentElement.closest("li,article,[class*=chip],[class*=card],[class*=karte],[class*=item]")
    || griff.parentElement;
  return { element, griff };
}
async function ziehen(touch) {
  const aktion = touch ? "ziehen_touch" : "ziehen";
  await allesAufklappen();
  const fund = ziehbar();
  const element = fund ? fund.element : null;
  const griff = fund ? fund.griff : null;
  const html5Element = Boolean(element && element.getAttribute("draggable") === "true");
  if (!element) {
    // Keine ziehbaren Elemente — vielleicht ein „Verschieben nach …“-Knopf je Karte.
    const knopf = menueKnopf(document);
    const karte = knopf && (knopf.parentElement.closest("li,article,[class*=chip],[class*=card],[class*=karte],[class*=item]")
      || knopf.parentElement);
    if (!karte) return ergebnis(aktion, null, "nicht_moeglich", [], "Keine ziehbaren Elemente und kein „Verschieben“-Knopf gefunden");
    return (await perMenue(aktion, karte, kennText(karte)))
      || ergebnis(aktion, null, "nicht_moeglich", [], "Kein „Verschieben“-Knopf gefunden");
  }
  const text = kennText(element);
  const kandidat = ziele(element)[0];
  if (!kandidat || !text) return ergebnis(aktion, null, "nicht_moeglich", [], "Kein zweiter Behälter als Ziel gefunden");
  let bewegt = beobachter(element, text);
  // Start und Ziel gemeinsam in den sichtbaren Bereich holen: elementFromPoint
  // sieht nur, was auf dem Bildschirm ist.
  griff.scrollIntoView({ block: "center" });
  const a = griff.getBoundingClientRect(), b = kandidat.getBoundingClientRect();
  window.scrollBy(0, (a.top + b.top) / 2 - window.innerHeight / 2);
  await warte(60);
  // 1. Ziehen (Touch oder Maus über Pointer-Events). Bei Touch gehen alle
  // weiteren Ereignisse an das Element, auf dem der Finger aufsetzte — wie auf
  // echten Geräten (implizites Pointer-Capture, TouchEvents am Startelement).
  const start = mitte(griff), ziel = mitte(kandidat);
  zeiger(griff, "pointerdown", start, touch);
  for (let schritt = 1; schritt <= 6; schritt++) {
    const punkt = { x: start.x + (ziel.x - start.x) * schritt / 6, y: start.y + (ziel.y - start.y) * schritt / 6 };
    zeiger(touch ? griff : (document.elementFromPoint(punkt.x, punkt.y) || element), "pointermove", punkt, touch);
    await warte(30);
  }
  zeiger(touch ? griff : (document.elementFromPoint(ziel.x, ziel.y) || kandidat), "pointerup", ziel, touch);
  await warte(160);
  if (bewegt()) return ergebnis(aktion, null, "bestanden", [touch ? "touch_drag" : "pointer_drag", `„${text}“ verschoben`]);
  // 2. Antippen, dann Ziel antippen
  if (element.isConnected && kandidat.isConnected) {
    element.click(); await warte(80); kandidat.click(); await warte(160);
    if (bewegt()) return ergebnis(aktion, null, "bestanden", ["tap_move", `„${text}“ per Antippen verschoben`]);
  }
  // 3. HTML5-Drag&Drop — auf dem Desktop ein Beleg, auf Touch-Geräten nur die Erklärung
  let html5 = false;
  if (element.isConnected && kandidat.isConnected) {
    try {
      const daten = new DataTransfer();
      element.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true, dataTransfer: daten }));
      kandidat.dispatchEvent(new DragEvent("dragenter", { bubbles: true, cancelable: true, dataTransfer: daten }));
      kandidat.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: daten }));
      kandidat.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: daten }));
      element.dispatchEvent(new DragEvent("dragend", { bubbles: true, cancelable: true, dataTransfer: daten }));
      await warte(160);
      html5 = bewegt();
    } catch (e) { /* ohne DragEvent */ }
  }
  if (!touch && html5) return ergebnis(aktion, null, "bestanden", ["html5_drag", `„${text}“ verschoben`]);
  // 4. Verschieben-Menü an der Karte
  const karte = [...document.querySelectorAll(ZIEHBAR)].find((el) => sichtbar(el) && flach(el).includes(text)) || element;
  const menue = await perMenue(aktion, karte, text);
  if (menue && menue.ergebnis === "bestanden") return menue;
  const hinweis = html5Element
    ? " Die Karten sind nur HTML5-draggable (dragstart/drop) — das reagiert auf Touch-Geräten nicht. "
      + "Pointer-Events (pointerdown/pointermove/pointerup, touch-action: none) oder „Antippen → Ziel antippen“ ergänzen."
    : "";
  return ergebnis(aktion, null, "gescheitert", [], touch
    ? `„${text}“ ließ sich weder per Touch ziehen noch per Antippen verschieben.${hinweis}`
    : `„${text}“ ließ sich nicht in einen anderen Behälter ziehen.${hinweis}`);
}

async function probe(aktion) {
  if (aktion === "ziehen" || aktion === "ziehen_touch") return ziehen(aktion === "ziehen_touch");
  const knopf = knopfFuer(aktion);
  if (!knopf) return ergebnis(aktion, null, "nicht_moeglich", [], `Kein Knopf für „${aktion}“ gefunden`);
  if (aktion === "speichern") {
    await fuelle("A");
    const s0 = speicher(), e0 = (J.exporte || []).length, d0 = downloads;
    knopf.click(); await warte(180);
    const s1 = speicher();
    if (s1 !== s0) return ergebnis(aktion, knopf, "bestanden", ["local_storage_changed"]);
    if (/JOSHI-A-/.test(s1)) return ergebnis(aktion, knopf, "bestanden", ["local_storage_changed (automatisch gespeichert)"]);
    if ((J.exporte || []).length > e0) return ergebnis(aktion, knopf, "bestanden", ["export_requested"]);
    if (downloads > d0) return ergebnis(aktion, knopf, "bestanden", ["download_triggered"]);
    return ergebnis(aktion, knopf, "gescheitert", [], "Nach dem Klick änderte sich der Speicher nicht und es wurde keine Datei angefordert");
  }
  if (aktion === "laden") {
    const sichern = knopfFuer("speichern");
    if (!sichern) return ergebnis(aktion, knopf, "nicht_moeglich", [], "Kein Speichern-Knopf, um einen bekannten Stand herzustellen");
    if (!(await fuelle("L"))) return ergebnis(aktion, knopf, "nicht_moeglich", [], "Kein Eingabefeld, dessen Stand sich prüfen ließe");
    sichern.click(); await warte(180);
    const zielWerte = werte(), zielText = text(), gespeichert = speicher();
    await fuelle("X");
    if (speicher() !== gespeichert) {
      return ergebnis(aktion, knopf, "nicht_moeglich", [], "Die Anwendung speichert jede Eingabe automatisch — Laden lässt sich so nicht gegenprüfen");
    }
    if (anteilGleich(zielWerte, werte()) === 1 && text() === zielText) {
      return ergebnis(aktion, knopf, "nicht_moeglich", [], "Der Stand ließ sich nicht verändern");
    }
    dateiDialog = false;
    knopf.click(); await warte(220);
    if (dateiDialog) return ergebnis(aktion, knopf, "nicht_moeglich", [], "„Laden“ öffnet einen Dateidialog");
    if (anteilGleich(zielWerte, werte()) >= 0.8 || text() === zielText) {
      return ergebnis(aktion, knopf, "bestanden", ["local_storage_restored"]);
    }
    return ergebnis(aktion, knopf, "gescheitert", [], "Nach „Laden“ kehrte der gespeicherte Stand nicht zurück");
  }
  if (aktion === "neu") {
    const gefuellt = await fuelle("N");
    const t0 = text().length, n0 = document.querySelectorAll("body *").length;
    const vorher = werte();
    knopf.click(); await warte(220);
    const nachher = werte();
    let zurueck = 0;
    vorher.forEach((w, i) => { if (/^JOSHI-N-|^\d+$/.test(w) && nachher[i] !== w) zurueck++; });
    const weniger = text().length < t0 * 0.8 || document.querySelectorAll("body *").length < n0;
    if ((gefuellt && zurueck) || weniger) {
      return ergebnis(aktion, knopf, "bestanden", ["reset" + (zurueck ? `: ${zurueck} Felder zurückgesetzt` : ": Inhalt entfernt")]);
    }
    return ergebnis(aktion, knopf, "gescheitert", [], "Nach „Neu“ blieben die eingegebenen Daten unverändert");
  }
  if (aktion === "rueckgaengig" || aktion === "wiederholen") {
    const undo = knopfFuer("rueckgaengig");
    if (!undo) return ergebnis(aktion, knopf, "nicht_moeglich", [], "Kein Rückgängig-Knopf");
    const feld = bearbeitbar()[0];
    if (!feld) return ergebnis(aktion, knopf, "nicht_moeglich", [], "Kein Eingabefeld für die Probe");
    const kennung = feld.id, t0 = text(), v0 = wertVon(feld);
    await setze(feld, markierung(feld, "U", 1));
    const t1 = text(), v1 = wertVon(feld);
    if (v1 === v0 && t1 === t0) return ergebnis(aktion, knopf, "nicht_moeglich", [], "Die Eingabe veränderte nichts");
    const wieder = () => (kennung && document.getElementById(kennung)) || bearbeitbar()[0];
    const zurueck = () => wertVon(wieder()) === v0 || (t1 !== t0 && text() === t0);
    // Manche Anwendungen merken sich „input“ und „change“ getrennt: Zwei
    // Rückgängig-Schritte sind dann eine Eingabe.
    let rueck = false;
    for (let versuch = 0; versuch < 2 && !rueck; versuch++) { undo.click(); await warte(180); rueck = zurueck(); }
    if (!rueck && t1 === t0) {
      return ergebnis(aktion, undo, "nicht_moeglich", [], "Die Test-Eingabe änderte nur das Feld selbst — ob die Anwendung sie als Schritt merkt, ist nicht erkennbar");
    }
    if (aktion === "rueckgaengig") {
      return rueck ? ergebnis(aktion, undo, "bestanden", ["undo_restored"])
        : ergebnis(aktion, undo, "gescheitert", [], "Nach „Rückgängig“ blieb die letzte Eingabe bestehen");
    }
    if (!rueck) return ergebnis(aktion, knopf, "nicht_moeglich", [], "Rückgängig wirkte nicht — Wiederholen nicht prüfbar");
    const vorwaerts = () => wertVon(wieder()) === v1 || (t1 !== t0 && text() === t1);
    let wiederda = false;
    for (let versuch = 0; versuch < 2 && !wiederda; versuch++) { knopf.click(); await warte(180); wiederda = vorwaerts(); }
    return wiederda
      ? ergebnis(aktion, knopf, "bestanden", ["redo_restored"])
      : ergebnis(aktion, knopf, "gescheitert", [], "Nach „Wiederholen“ kehrte die Eingabe nicht zurück");
  }
  return ergebnis(aktion, knopf, "nicht_moeglich", [], "Für diese Aktion gibt es keine Probe");
}

// ---------------------------------------------------------------- Szenarien
const NICHT_NACHSTELLBAR = {
  zweite_sitzung: "Eine zweite Sitzung lässt sich in der isolierten Prüfseite nicht öffnen",
  offline: "Eine echte Offline-Verbindung lässt sich hier nicht nachstellen (die Seite hat ohnehin kein Netz)",
  online: "Ein Wiederverbinden lässt sich hier nicht nachstellen (die Seite hat ohnehin kein Netz)",
};

async function szenario(schritte) {
  let messbeginn = performance.now();
  const messwerte = {};
  for (let i = 0; i < schritte.length; i++) {
    const s = schritte[i] || {};
    const nummer = `Schritt ${i + 1} (${s.art})`;
    if (NICHT_NACHSTELLBAR[s.art]) return { ergebnis: "nicht_beweisbar", grund: NICHT_NACHSTELLBAR[s.art], messwerte };
    if (s.art === "eingeben") {
      const el = finde(s.ziel, "feld");
      if (!el) return { ergebnis: "nicht_beweisbar", grund: `${nummer}: Feld „${s.ziel}“ nicht gefunden`, messwerte };
      await setze(el, s.wert == null ? "" : String(s.wert));
    } else if (s.art === "klicken") {
      const el = finde(s.ziel, "knopf");
      if (!el) return { ergebnis: "nicht_beweisbar", grund: `${nummer}: Knopf „${s.ziel}“ nicht gefunden`, messwerte };
      el.click(); await warte(120);
    } else if (s.art === "taste") {
      const el = s.ziel ? finde(s.ziel, "feld") : document.activeElement;
      if (!el) return { ergebnis: "nicht_beweisbar", grund: `${nummer}: Ziel „${s.ziel}“ nicht gefunden`, messwerte };
      ["keydown", "keyup"].forEach((typ) => el.dispatchEvent(new KeyboardEvent(typ, { key: String(s.wert || "Enter"), bubbles: true })));
      await warte(60);
    } else if (s.art === "warten") {
      await warte(Math.min(2000, Number(s.ms) || 100));
    } else if (s.art === "messen") {
      messbeginn = performance.now();
    } else if (s.art === "neu_laden") {
      return { ergebnis: "nicht_beweisbar", grund: "Neuladen wird vom Prüfer zwischen zwei Phasen erledigt", messwerte };
    } else {
      // Prüfungen
      const el = s.ziel ? finde(s.ziel, s.art.startsWith("wert") ? "feld" : "") : null;
      if (s.ziel && !el && s.art !== "text_enthaelt" && s.art !== "text_fehlt") {
        if (s.art === "unsichtbar") continue;
        return { ergebnis: "nicht_beweisbar", grund: `${nummer}: Ziel „${s.ziel}“ nicht gefunden`, messwerte };
      }
      const quelle = el ? (el.matches(FELDER) ? wertVon(el) : el.innerText) : text();
      const erwartet = norm(s.wert);
      let ok = true, gefunden = "";
      if (s.art === "text_enthaelt") {
        ok = norm(quelle).includes(erwartet);
        const frei = !ok && jetztMuster(erwartet);
        if (frei) ok = frei.test(norm(quelle));
        gefunden = kurz(quelle, 160);
      }
      else if (s.art === "text_fehlt") { ok = !norm(quelle).includes(erwartet); gefunden = kurz(quelle, 160); }
      else if (s.art === "wert_ist") { ok = norm(quelle) === erwartet; gefunden = kurz(quelle, 80); }
      else if (s.art === "wert_enthaelt") { ok = norm(quelle).includes(erwartet); gefunden = kurz(quelle, 80); }
      else if (s.art === "speicher_enthaelt") { ok = norm(speicher()).includes(erwartet); gefunden = kurz(speicher(), 160); }
      else if (s.art === "keine_fehler") { const neu = (J.fehler || []).slice(fehlerStart); ok = !neu.length; gefunden = neu.map((f) => f.text).join("; ").slice(0, 160); }
      else if (s.art === "sichtbar") {
        const exakt = findeExakt(s.ziel);
        ok = exakt.length ? exakt.some(sichtbar) : sichtbar(el);
        gefunden = ok ? "sichtbar" : "unsichtbar";
      }
      else if (s.art === "unsichtbar") {
        const exakt = findeExakt(s.ziel);
        ok = exakt.length ? !exakt.some(sichtbar) : (!el || !sichtbar(el));
        gefunden = ok ? "unsichtbar" : "sichtbar";
      }
      else if (s.art === "dauer_hoechstens") {
        const dauer = Math.round(performance.now() - messbeginn);
        messwerte[`dauer_ms_${i + 1}`] = dauer;
        ok = dauer <= (Number(s.ms) || 0); gefunden = `${dauer} ms`;
      }
      if (!ok) {
        return { ergebnis: "gescheitert", grund: `${nummer}: erwartet „${kurz(s.wert || s.ms, 80)}“, gefunden „${gefunden}“`, messwerte };
      }
    }
  }
  const neueFehler = (J.fehler || []).slice(fehlerStart);
  if (neueFehler.length) return { ergebnis: "gescheitert", grund: "Skriptfehler: " + neueFehler[0].text, messwerte };
  return { ergebnis: "bestanden", grund: "", messwerte };
}

const antwort = { aktionen: [], szenario: null };
for (const aktion of A.aktionen || []) {
  try { antwort.aktionen.push(await probe(aktion)); }
  catch (e) { antwort.aktionen.push(ergebnis(aktion, null, "nicht_moeglich", [], "Probe brach ab: " + (e && e.message))); }
}
if (Array.isArray(A.schritte)) {
  try { antwort.szenario = await szenario(A.schritte); }
  catch (e) { antwort.szenario = { ergebnis: "nicht_beweisbar", grund: "Szenario brach ab: " + (e && e.message), messwerte: {} }; }
}
antwort.zustand = typeof J.zustand === "function" ? J.zustand() : null;
antwort.fehler = (J.fehler || []).slice(fehlerStart, fehlerStart + 5);
return JSON.stringify(antwort);
