// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
// Bedienprobe: füllt jedes sichtbare Feld, klickt jeden Knopf und misst, ob
// die Seite reagiert und dabei fehlerfrei bleibt. Der Python-Teil setzt davor
// `const __vorher = …` (die Gliederung aus inhalt.js vor der Bedienung).
const J = window.__joshi || { fehler: [], dialoge: [] };
const warte = (ms) => new Promise((r) => setTimeout(r, ms));
const sichtbar = (el) => {
  if (!el || !el.getBoundingClientRect || !el.isConnected) return false;
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none";
};
const fehlerVorher = (J.fehler || []).length;
// Was die Anwendung zeigt — ohne die Werte der Eingabefelder selbst: Dass ein
// Feld nach dem Ausfüllen anders aussieht, ist noch keine Reaktion.
// Klassen und Zustandsattribute gehören dazu: Eine Bewertung, die nur den
// gewählten Knopf hervorhebt, ändert keinen Text.
const signatur = () => {
  let teile = document.body ? document.body.innerText : "";
  document.querySelectorAll("output").forEach((el) => { teile += "|" + el.value; });
  document.querySelectorAll("body *").forEach((el) => {
    if (el.tagName === "SCRIPT" || el.tagName === "STYLE") return;
    teile += "|" + (typeof el.className === "string" ? el.className : "")
      + (el.hidden ? "h" : "") + (el.getAttribute("style") || "")
      + (el.getAttribute("aria-pressed") || "") + (el.getAttribute("aria-checked") || "")
      + (el.getAttribute("aria-selected") || "") + (el.disabled ? "d" : "");
  });
  document.querySelectorAll("canvas").forEach((c) => {
    try { teile += "|c" + c.toDataURL().length + ":" + c.toDataURL().slice(-64); } catch (e) { teile += "|c?"; }
  });
  document.querySelectorAll("svg").forEach((s) => { teile += "|s" + s.innerHTML.length; });
  teile += "|" + document.querySelectorAll("body *").length;
  return teile;
};
const ausgangstext = signatur();

// Felder füllen — mit Werten, die ein Mensch eingeben würde.
let gefuellt = 0;
const felder = [...document.querySelectorAll("input,select,textarea")].filter((el) => sichtbar(el) && !el.disabled && !el.readOnly);
const sichtbareKnoepfe = () => [...document.querySelectorAll("button,input[type=button],input[type=submit],[role=button]")]
  .filter((el) => sichtbar(el)).length;
const knoepfeVorEingabe = sichtbareKnoepfe();
const urwerte = new Map();
for (const el of felder.slice(0, 40)) {
  const typ = (el.type || "").toLowerCase();
  urwerte.set(el, { wert: el.value, index: el.selectedIndex, an: el.checked });
  try {
    if (["hidden", "file", "submit", "button", "reset", "image", "password"].includes(typ)) continue;
    if (typ === "checkbox" || typ === "radio") { el.click(); gefuellt++; continue; }
    if (el.tagName === "SELECT") {
      if (el.options.length > 1) el.selectedIndex = el.selectedIndex === 1 ? 0 : 1;
    } else if (typ === "number" || typ === "range") {
      const min = parseFloat(el.min), max = parseFloat(el.max);
      let wert = !isNaN(min) && !isNaN(max) ? (min + max) / 2 : !isNaN(min) ? min + 12 : !isNaN(max) ? max / 2 : 42;
      const schritt = parseFloat(el.step);
      if (!isNaN(schritt) && schritt > 0) wert = Math.round(wert / schritt) * schritt;
      if (String(el.value) === String(wert)) wert = wert + (isNaN(schritt) || schritt <= 0 ? 1 : schritt);
      if (!isNaN(max) && wert > max) wert = max;
      el.value = String(wert);
    } else if (typ === "date") el.value = "2026-09-19";
    else if (typ === "time") el.value = "09:30";
    else if (typ === "datetime-local") el.value = "2026-09-19T09:30";
    else if (typ === "month") el.value = "2026-09";
    else if (typ === "email") el.value = "test@example.com";
    else if (typ === "tel") el.value = "0123 456789";
    else if (typ === "url") el.value = "https://example.com";
    else if (typ === "color") el.value = "#3366cc";
    else {
      const zahl = el.inputMode === "numeric" || el.inputMode === "decimal" || /\d/.test(el.placeholder || "");
      el.value = zahl ? "42" : (el.tagName === "TEXTAREA" ? "Testeintrag für die Prüfung" : "Test");
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    gefuellt++;
  } catch (e) { /* Fehler meldet die Laufzeit */ }
}
await warte(120);
// Filter, Suche oder Datumsauswahl können mit Testwerten die ganze Liste
// leeren — dann fände die Probe die Knöpfe darin nie (gefunden am 29.09.2026:
// „Umplanen“ und „Maps-Link kopieren“ blieben ungeklickt, weil der
// Statusfilter alle Touren ausblendete). Solche Felder bekommen ihren
// Ausgangswert zurück.
const zurueckgesetzt = [];
if (sichtbareKnoepfe() < knoepfeVorEingabe * 0.7) {
  const ausloesen = (el) => { el.dispatchEvent(new Event("input", { bubbles: true })); el.dispatchEvent(new Event("change", { bubbles: true })); };
  for (const [el, ur] of [...urwerte.entries()].reverse()) {
    if (sichtbareKnoepfe() >= knoepfeVorEingabe * 0.9) break;
    const jetzt = { wert: el.value, index: el.selectedIndex, an: el.checked };
    const vorher = sichtbareKnoepfe();
    try {
      if (el.type === "checkbox" || el.type === "radio") el.checked = ur.an;
      else if (el.tagName === "SELECT") el.selectedIndex = ur.index;
      else el.value = ur.wert;
      ausloesen(el);
      await warte(40);
      if (sichtbareKnoepfe() > vorher) { zurueckgesetzt.push(el.id || el.name || el.tagName.toLowerCase()); continue; }
      if (el.type === "checkbox" || el.type === "radio") el.checked = jetzt.an;
      else if (el.tagName === "SELECT") el.selectedIndex = jetzt.index;
      else el.value = jetzt.wert;
      ausloesen(el);
    } catch (e) { /* Laufzeit */ }
  }
  await warte(80);
}
const nachEingabe = signatur();

// Was ein Klick sichtbar macht, ist der Beweis für Anforderungen wie „beim
// Klick erscheint eine Eingabemaske“. Vor und nach jedem Klick wird deshalb
// festgehalten, welche Felder, Knöpfe und Beschriftungen zu sehen sind.
const kurz = (t, n = 60) => String(t || "").replace(/\s+/g, " ").trim().slice(0, n);
const beschriftungen = () => new Set([
  ...[...document.querySelectorAll("h1,h2,h3,h4,label,legend,summary,th,figcaption")]
    .filter(sichtbar).map((el) => kurz(el.innerText)),
  // Auch Knöpfe, die erst durch den Klick erscheinen — „Als PDF speichern“ ist
  // der Beweis, dass eine geforderte Ausgabe existiert.
  ...[...document.querySelectorAll("button,input[type=button],input[type=submit],[role=button]")]
    .filter(sichtbar).map((el) => kurz(el.innerText || el.value)),
].filter(Boolean));
const oberflaeche = () => ({
  felder: [...document.querySelectorAll("input,select,textarea")].filter(sichtbar).length,
  knoepfe: [...document.querySelectorAll("button,input[type=button],input[type=submit],[role=button]")].filter(sichtbar).length,
  texte: beschriftungen(),
  laenge: (document.body ? document.body.innerText : "").length,
});

// Wirkungen eines Klicks — typisiert. Ein Speichern-Knopf zeigt sich im
// Speicher, ein Export in der Anforderung an JOSHI, ein Filter in der
// Sichtbarkeit. „Etwas Neues erschien“ ist nur eine von vielen Wirkungen.
// Downloads werden nur gezählt, nie ausgeführt.
let downloads = 0;
try {
  const ankerKlick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.hasAttribute("download") || /^(blob|data):/i.test(this.getAttribute("href") || "")) downloads++;
    return ankerKlick.apply(this, arguments);
  };
} catch (e) { /* ohne Zählung */ }
document.addEventListener("click", (e) => {
  const anker = e.target && e.target.closest ? e.target.closest("a[download],a[href^='blob:'],a[href^='data:']") : null;
  if (anker) downloads++;
}, true);
const werteStand = () => {
  let s = "";
  const liste = document.querySelectorAll("input,select,textarea,[contenteditable=true],[contenteditable='']");
  for (let i = 0; i < liste.length && i < 1500; i++) {
    const el = liste[i];
    s += "|" + (el.type === "checkbox" || el.type === "radio" ? el.checked : (el.isContentEditable ? el.textContent : el.value));
  }
  return s;
};
const leereFelder = () => [...document.querySelectorAll("input,textarea")].slice(0, 1500)
  .filter((el) => !["checkbox", "radio", "button", "submit", "hidden"].includes((el.type || "").toLowerCase()) && !el.value).length;
const speicherObjekt = () => {
  try {
    const s = window.localStorage;
    if (s && typeof s.__werte === "function") return Object.assign({}, s.__werte());
  } catch (e) { /* kein Speicher */ }
  return {};
};
const sichtbarZahl = () => {
  let n = 0;
  const alle = document.querySelectorAll("body *");
  for (let i = 0; i < alle.length && i < 3000; i++) {
    const el = alle[i];
    if (el.checkVisibility ? el.checkVisibility() : el.getClientRects().length) n++;
  }
  return n;
};
const ortStand = () => location.hash + "|" + [...document.querySelectorAll(
  "[aria-selected=true],[aria-current]:not([aria-current=false]),[aria-expanded=true],.active,.is-active,.selected")]
  .slice(0, 40).map((el) => el.tagName + (el.id || String(el.textContent || "").slice(0, 16))).join(",");
const modalZahl = () => [...document.querySelectorAll("dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]")]
  .filter(sichtbar).length;
const stand = () => ({
  text: document.body ? document.body.innerText : "", werte: werteStand(), leer: leereFelder(),
  speicher: speicherObjekt(), sicht: sichtbarZahl(), ort: ortStand(), modal: modalZahl(),
  exporte: (J.exporte || []).length, downloads,
});
const geaenderteSchluessel = (a, b) => [...new Set([...Object.keys(a), ...Object.keys(b)])]
  .filter((k) => a[k] !== b[k]).slice(0, 6);

// Knöpfe drücken — zerstörerische (Zurücksetzen, Löschen) zuletzt.
const ZULETZT = /zurück|reset|lösch|leer|entfern|clear|delete|neu starten|abbrechen|schließen|export|download|herunterladen|drucken|print/i;
// Ein Knopf mit Symbol („i“, „×“, „▾“) heißt, was sein aria-label oder title sagt.
// Gefunden am 27.09.2026: Info-Knöpfe mit „i“ und aria-label „Info zur Übung“
// blieben für die Abnahme unsichtbar.
const beschriftung = (el) => {
  const text = String(el.innerText || el.value || "").replace(/\s+/g, " ").trim();
  const zusatz = String(el.getAttribute("aria-label") || el.title || "").trim();
  if (zusatz && text.length <= 2) return (zusatz + (text ? ` (${text})` : "")).slice(0, 60);
  return (text || zusatz).slice(0, 60);
};
// Aufklapper zählen mit: <summary> und alles mit aria-expanded.
const KNOPF_AUSWAHL = "button,input[type=button],input[type=submit],[role=button],summary,[aria-expanded]";
const aufklapper = (el) => el.tagName === "SUMMARY" || el.hasAttribute("aria-expanded");
const knopfListe = () => [...document.querySelectorAll(KNOPF_AUSWAHL)]
  .filter((el) => sichtbar(el) && !el.disabled && !(el.matches("[aria-expanded]") && el.closest("summary")));
// Was der Abnahmevertrag verlangt, kommt zuerst dran.
const FOKUS = (typeof __fokus !== "undefined" && Array.isArray(__fokus) ? __fokus : [])
  .map((w) => String(w).toLowerCase().trim()).filter((w) => w.length >= 3).map((w) => (w.length >= 7 ? w.slice(0, 6) : w));
const merkmale = (el) => (beschriftung(el) + " " + (el.getAttribute("aria-label") || "") + " " + (el.title || "") + " "
  + (typeof el.className === "string" ? el.className : "") + " " + (el.id || "") + " "
  + [...el.attributes].filter((a) => a.name.startsWith("data-")).map((a) => a.name).join(" ")).toLowerCase();
const imFokus = (el) => FOKUS.length > 0 && FOKUS.some((w) => merkmale(el).includes(w));
const sortiert = (liste) => [
  ...liste.filter((k) => imFokus(k) && !ZULETZT.test(beschriftung(k))),
  ...liste.filter((k) => !imFokus(k) && !ZULETZT.test(beschriftung(k))),
  ...liste.filter((k) => ZULETZT.test(beschriftung(k))),
];
// Zehn gleiche „+ hinzufügen“-Knöpfe beweisen nicht mehr als zwei davon.
const gleichartig = new Map();
const zeilenSatz = () => new Set((document.body ? document.body.innerText : "").split("\n").map((z) => z.trim()).filter(Boolean));
const knoepfe = knopfListe();
let geklickt = 0;
const fehlerJeKnopf = [];
const KAPUTT = /\bNaN\b|\bundefined\b|\[object Object\]/g;
const kaputt = [];
const kaputtPruefen = (wann) => {
  const text = document.body ? document.body.innerText : "";
  (text.match(KAPUTT) || []).slice(0, 2).forEach((wert) => { if (kaputt.length < 5) kaputt.push({ wert, wann }); });
};
kaputtPruefen("nach dem Ausfüllen");
// Jeder Klick wird für sich gemessen: „Zurücksetzen“ am Ende darf die
// Reaktion auf „Berechnen“ nicht wieder unsichtbar machen. In einem zweiten
// Durchgang kommen Knöpfe dran, die erst durch einen Klick erschienen sind
// (etwa „Als PDF speichern“ in einer geöffneten Maske).
let reaktionKlick = false;
let letzte = signatur();
const klicks = [];
// Größte Spiel-/Zeichenfläche — auch nach Klicks gemessen: Ein Spiel zeigt seine
// Fläche oft erst nach „Start“ (08.10.2026, Kolibri Jump: beim Laden lag das
// Startmenü obenauf, die Abnahme sah keinen Vollbild-Spielbereich).
const vollbildMessen = () => {
  let bestes = { breite: 0, hoehe: 0, element: "" };
  for (const el of document.querySelectorAll("canvas, svg, main, video, [id*='game' i], [id*='spiel' i], [class*='game' i], [class*='spiel' i]")) {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0) continue;
    const r = el.getBoundingClientRect();
    const b = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0)) / innerWidth * 100;
    const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0)) / innerHeight * 100;
    if (b * h > bestes.breite * bestes.hoehe) {
      bestes = { breite: Math.round(b), hoehe: Math.round(h), element: el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") };
    }
  }
  return bestes;
};
let vollbild = vollbildMessen();
const vollbildNachKlick = (knopfName) => {
  const jetzt = vollbildMessen();
  if (jetzt.breite * jetzt.hoehe > vollbild.breite * vollbild.hoehe) vollbild = { ...jetzt, nach: knopfName };
};
const erledigt = new Set();
const reihenfolge = [...sortiert(knoepfe), ...Array(30).fill(null)];
// Öffnet ein Klick eine Maske mit leeren Feldern („Route umplanen“ → Start,
// Ziel, „Route erzeugen“), füllt die Probe sie wie ein Mensch und klickt als
// Nächstes den neuen Knopf darin. Gefunden am 29.09.2026: Der Apple-Maps-Link
// entstand erst nach dem Bestätigen der Maske — die Probe ließ sie leer.
const nachgefuellt = new Set();
let folgeMasken = 0;
const ABBRUCH = /abbrech|schließ|schliess|zurück|cancel|close|×|✕/i;
const fuelleNeu = (el) => {
  const typ = (el.type || "").toLowerCase();
  if (["hidden", "file", "submit", "button", "reset", "image", "password", "checkbox", "radio"].includes(typ)) return false;
  const hinweis = `${el.name || ""} ${el.id || ""} ${el.placeholder || ""} ${(el.labels && el.labels[0] ? el.labels[0].textContent : "")}`;
  if (el.tagName === "SELECT") { if (el.options.length > 1 && el.selectedIndex <= 0) el.selectedIndex = 1; else return false; }
  else if (String(el.value || "").trim()) return false;
  else if (typ === "number" || typ === "range") el.value = el.min && !isNaN(parseFloat(el.min)) ? String(parseFloat(el.min) + 1) : "42";
  else if (typ === "date") el.value = "2026-09-19";
  else if (typ === "time") el.value = "09:30";
  else if (typ === "email") el.value = "test@example.com";
  else if (typ === "tel") el.value = "0123 456789";
  else if (typ === "url") el.value = "https://example.com";
  else if (/adress|straße|strasse|ort|ziel|start|anschrift|address|location/i.test(hinweis)) el.value = "Musterstraße 1, 10115 Berlin";
  else el.value = el.tagName === "TEXTAREA" ? "Testeintrag für die Prüfung" : "Test";
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
};
for (let stelle = 0; stelle < reihenfolge.length && geklickt < 30; stelle++) {
  let knopf = reihenfolge[stelle];
  if (knopf && knopf.folge) {
    const text = knopf.folge;
    knopf = knopfListe().find((k) => beschriftung(k) === text && !erledigt.has(k)) || null;
    if (!knopf) continue;
  } else if (knopf === null) {
    const nachzuegler = sortiert(knopfListe().filter((k) => !erledigt.has(k)));
    if (!nachzuegler.length) break;
    knopf = nachzuegler[0];
  }
  if (!knopf || erledigt.has(knopf)) continue;
  erledigt.add(knopf);
  if (!sichtbar(knopf) || knopf.disabled) continue;
  const art = beschriftung(knopf).toLowerCase().replace(/\d+/g, "#");
  gleichartig.set(art, (gleichartig.get(art) || 0) + 1);
  if (gleichartig.get(art) > 2) continue;
  const vorher = (J.fehler || []).length;
  const davor = oberflaeche();
  const vorStand = stand();
  const vorZeilen = zeilenSatz();
  const vorSignatur = signatur();
  // Nach Beschriftung und Feldname vergleichen: Viele Anwendungen zeichnen
  // nach jedem Klick alles neu, dann ist jedes Element „neu“.
  const feldKennung = (el) => `${el.tagName}|${el.id || el.name || ""}|${el.placeholder || ""}|${(el.labels && el.labels[0] ? el.labels[0].textContent : "").trim()}`;
  const vorKnoepfe = new Set(knopfListe().map((k) => beschriftung(k)));
  const vorFelder = new Set([...document.querySelectorAll("input,select,textarea")].filter(sichtbar).map(feldKennung));
  const name = beschriftung(knopf);
  const istAufklapper = aufklapper(knopf);
  try { knopf.click(); geklickt++; } catch (e) { /* Laufzeit */ }
  await warte(80);
  // Was der Klick sichtbar gemacht hat — etwa die aufgeklappte Beschreibung.
  const aufgedeckt = [...zeilenSatz()].filter((z) => !vorZeilen.has(z)).join(" · ").slice(0, 600);
  const danach = oberflaeche();
  const nachStand = stand();
  const jetzt = signatur();
  const neueTexte = [...danach.texte].filter((t) => !davor.texte.has(t)).slice(0, 10);
  const effekte = [];
  if (nachStand.text !== vorStand.text) effekte.push("text_changed");
  if (nachStand.werte !== vorStand.werte) effekte.push("value_changed");
  const schluessel = geaenderteSchluessel(vorStand.speicher, nachStand.speicher);
  if (schluessel.length) effekte.push("local_storage_changed");
  if (danach.felder > davor.felder || danach.knoepfe > davor.knoepfe || neueTexte.length) effekte.push("dom_added");
  if (nachStand.sicht > vorStand.sicht) effekte.push("element_shown");
  if (nachStand.sicht < vorStand.sicht) effekte.push("element_hidden");
  if (nachStand.ort !== vorStand.ort) effekte.push("route_changed");
  if (nachStand.modal > vorStand.modal) effekte.push("modal_opened");
  if (nachStand.exporte > vorStand.exporte) effekte.push("export_requested");
  if (nachStand.downloads > vorStand.downloads) effekte.push("download_triggered");
  if (jetzt !== letzte && !effekte.length) effekte.push("state_changed");
  if ((J.fehler || []).length > vorher) effekte.push("runtime_error");
  if (klicks.length < 30) {
    const eintrag = {
      knopf: name,
      effekte,
      // Neu sichtbare Zeilen: kurze Rückmeldungen wie „PDF wurde erstellt“
      // ebenso wie eine aufgeklappte Beschreibung.
      neuerText: aufgedeckt,
      neueFelder: danach.felder - davor.felder,
      neueKnoepfe: danach.knoepfe - davor.knoepfe,
      neueTexte,
      textZuwachs: danach.laenge - davor.laenge,
    };
    if (schluessel.length) eintrag.speicher = schluessel;
    if (nachStand.exporte > vorStand.exporte) eintrag.export = String((J.exporte || [])[nachStand.exporte - 1]?.typ || "");
    if (nachStand.leer > vorStand.leer) eintrag.geleert = nachStand.leer - vorStand.leer;
    if (istAufklapper) {
      // Ein Aufklapper muss auch wieder zuklappen: zweiter Klick, Vergleich mit vorher.
      eintrag.aufklapper = true;
      try { knopf.click(); } catch (e) { /* Laufzeit */ }
      await warte(80);
      eintrag.zurueck = signatur() === vorSignatur;
      const geoeffnet = effekte.some((e) => ["element_shown", "dom_added"].includes(e));
      if (eintrag.zurueck && (geoeffnet || effekte.includes("text_changed"))) effekte.push("toggled");
      // Was der erste Klick geöffnet hat, bleibt offen: Darin stecken oft die
      // nächsten Knöpfe (etwa „Info“ in aufgeklappten Karten).
      if (eintrag.zurueck && geoeffnet) {
        try { knopf.click(); } catch (e) { /* Laufzeit */ }
        await warte(80);
      }
    }
    if (imFokus(knopf)) eintrag.fokus = true;
    // Klassen und data-Attribute: „chip-info“ verrät einen Info-Knopf, auch wenn er nur „i“ zeigt.
    eintrag.merkmal = kurz((typeof knopf.className === "string" ? knopf.className : "") + " "
      + [...knopf.attributes].filter((a) => a.name.startsWith("data-")).map((a) => a.name.slice(5)).join(" "), 80);
    klicks.push(eintrag);
  }
  if (jetzt !== letzte) reaktionKlick = true;
  try { vollbildNachKlick(name); } catch (e) { /* Messung ist Beiwerk */ }
  letzte = signatur();
  if (!kaputt.length) kaputtPruefen(`nach Klick auf „${beschriftung(knopf)}“`);
  if (folgeMasken < 6) {
    const neueFelder = [...document.querySelectorAll("input,select,textarea")]
      .filter((el) => sichtbar(el) && !el.disabled && !el.readOnly && !vorFelder.has(feldKennung(el)) && !nachgefuellt.has(el));
    neueFelder.slice(0, 12).forEach((el) => { nachgefuellt.add(el); try { fuelleNeu(el); } catch (e) { /* Laufzeit */ } });
    if (neueFelder.length) await warte(80);
    const gesehen = new Set();
    const folge = knopfListe().filter((k) => {
      const text = beschriftung(k);
      if (vorKnoepfe.has(text) || gesehen.has(text) || ZULETZT.test(text) || ABBRUCH.test(text)) return false;
      gesehen.add(text);
      return true;
    }).slice(0, 3);
    if (folge.length && (neueFelder.length || folge.length <= 3)) {
      folgeMasken++;
      // Folgeknöpfe per Beschriftung merken: Nach dem nächsten Klick sind die
      // Elemente womöglich schon wieder neu gezeichnet.
      folge.reverse().forEach((k) => reihenfolge.splice(stelle + 1, 0, { folge: beschriftung(k) }));
    }
  }
  const neu = (J.fehler || []).slice(vorher);
  if (neu.length) fehlerJeKnopf.push({ knopf: beschriftung(knopf), fehler: neu.map((f) => f.text).slice(0, 2) });
}

return JSON.stringify({
  vorher: __vorher,
  interaktion: {
    felder: felder.length,
    gefuellt,
    knoepfe: Math.max(knoepfe.length, geklickt),   // auch später erschienene
    geklickt,
    zurueckgesetzt,
    reaktionEingabe: nachEingabe !== ausgangstext,
    reaktionKlick,
    fehlerJeKnopf,
    kaputteWerte: kaputt,
    klicks,
    vollbild,
  },
  fehler: (J.fehler || []),
  fehlerBeimLaden: fehlerVorher,
  dialoge: J.dialoge || [],
  // Was die Anwendung exportieren wollte — JOSHI erzeugt die Dateien danach
  // wirklich und weist die Ausgabe damit nach.
  exporte: (J.exporte || []).slice(0, 3),
});
