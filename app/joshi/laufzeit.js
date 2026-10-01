// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
/* JOSHI-Laufzeit: läuft als erstes Skript in jedem JOSHI-Produkt.
 *
 * Dieselbe Vorrede steckt in der Vorschau (Sandkasten-iframe), in der Prüfung
 * (WebKit-Renderer auf dem Mac) und im exportierten HTML. Sie
 *  - sammelt JavaScript-Fehler, statt die Seite still sterben zu lassen,
 *  - ersetzt im Sandkasten den gesperrten localStorage,
 *  - merkt sich Formularwerte und stellt sie beim Öffnen wieder her,
 *  - zeigt alert() im Seiteninhalt (im Sandkasten verpufft es sonst),
 *  - verhindert, dass ein Formular die Seite wegnavigiert.
 * Konfiguration: window.__JOSHI__ = {modus, zustand, schluessel}.
 */
(function () {
  "use strict";
  var K = window.__JOSHI__ || {};
  var modus = K.modus || "vorschau";          // vorschau | pruefung | export
  var start = K.zustand && typeof K.zustand === "object" ? K.zustand : {};
  var startFelder = start.felder && typeof start.felder === "object" ? start.felder : {};
  var startSpeicher = start.speicher && typeof start.speicher === "object" ? start.speicher : {};
  var fehler = [];
  var dialoge = [];
  var joshi = { fehler: fehler, dialoge: dialoge, modus: modus };
  window.__joshi = joshi;

  function melden(art, daten) {
    if (modus !== "vorschau") return;
    try { parent.postMessage({ joshi: 1, art: art, daten: daten }, "*"); } catch (e) {}
  }

  // ---------------------------------------------------------------- Fehler
  function fehlerMerken(text, zeile, quelle) {
    var eintrag = { text: String(text || "Unbekannter Fehler").slice(0, 400), zeile: zeile || 0, quelle: quelle || "" };
    if (fehler.length < 30) fehler.push(eintrag);
    melden("fehler", eintrag);
  }
  window.addEventListener("error", function (e) {
    if (e && e.target && e.target !== window && e.target.tagName) {
      var ziel = e.target.getAttribute && (e.target.getAttribute("src") || e.target.getAttribute("href")) || "";
      fehlerMerken("Datei nicht ladbar: <" + e.target.tagName.toLowerCase() + "> " + String(ziel).slice(0, 120), 0, "ressource");
      return;
    }
    fehlerMerken(e && (e.message || (e.error && e.error.message)), e && e.lineno, "skript");
  }, true);
  window.addEventListener("unhandledrejection", function (e) {
    var grund = e && e.reason && e.reason.message ? e.reason.message : String(e && e.reason);
    fehlerMerken("Nicht behandelter Fehler: " + grund, 0, "promise");
  });
  var ursprungFehler = console.error;
  console.error = function () {
    try {
      var teile = [];
      for (var i = 0; i < arguments.length; i++) {
        var a = arguments[i];
        teile.push(a && a.message ? a.message : String(a));
      }
      fehlerMerken("console.error: " + teile.join(" "), 0, "konsole");
    } catch (e) {}
    return ursprungFehler.apply(console, arguments);
  };

  // --------------------------------------------------------------- Speicher
  function ersatzSpeicher(saat, meldend) {
    var werte = {};
    Object.keys(saat || {}).forEach(function (k) { werte[k] = String(saat[k]); });
    var api = {
      getItem: function (k) { k = String(k); return Object.prototype.hasOwnProperty.call(werte, k) ? werte[k] : null; },
      setItem: function (k, v) { werte[String(k)] = String(v); if (meldend) geaendert(); },
      removeItem: function (k) { delete werte[String(k)]; if (meldend) geaendert(); },
      clear: function () { werte = {}; if (meldend) geaendert(); },
      key: function (i) { var s = Object.keys(werte); return i < s.length ? s[i] : null; },
      __werte: function () { return werte; }
    };
    Object.defineProperty(api, "length", { get: function () { return Object.keys(werte).length; } });
    return api;
  }
  var speicher = null;
  var echterSpeicher = null;
  try { echterSpeicher = window.localStorage; echterSpeicher.getItem("__joshi"); } catch (e) { echterSpeicher = null; }
  if (modus === "export" && echterSpeicher) {
    // Beim Empfänger zählt beim ersten Öffnen der mitgeschickte Stand, danach
    // bleiben seine eigenen Änderungen erhalten.
    var marke = "__joshi_saat_" + (K.schluessel || "produkt");
    try {
      if (!echterSpeicher.getItem(marke)) {
        Object.keys(startSpeicher).forEach(function (k) { echterSpeicher.setItem(k, String(startSpeicher[k])); });
        echterSpeicher.setItem(marke, "1");
      } else {
        startFelder = {};
      }
    } catch (e) {}
  } else {
    speicher = ersatzSpeicher(startSpeicher, true);
    try {
      Object.defineProperty(window, "localStorage", { value: speicher, configurable: true });
      Object.defineProperty(window, "sessionStorage", { value: ersatzSpeicher({}, false), configurable: true });
    } catch (e) {}
  }

  // ----------------------------------------------------------- Formularwerte
  function schluesselVon(el) {
    if (!el || !el.tagName) return "";
    var tag = el.tagName.toLowerCase();
    if (tag !== "input" && tag !== "select" && tag !== "textarea") return "";
    var typ = (el.type || "").toLowerCase();
    if (typ === "password" || typ === "file" || typ === "hidden" || typ === "submit" || typ === "button" || typ === "reset") return "";
    if (el.id) return "#" + el.id;
    if (el.name) {
      var gleiche = document.getElementsByName(el.name);
      for (var i = 0; i < gleiche.length; i++) if (gleiche[i] === el) return "name:" + el.name + "[" + i + "]";
    }
    return "";
  }
  function wertVon(el) {
    var typ = (el.type || "").toLowerCase();
    if (typ === "checkbox" || typ === "radio") return !!el.checked;
    if (el.tagName.toLowerCase() === "select" && el.multiple) {
      var liste = [];
      for (var i = 0; i < el.options.length; i++) if (el.options[i].selected) liste.push(el.options[i].value);
      return liste;
    }
    return String(el.value == null ? "" : el.value).slice(0, 5000);
  }
  function wertSetzen(el, wert) {
    var typ = (el.type || "").toLowerCase();
    try {
      if (typ === "checkbox" || typ === "radio") { el.checked = !!wert; return; }
      if (el.tagName.toLowerCase() === "select" && el.multiple && Array.isArray(wert)) {
        for (var i = 0; i < el.options.length; i++) el.options[i].selected = wert.indexOf(el.options[i].value) >= 0;
        return;
      }
      el.value = String(wert);
    } catch (e) {}
  }
  var wiederhergestellt = {};
  function wiederherstellen(el) {
    var s = schluesselVon(el);
    if (!s || wiederhergestellt[s] || !Object.prototype.hasOwnProperty.call(startFelder, s)) return false;
    wiederhergestellt[s] = true;
    wertSetzen(el, startFelder[s]);
    return true;
  }
  function durchsuchen(knoten) {
    if (!knoten || knoten.nodeType !== 1) return;
    wiederherstellen(knoten);
    if (knoten.querySelectorAll) {
      var felder = knoten.querySelectorAll("input,select,textarea");
      for (var i = 0; i < felder.length; i++) wiederherstellen(felder[i]);
    }
  }
  // Werte setzen, sobald der Parser ein Feld anlegt — also noch bevor das
  // Skript der Anwendung zum ersten Mal rechnet.
  var beobachter = null;
  if (Object.keys(startFelder).length && window.MutationObserver) {
    beobachter = new MutationObserver(function (liste) {
      liste.forEach(function (m) { for (var i = 0; i < m.addedNodes.length; i++) durchsuchen(m.addedNodes[i]); });
    });
    beobachter.observe(document.documentElement, { childList: true, subtree: true });
  }
  document.addEventListener("DOMContentLoaded", function () {
    if (beobachter) { beobachter.disconnect(); beobachter = null; }
    var nachgeholt = [];
    var felder = document.querySelectorAll("input,select,textarea");
    for (var i = 0; i < felder.length; i++) if (wiederherstellen(felder[i])) nachgeholt.push(felder[i]);
    // Felder, die erst das Skript angelegt hat: Werte setzen und die
    // Anwendung wie bei einer Eingabe neu rechnen lassen.
    nachgeholt.forEach(function (el) {
      try {
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
      } catch (e) {}
    });
  });

  function zustand() {
    var felder = {};
    try {
      var liste = document.querySelectorAll("input,select,textarea");
      for (var i = 0; i < liste.length && i < 400; i++) {
        var s = schluesselVon(liste[i]);
        if (s) felder[s] = wertVon(liste[i]);
      }
    } catch (e) {}
    var werte = {};
    try {
      if (speicher) werte = speicher.__werte();
      else if (echterSpeicher) {
        for (var j = 0; j < echterSpeicher.length && j < 200; j++) {
          var k = echterSpeicher.key(j);
          if (k && k.indexOf("__joshi") !== 0) werte[k] = echterSpeicher.getItem(k);
        }
      }
    } catch (e) {}
    return { v: 1, felder: felder, speicher: werte };
  }
  joshi.zustand = zustand;

  var uhr = null;
  function geaendert() {
    if (modus !== "vorschau") return;
    clearTimeout(uhr);
    uhr = setTimeout(function () { melden("zustand", zustand()); }, 450);
  }
  document.addEventListener("input", geaendert, true);
  document.addEventListener("change", geaendert, true);

  // -------------------------------------------------------- Dialoge, Formulare
  var leiste = null;
  function zeigen(text) {
    function bauen() {
      if (!leiste) {
        leiste = document.createElement("div");
        leiste.setAttribute("role", "status");
        leiste.setAttribute("style", "position:fixed;left:50%;bottom:16px;transform:translateX(-50%);z-index:2147483647;"
          + "max-width:min(92vw,560px);padding:10px 14px;border-radius:10px;background:#111827;color:#fff;"
          + "font:14px/1.45 system-ui,-apple-system,sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.25);");
        document.body.appendChild(leiste);
      }
      leiste.textContent = text;
      leiste.style.display = "block";
      clearTimeout(leiste.uhr);
      leiste.uhr = setTimeout(function () { leiste.style.display = "none"; }, 4200);
    }
    if (document.body) bauen(); else document.addEventListener("DOMContentLoaded", bauen, { once: true });
  }
  window.alert = function (text) { dialoge.push(String(text).slice(0, 200)); zeigen(String(text)); };
  window.confirm = function (text) { dialoge.push(String(text).slice(0, 200)); return true; };
  window.prompt = function (text, vorgabe) { dialoge.push(String(text).slice(0, 200)); return vorgabe == null ? "" : String(vorgabe); };
  document.addEventListener("submit", function (e) { e.preventDefault(); }, true);

  // ------------------------------------------------- Dokumente exportieren
  // Die Anwendung darf selbst nichts Privilegiertes tun. Sie beschreibt nur,
  // was exportiert werden soll; JOSHI führt es aus und liefert die Datei.
  //   await window.JOSHI.export({ type: "pdf", target: "#angebot", filename: "angebot.pdf" })
  var ERLAUBT = ["pdf", "docx", "png", "jpg"];
  var MAX_HTML = 900000;
  var offeneAnfragen = {};
  var exporte = [];
  joshi.exporte = exporte;

  function abschnitt(ziel) {
    var knoten = ziel ? document.querySelector(ziel) : (document.body || null);
    if (!knoten) return null;
    var stile = [];
    var quellen = document.querySelectorAll("style");
    for (var i = 0; i < quellen.length; i++) stile.push(quellen[i].textContent || "");
    return { html: String(knoten.outerHTML || "").slice(0, MAX_HTML), css: stile.join("\n").slice(0, MAX_HTML) };
  }

  function kennung() {
    return "a" + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
  }

  function exportieren(wunsch) {
    wunsch = wunsch || {};
    var typ = String(wunsch.type || wunsch.typ || "pdf").toLowerCase().replace("jpeg", "jpg");
    var ziel = String(wunsch.target || wunsch.ziel || "");
    var dateiname = String(wunsch.filename || wunsch.dateiname || "");
    var titel = String(wunsch.title || wunsch.titel || document.title || "");
    if (ERLAUBT.indexOf(typ) < 0) {
      return Promise.resolve({ ok: false, error: "Diesen Exporttyp gibt es nicht: " + typ });
    }
    var inhalt = null;
    try { inhalt = abschnitt(ziel); } catch (e) { inhalt = null; }
    if (!inhalt) {
      return Promise.resolve({ ok: false, error: ziel ? "Der Bereich " + ziel + " wurde nicht gefunden." : "Nichts zu exportieren." });
    }
    var anfrage = kennung();
    var auftrag = { anfrage: anfrage, typ: typ, ziel: ziel, dateiname: dateiname, titel: titel,
                    html: inhalt.html, css: inhalt.css };
    if (modus === "pruefung") {
      // In der Prüfung wird der Wunsch aufgezeichnet; JOSHI erzeugt die Datei
      // danach wirklich und weist die Ausgabe so nach.
      if (exporte.length < 4) exporte.push(auftrag);
      return Promise.resolve({ ok: true, filename: dateiname || typ, request_id: anfrage });
    }
    if (modus === "export") {
      if (typ === "pdf" && typeof druckenEcht === "function") {
        try { druckenEcht(); return Promise.resolve({ ok: true, filename: dateiname || "" }); } catch (e) {}
      }
      return Promise.resolve({ ok: false, error: "Dieser Export steht nur in JOSHI zur Verfügung." });
    }
    zeigen((typ === "docx" ? "Word-Datei" : typ.toUpperCase()) + " wird erstellt …");
    return new Promise(function (fertig) {
      var uhr = setTimeout(function () {
        delete offeneAnfragen[anfrage];
        fertig({ ok: false, error: "Der Export hat zu lange gedauert." });
      }, 120000);
      offeneAnfragen[anfrage] = function (antwort) {
        clearTimeout(uhr);
        zeigen(antwort.ok ? (antwort.dateiname || "Datei") + " wurde erstellt."
                          : (antwort.fehler || "Der Export hat nicht geklappt."));
        fertig(antwort.ok ? { ok: true, filename: antwort.dateiname, request_id: anfrage }
                          : { ok: false, error: antwort.fehler || "Export fehlgeschlagen.", request_id: anfrage });
      };
      melden("export", auftrag);
    });
  }

  window.addEventListener("message", function (e) {
    if (e.source !== window.parent) return;
    var daten = e.data;
    if (!daten || daten.joshi !== 1 || daten.art !== "export-antwort") return;
    var erledigen = offeneAnfragen[daten.anfrage];
    if (!erledigen) return;
    delete offeneAnfragen[daten.anfrage];
    erledigen(daten);
  });

  window.JOSHI = { version: 1, formate: ERLAUBT.slice(), export: exportieren };
  var druckenEcht = window.print ? window.print.bind(window) : null;
  if (modus !== "export") {
    // Ältere Anwendungen drucken selbst; im Sandkasten verpufft das. Daraus
    // wird ein echter PDF-Export der ganzen Anwendung.
    window.print = function () { exportieren({ type: "pdf" }); };
  }

  melden("bereit", { modus: modus, joshi: 1 });
  window.addEventListener("load", function () { melden("geladen", { fehler: fehler.length }); });
})();
