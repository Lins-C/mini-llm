// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
// Liest die fertig geladene Seite, ohne sie zu verändern: Gliederung für die
// Prüfung und die Chat-Übergabe, dazu der sichtbare Inhalt als Markdown für
// den Word-Export. Läuft als Funktionsrumpf (callAsyncJavaScript).
const J = window.__joshi || { fehler: [], dialoge: [] };
const sichtbar = (el) => {
  if (!el || !el.getBoundingClientRect) return false;
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0";
};
const kurz = (t, n = 120) => String(t || "").replace(/\s+/g, " ").trim().slice(0, n);
const beschriftung = (el) => {
  if (el.id) {
    const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (l) return kurz(l.innerText, 80);
  }
  const huelle = el.closest("label");
  if (huelle) return kurz(huelle.innerText, 80);
  return kurz(el.getAttribute("aria-label") || el.getAttribute("placeholder") || el.name || el.id, 80);
};
const felder = [...document.querySelectorAll("input,select,textarea")]
  .filter((el) => sichtbar(el) && !["hidden", "submit", "button", "reset"].includes((el.type || "").toLowerCase()))
  .slice(0, 60)
  .map((el) => ({
    label: beschriftung(el),
    typ: el.tagName === "INPUT" ? (el.type || "text").toLowerCase() : el.tagName.toLowerCase(),
    id: el.id || "",
    wert: ["checkbox", "radio"].includes((el.type || "").toLowerCase())
      ? (el.checked ? "ja" : "nein")
      : el.tagName === "SELECT" ? kurz(el.options[el.selectedIndex]?.text || "", 80) : kurz(el.value, 80),
  }));
// Symbolknöpfe („i“, „×“) heißen, was ihr aria-label oder title sagt.
const knopfname = (el) => {
  const text = kurz(el.innerText || el.value, 60);
  const zusatz = kurz(el.getAttribute("aria-label") || el.title, 60);
  return zusatz && text.length <= 2 ? kurz(zusatz + (text ? ` (${text})` : ""), 60) : (text || zusatz);
};
const knoepfe = [...document.querySelectorAll("button,input[type=button],input[type=submit],[role=button],summary")]
  .filter(sichtbar).slice(0, 60)
  .map(knopfname)
  .filter(Boolean);
const ueberschriften = [...document.querySelectorAll("h1,h2,h3")].filter(sichtbar).slice(0, 30).map((h) => kurz(h.innerText, 100));
const text = document.body ? document.body.innerText : "";

// Sichtbarkeitsmaße gegen die weiße Seite: Wie viel zeigt die Anwendung
// wirklich? Eine Seite, die lädt, kann trotzdem leer sein.
const alleSichtbaren = [...document.querySelectorAll("body *")]
  .filter((el) => !["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "HEAD", "LINK", "META"].includes(el.tagName) && sichtbar(el));
const ZEIGT = ["IMG", "CANVAS", "SVG", "INPUT", "SELECT", "TEXTAREA", "BUTTON", "VIDEO"];
let huelle = null;
alleSichtbaren.forEach((el) => {
  const eigenerText = el.children.length === 0 && (el.innerText || "").trim().length > 0;
  if (!eigenerText && !ZEIGT.includes(el.tagName)) return;
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return;
  huelle = huelle
    ? { l: Math.min(huelle.l, r.left), o: Math.min(huelle.o, r.top), re: Math.max(huelle.re, r.right), u: Math.max(huelle.u, r.bottom) }
    : { l: r.left, o: r.top, re: r.right, u: r.bottom };
});
const sichtFlaeche = huelle
  ? Math.round(((huelle.re - huelle.l) * (huelle.u - huelle.o)) / (window.innerWidth * window.innerHeight) * 100)
  : 0;

// Stil als Beleg für Gestaltungswünsche („heller“, „größere Schrift“): nur
// wenige berechnete Werte, damit die Abnahme vorher und nachher vergleichen
// kann — keine Stylesheets, kein Code.
const flaeche = (el) => {
  while (el && el.nodeType === 1) {
    const f = getComputedStyle(el).backgroundColor;
    if (f && f !== "transparent" && !/rgba\([^)]*,\s*0\)$/.test(f)) return f;
    el = el.parentElement;
  }
  return "rgb(255, 255, 255)";
};
const ersteSichtbare = (auswahl) => [...document.querySelectorAll(auswahl)].find(sichtbar) || null;
const stilVon = (el) => (el ? { farbe: getComputedStyle(el).color, flaeche: flaeche(el),
                                 groesse: getComputedStyle(el).fontSize } : null);
const stil = document.body ? {
  seite: flaeche(document.body),
  text: getComputedStyle(document.body).color,
  schrift: String(getComputedStyle(document.body).fontFamily || "").split(",")[0].replace(/["']/g, "").trim(),
  schriftgroesse: getComputedStyle(document.body).fontSize,
  ueberschrift: stilVon(ersteSichtbare("h1,h2")),
  knopf: stilVon(ersteSichtbare("button,[role=button]")),
  karte: (() => { const k = ersteSichtbare("main,section,article,.card,.karte,form,table"); return k ? flaeche(k) : null; })(),
} : null;

// Farbfamilien und Glaseffekte für Wünsche wie „in Rot, Gelb, Grün“ oder
// „Glas-Optik“: gezählt über sichtbare Elemente (Hintergrund, Rahmen, Schrift).
const FAMILIEN = [["rot", 345, 15], ["orange", 15, 40], ["gelb", 40, 70], ["gruen", 70, 170], ["tuerkis", 170, 200],
                  ["blau", 200, 255], ["lila", 255, 300], ["pink", 300, 345]];
const familie = (farbe) => {
  const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/.exec(farbe || "");
  if (!m || (m[4] !== undefined && parseFloat(m[4]) < 0.15)) return null;
  const [r, g, b] = [m[1], m[2], m[3]].map((x) => parseFloat(x) / 255);
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  if (max < 0.2 || d / (max || 1) < 0.35 || d < 0.12) return null;
  let h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  h = (h * 60 + 360) % 360;
  const f = FAMILIEN.find(([, von, bis]) => (von > bis ? h >= von || h < bis : h >= von && h < bis));
  return f ? f[0] : null;
};
const gestaltung = (() => {
  const farben = {};
  let glas = 0, transparent = 0, schatten = 0;
  const alle = [...document.querySelectorAll("body *")].filter((el) => !["SCRIPT", "STYLE"].includes(el.tagName)).slice(0, 2500);
  for (const el of alle) {
    if (!sichtbar(el)) continue;
    const s = getComputedStyle(el);
    for (const wert of [s.backgroundColor, s.borderTopColor, s.color, s.fill]) {
      const f = familie(wert);
      if (f) farben[f] = (farben[f] || 0) + 1;
    }
    const verlauf = (s.backgroundImage || "").match(/rgba?\([^)]*\)/g) || [];
    verlauf.forEach((wert) => { const f = familie(wert); if (f) farben[f] = (farben[f] || 0) + 1; });
    const unschaerfe = s.backdropFilter || s.webkitBackdropFilter || "";
    if (unschaerfe && unschaerfe !== "none") glas++;
    const alpha = /rgba\([^)]*,\s*([\d.]+)\)/.exec(s.backgroundColor || "");
    if (alpha && parseFloat(alpha[1]) > 0.05 && parseFloat(alpha[1]) < 0.9) transparent++;
    if (s.boxShadow && s.boxShadow !== "none") schatten++;
  }
  return { farben, glas, transparent, schatten };
})();

// Aufbau: Wie viele Spalten bilden die wiederholten Karten, wie breit sind sie
// — und gibt es leere Flächen, die sich farblich vom Hintergrund abheben (ein
// „weißer Kasten“ in einer dunklen Anwendung)? Belege für Layout-Wünsche.
const hell = (farbe) => {
  const m = String(farbe || "").match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/);
  if (!m || (m[4] !== undefined && Number(m[4]) < 0.5)) return null;
  return (0.2126 * m[1] + 0.7152 * m[2] + 0.0722 * m[3]) / 255;
};
const layout = (() => {
  const breite = window.innerWidth;
  let beste = null;
  document.querySelectorAll("body *").forEach((el) => {
    if (el.children.length < 3 || !sichtbar(el)) return;
    const kinder = [...el.children].filter((k) => sichtbar(k) && k.getBoundingClientRect().width >= breite * 0.2
      && k.getBoundingClientRect().height >= 40);
    if (kinder.length < 3) return;
    const klassen = new Map();
    kinder.forEach((k) => { const s = k.tagName + "." + (typeof k.className === "string" ? k.className.split(" ")[0] : "");
      klassen.set(s, (klassen.get(s) || 0) + 1); });
    const gruppe = Math.max(...klassen.values());
    if (gruppe >= 3 && (!beste || gruppe > beste.anzahl)) beste = { el, anzahl: gruppe, kinder };
  });
  let spalten = null, kartenbreite = null;
  if (beste) {
    const links = new Set(beste.kinder.map((k) => Math.round(k.getBoundingClientRect().left / 8)));
    spalten = links.size;
    kartenbreite = Math.round(Math.max(...beste.kinder.map((k) => k.getBoundingClientRect().width)) / breite * 100);
  }
  const seite = hell(flaeche(document.body));
  const leereFlaechen = [];
  if (seite !== null) {
    const MEDIEN = ["IMG", "CANVAS", "SVG", "VIDEO", "INPUT", "SELECT", "TEXTAREA", "BUTTON", "IFRAME", "PICTURE", "OPTION"];
    for (const el of document.querySelectorAll("body *")) {
      if (leereFlaechen.length >= 5) break;
      if (MEDIEN.includes(el.tagName) || !sichtbar(el)) continue;
      const r = el.getBoundingClientRect();
      if (r.width * r.height < window.innerWidth * window.innerHeight * 0.01 || r.top > window.innerHeight * 3) continue;
      const eigen = hell(getComputedStyle(el).backgroundColor);
      if (eigen === null || Math.abs(eigen - seite) < 0.5) continue;
      if ((el.innerText || "").trim() || el.querySelector(MEDIEN.join(","))) continue;
      leereFlaechen.push({ tag: el.tagName.toLowerCase(), klasse: kurz(typeof el.className === "string" ? el.className : "", 40),
        x: Math.round(r.left), y: Math.round(r.top), breite: Math.round(r.width), hoehe: Math.round(r.height),
        farbe: getComputedStyle(el).backgroundColor });
    }
  }
  return { spalten, karten: beste ? beste.anzahl : 0, kartenbreite, leereFlaechen };
})();

// Markdown in Lesereihenfolge: Überschriften, Absätze, Listen, Tabellen und
// Formularfelder mit ihrem aktuellen Wert.
const zeilen = [];
const gesehen = new Set();
const tabelle = (t) => {
  const reihen = [...t.rows].slice(0, 200).map((r) => [...r.cells].map((c) => kurz(c.innerText, 200).replace(/\|/g, "/")));
  if (!reihen.length) return;
  const breite = Math.max(...reihen.map((r) => r.length));
  const auf = (r) => "| " + [...r, ...Array(breite - r.length).fill("")].join(" | ") + " |";
  zeilen.push("", auf(reihen[0]), "| " + Array(breite).fill("---").join(" | ") + " |", ...reihen.slice(1).map(auf), "");
};
const gehe = (knoten) => {
  if (!knoten || knoten.nodeType !== 1 || gesehen.has(knoten)) return;
  const tag = knoten.tagName.toLowerCase();
  if (["script", "style", "noscript", "template", "svg", "canvas"].includes(tag)) return;
  if (!sichtbar(knoten)) return;
  if (/^h[1-6]$/.test(tag)) { zeilen.push("", "#".repeat(Number(tag[1])) + " " + kurz(knoten.innerText, 200), ""); return; }
  if (tag === "table") { tabelle(knoten); return; }
  if (tag === "li") { zeilen.push("- " + kurz(knoten.innerText, 400)); return; }
  if (["input", "select", "textarea"].includes(tag)) {
    const typ = (knoten.type || "").toLowerCase();
    if (["hidden", "submit", "button", "reset", "password", "file"].includes(typ)) return;
    const wert = ["checkbox", "radio"].includes(typ) ? (knoten.checked ? "ja" : "nein")
      : tag === "select" ? kurz(knoten.options[knoten.selectedIndex]?.text || "", 120) : kurz(knoten.value, 300);
    zeilen.push(`**${beschriftung(knoten) || "Eingabe"}:** ${wert || "–"}`, "");
    return;
  }
  if (tag === "label") {
    const feld = knoten.querySelector("input,select,textarea");
    if (feld) { gehe(feld); return; }
    if (knoten.htmlFor) return;
  }
  if (["button"].includes(tag)) return;
  const hatBlockKinder = [...knoten.children].some((k) => {
    const d = getComputedStyle(k).display;
    return !d.startsWith("inline") || ["input", "select", "textarea", "table"].includes(k.tagName.toLowerCase());
  });
  if (!hatBlockKinder) {
    const t = kurz(knoten.innerText, 1200);
    if (t) zeilen.push(t, "");
    return;
  }
  [...knoten.children].forEach(gehe);
};
if (document.body) [...document.body.children].forEach(gehe);
const markdown = zeilen.join("\n").replace(/\n{3,}/g, "\n\n").trim().slice(0, 60000);

return JSON.stringify({
  titel: kurz(document.title, 120),
  h1: kurz(document.querySelector("h1")?.innerText || "", 120),
  ueberschriften, felder, knoepfe,
  anzahl: {
    tabellen: document.querySelectorAll("table").length,
    diagramme: document.querySelectorAll("canvas").length + [...document.querySelectorAll("svg")].filter((s) => s.getBoundingClientRect().width > 80).length,
    bilder: document.querySelectorAll("img").length,
    elemente: document.querySelectorAll("body *").length,
  },
  textLaenge: text.trim().length,
  sichtbar: {
    elemente: alleSichtbaren.length,
    interaktiv: alleSichtbaren.filter((el) => ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(el.tagName)
      || el.getAttribute("role") === "button" || (el.tagName === "A" && el.getAttribute("href"))).length,
    flaecheProzent: sichtFlaeche,
  },
  stil,
  gestaltung,
  layout,
  ueberlauf: document.documentElement.scrollWidth > window.innerWidth + 4,
  breite: window.innerWidth,
  markdown,
  fehler: J.fehler || [],
  dialoge: J.dialoge || [],
  zustand: typeof J.zustand === "function" ? J.zustand() : null,
});
