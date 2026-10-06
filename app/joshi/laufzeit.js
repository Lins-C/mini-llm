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
  var echtesBestaetigen = window.confirm ? window.confirm.bind(window) : null;
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
    if (!daten || daten.joshi !== 1) return;
    var offen = daten.art === "export-antwort" ? offeneAnfragen : daten.art === "ki-antwort" ? kiOffen : null;
    var erledigen = offen && offen[daten.anfrage];
    if (!erledigen) return;
    delete offen[daten.anfrage];
    erledigen(daten);
  });

  // ------------------------------------------------------- KI-Sprachmodell
  // Anwendungen mit Figuren, Chats oder Geschichten brauchen ein Sprachmodell.
  // Sie bekommen es über JOSHI, nie über eigene Netzwerkzugriffe:
  //   var a = await window.JOSHI.ki({ system: "…", messages: [{ role: "user", content: "…" }] });
  //   a.ok ? a.text : a.fehler
  // Vorschau: Mini LLM fragt den Nutzer einmal um Erlaubnis und nutzt sein
  // gewähltes Modell — Zugangsdaten bleiben auf dem Server.
  // Prüfung: feste Testantwort, damit die Abnahme ohne Modell durchläuft.
  // Export: direkt das lokale Ollama dieses Rechners (nach Rückfrage); die
  // Sicherheitsrichtlinie gibt dafür nur localhost:11434 frei.
  var kiOffen = {};
  var OLLAMA = "http://localhost:11434";
  var KI_ROLLEN = { system: 1, user: 1, assistant: 1 };

  function kiNachrichten(auftrag) {
    var liste = [];
    if (auftrag.system) liste.push({ role: "system", content: String(auftrag.system) });
    (Array.isArray(auftrag.messages) ? auftrag.messages : []).forEach(function (n) {
      if (n && KI_ROLLEN[n.role] && n.content != null) {
        liste.push({ role: n.role, content: typeof n.content === "string" ? n.content : JSON.stringify(n.content) });
      }
    });
    if (auftrag.prompt) liste.push({ role: "user", content: String(auftrag.prompt) });
    return liste.slice(-60);
  }

  function kiPruefantwort(auftrag) {
    var json = auftrag.format === "json" || /\bjson\b/i.test(JSON.stringify(auftrag.messages || auftrag.prompt || "").slice(-2000));
    return json ? "{}" : "Testantwort der JOSHI-Prüfung: Hier antwortet später das gewählte KI-Modell.";
  }

  // Beim Empfänger: JOSHI wählt und zeigt das Modell selbst — die Anwendung
  // baut keine eigene Modellauswahl (sonst Attrappe ohne Wirkung).
  var KI_WAHL = "joshi-ki-modell";
  function merken(schluessel, wert) { try { localStorage.setItem(schluessel, wert); } catch (e) {} }
  function gemerkt(schluessel) { try { return localStorage.getItem(schluessel) || ""; } catch (e) { return ""; } }
  function istCloud(name) { return /(^|[:-])cloud\b/.test(name); }

  function installierteModelle() {
    return (echtesHolen || window.fetch)(OLLAMA + "/api/tags").then(function (r) { return r.json(); })
      .then(function (d) {
        var namen = (d.models || []).map(function (m) { return m.name || m.model; }).filter(Boolean);
        // Lokale Modelle zuerst: sie brauchen weder Konto noch Internet.
        return namen.filter(function (n) { return !istCloud(n); }).concat(namen.filter(istCloud));
      });
  }

  function modellBestimmen(gewuenscht) {
    return installierteModelle().then(function (liste) {
      if (!liste.length) throw new Error("In Ollama ist noch kein Modell geladen – bitte in der Ollama-App eins laden.");
      var wahl = gemerkt(KI_WAHL);
      if (wahl && liste.indexOf(wahl) >= 0) return wahl;
      if (gewuenscht && liste.indexOf(gewuenscht) >= 0) return gewuenscht;
      return liste[0];
    });
  }

  function kiErlaubtExport(modell) {
    var schluessel = "joshi-ki-erlaubt:" + (K.schluessel || location.pathname);
    if (gemerkt(schluessel) === "ja") return true;
    var ja = echtesBestaetigen ? echtesBestaetigen(
      "Diese Anwendung möchte das KI-Modell auf diesem Rechner nutzen (Ollama).\n\n"
      + "Modell: " + modell + (istCloud(modell) ? " (Cloud-Modell von Ollama)" : " (läuft lokal)") + "\n"
      + "Angesprochen wird nur http://localhost:11434. Das Modell lässt sich unten links jederzeit wechseln.\n\nErlauben?") : false;
    if (ja) merken(schluessel, "ja");
    return ja;
  }

  var plakette = null;
  function plaketteZeigen(modell) {
    if (!document.body) return;
    if (!plakette) {
      plakette = document.createElement("button");
      plakette.type = "button";
      plakette.title = "KI-Modell wechseln";
      plakette.setAttribute("style", "position:fixed;left:12px;bottom:12px;z-index:2147483646;padding:5px 10px;"
        + "border:1px solid rgba(127,127,127,.4);border-radius:999px;background:rgba(17,24,39,.88);color:#e5e7eb;"
        + "font:12px/1.3 system-ui,-apple-system,sans-serif;cursor:pointer;max-width:70vw;overflow:hidden;"
        + "text-overflow:ellipsis;white-space:nowrap;");
      plakette.addEventListener("click", modellWaehlen);
      document.body.appendChild(plakette);
    }
    plakette.textContent = "KI: " + modell + " ▾";
  }

  function modellWaehlen() {
    installierteModelle().then(function (liste) {
      var alt = document.getElementById("joshi-ki-wahl");
      if (alt) { alt.remove(); return; }
      var feld = document.createElement("select");
      feld.id = "joshi-ki-wahl";
      feld.setAttribute("aria-label", "KI-Modell");
      feld.setAttribute("style", "position:fixed;left:12px;bottom:46px;z-index:2147483647;max-width:80vw;"
        + "padding:6px;border-radius:8px;font:13px system-ui,-apple-system,sans-serif;");
      feld.size = Math.min(8, Math.max(2, liste.length));
      var aktiv = gemerkt(KI_WAHL);
      liste.forEach(function (name) {
        var option = document.createElement("option");
        option.value = name;
        option.textContent = name + (istCloud(name) ? "  (Cloud)" : "  (lokal)");
        option.selected = name === aktiv;
        feld.appendChild(option);
      });
      feld.addEventListener("change", function () {
        merken(KI_WAHL, feld.value);
        plaketteZeigen(feld.value);
        zeigen("KI-Modell: " + feld.value);
        feld.remove();
      });
      document.body.appendChild(feld);
      feld.focus();
    }).catch(function () { zeigen("Ollama ist nicht erreichbar."); });
  }

  // Direkt geöffnete Datei: Ollama lehnt die Herkunft „null“ ab. Einmal pro
  // Seitenaufruf erklärt JOSHI die zwei Wege, mit Kopierknopf für den Befehl.
  var anleitungGezeigt = false;
  function dateiAnleitung() {
    if (anleitungGezeigt || !document.body) return;
    anleitungGezeigt = true;
    var mac = /Mac/i.test(navigator.platform || navigator.userAgent);
    var befehl = mac ? 'launchctl setenv OLLAMA_ORIGINS "null"' : "setx OLLAMA_ORIGINS null";
    var kasten = document.createElement("div");
    kasten.setAttribute("role", "dialog");
    kasten.setAttribute("style", "position:fixed;inset:auto 12px 12px 12px;margin:auto;max-width:560px;z-index:2147483647;"
      + "padding:16px 18px;border-radius:14px;background:#111827;color:#f3f4f6;box-shadow:0 12px 40px rgba(0,0,0,.45);"
      + "font:14px/1.5 system-ui,-apple-system,sans-serif;");
    function absatz(text, stil) {
      var p = document.createElement("p");
      p.textContent = text;
      p.setAttribute("style", "margin:0 0 8px;" + (stil || ""));
      kasten.appendChild(p);
      return p;
    }
    absatz("KI-Funktion: So verbindest du die Anwendung mit Ollama", "font-weight:700;font-size:15px");
    absatz("Diese Datei wurde direkt geöffnet. Aus Sicherheitsgründen lässt Ollama das ab Werk nicht zu.");
    absatz("Empfohlen: Die Anwendung über „Starten (Mac).command“ bzw. „Starten (Windows).bat“ aus dem ZIP öffnen (siehe LIESMICH.txt).");
    absatz("Oder einmalig Ollama für geöffnete Dateien freischalten – dann darf allerdings jede geöffnete HTML-Datei Ollama nutzen. "
      + (mac ? "Befehl im Terminal ausführen, danach Ollama beenden und neu starten (gilt bis zum nächsten Neustart des Macs):"
             : "Befehl in der Eingabeaufforderung ausführen, danach Ollama neu starten:"));
    var code = absatz(befehl, "font-family:ui-monospace,Menlo,monospace;background:#1f2937;padding:8px 10px;border-radius:8px;user-select:all");
    var zeile = document.createElement("div");
    zeile.setAttribute("style", "display:flex;gap:8px;justify-content:flex-end;margin-top:6px");
    function knopf(text, aktion) {
      var b = document.createElement("button");
      b.type = "button";
      b.textContent = text;
      b.setAttribute("style", "padding:7px 12px;border-radius:8px;border:1px solid #4b5563;background:#1f2937;color:#f3f4f6;cursor:pointer;font:inherit");
      b.addEventListener("click", aktion);
      zeile.appendChild(b);
    }
    knopf("Befehl kopieren", function () {
      var fertig = function () { zeigen("Befehl kopiert."); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(befehl).then(fertig, function () { auswaehlen(code); });
      } else { auswaehlen(code); }
    });
    knopf("Schließen", function () { kasten.remove(); });
    kasten.appendChild(zeile);
    document.body.appendChild(kasten);
  }
  function auswaehlen(knoten) {
    try {
      var bereich = document.createRange();
      bereich.selectNodeContents(knoten);
      var auswahl = window.getSelection();
      auswahl.removeAllRanges();
      auswahl.addRange(bereich);
      zeigen("Befehl markiert – mit Cmd/Strg+C kopieren.");
    } catch (e) {}
  }

  function kiDirekt(auftrag, nachrichten) {
    var holen = echtesHolen || window.fetch;
    var gewuenscht = auftrag.model || auftrag.modell;
    return modellBestimmen(gewuenscht === "joshi" ? "" : gewuenscht).then(function (modell) {
      if (!kiErlaubtExport(modell)) return { ok: false, fehler: "Die Nutzung des KI-Modells wurde nicht erlaubt." };
      plaketteZeigen(modell);
      return holen(OLLAMA + "/api/chat", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: modell, messages: nachrichten, stream: false,
          format: auftrag.format === "json" ? "json" : undefined,
          options: auftrag.temperature != null ? { temperature: auftrag.temperature } : undefined })
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d.error) return { ok: false, fehler: String(d.error), modell: modell };
        return { ok: true, text: (d.message && d.message.content) || "", modell: modell };
      });
    }).catch(function (fehler) {
      // Browser melden geöffnete Dateien mit der Herkunft „null“; die lässt
      // Ollama nur zu, wenn OLLAMA_ORIGINS sie ausdrücklich erlaubt.
      if (location.protocol === "file:" || location.origin === "null") {
        dateiAnleitung();
        return { ok: false, fehler: "Die KI-Funktion ist noch nicht mit Ollama verbunden – siehe Hinweis unten." };
      }
      return { ok: false, fehler: "Ollama ist auf diesem Rechner nicht erreichbar (" + (fehler && fehler.message || fehler) + "). "
        + "Läuft Ollama und ist ein Modell geladen (in der Ollama-App)?" };
    });
  }

  function ki(auftrag) {
    auftrag = auftrag && typeof auftrag === "object" ? auftrag : { prompt: String(auftrag || "") };
    var nachrichten = kiNachrichten(auftrag);
    if (!nachrichten.length) return Promise.resolve({ ok: false, fehler: "Die KI-Anfrage ist leer." });
    if (modus === "pruefung") return Promise.resolve({ ok: true, text: kiPruefantwort(auftrag), modell: "pruefung", test: true });
    if (modus === "export") return kiDirekt(auftrag, nachrichten);
    var anfrage = kennung();
    return new Promise(function (fertig) {
      var uhr = setTimeout(function () {
        delete kiOffen[anfrage];
        fertig({ ok: false, fehler: "Das KI-Modell hat nicht rechtzeitig geantwortet." });
      }, 300000);
      kiOffen[anfrage] = function (antwort) {
        clearTimeout(uhr);
        fertig(antwort.ok ? { ok: true, text: String(antwort.text || ""), modell: antwort.modell || "" }
                          : { ok: false, fehler: antwort.fehler || "Das KI-Modell ist nicht erreichbar." });
      };
      melden("ki", { anfrage: anfrage, nachrichten: nachrichten, format: auftrag.format === "json" ? "json" : "",
                     temperatur: typeof auftrag.temperature === "number" ? auftrag.temperature : null });
    });
  }

  // Vorhandener Code spricht Ollama oder eine OpenAI-kompatible API oft direkt
  // an. Diese Aufrufe leitet JOSHI auf ki() um — ohne API-Schlüssel, ohne Netz.
  var echtesHolen = window.fetch ? window.fetch.bind(window) : null;
  function kiZiel(adresse) {
    var u;
    try { u = new URL(String(adresse), location.href); } catch (e) { return null; }
    var lokal = /^(localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\])$/.test(u.hostname) && u.port === "11434";
    if (/\/api\/tags$/.test(u.pathname) && lokal) return { art: "tags", lokal: true };
    if (/\/api\/(generate|chat)$/.test(u.pathname)) return { art: "ollama", lokal: lokal };
    if (/\/chat\/completions$/.test(u.pathname)) return { art: "openai", lokal: lokal };
    return null;
  }
  function antwort(daten, status, art) {
    return new Response(art || JSON.stringify(daten), {
      status: status || 200, headers: { "Content-Type": art ? "text/event-stream" : "application/json" } });
  }
  if (echtesHolen) {
    window.fetch = function (adresse, optionen) {
      var url = adresse && adresse.url ? adresse.url : adresse;
      var treffer = kiZiel(url);
      // Modellliste darf die Anwendung im Export echt lesen; Anfragen laufen immer
      // über ki(), damit JOSHIs Modellwahl, Rückfrage und Anzeige gelten.
      if (!treffer || (modus === "export" && treffer.art === "tags")) return echtesHolen(adresse, optionen);
      var ziel = treffer.art;
      if (ziel === "tags") return Promise.resolve(antwort({ models: [{ name: "joshi", model: "joshi" }] }));
      var koerper = {};
      try { koerper = JSON.parse(optionen && optionen.body || "{}"); } catch (e) {}
      var pfad = String(url);
      var auftrag = { system: koerper.system, messages: koerper.messages, prompt: koerper.prompt,
                      model: treffer.art === "ollama" ? koerper.model : "",
                      format: koerper.format === "json" || (koerper.response_format && koerper.response_format.type === "json_object") ? "json" : "",
                      temperature: koerper.temperature != null ? koerper.temperature : koerper.options && koerper.options.temperature };
      return ki(auftrag).then(function (a) {
        if (!a.ok) return antwort({ error: a.fehler }, 503);
        if (ziel === "openai") {
          if (koerper.stream) {
            return antwort(null, 200, "data: " + JSON.stringify({ choices: [{ index: 0, delta: { role: "assistant", content: a.text } }] })
              + "\n\ndata: " + JSON.stringify({ choices: [{ index: 0, delta: {}, finish_reason: "stop" }] }) + "\n\ndata: [DONE]\n\n");
          }
          return antwort({ object: "chat.completion", model: a.modell,
                           choices: [{ index: 0, message: { role: "assistant", content: a.text }, finish_reason: "stop" }] });
        }
        return antwort(/\/api\/generate$/.test(pfad)
          ? { model: a.modell, response: a.text, done: true }
          : { model: a.modell, message: { role: "assistant", content: a.text }, done: true });
      });
    };
  }

  window.JOSHI = { version: 1, formate: ERLAUBT.slice(), export: exportieren, ki: ki };
  var druckenEcht = window.print ? window.print.bind(window) : null;
  if (modus !== "export") {
    // Ältere Anwendungen drucken selbst; im Sandkasten verpufft das. Daraus
    // wird ein echter PDF-Export der ganzen Anwendung.
    window.print = function () { exportieren({ type: "pdf" }); };
  }

  melden("bereit", { modus: modus, joshi: 1 });
  window.addEventListener("load", function () { melden("geladen", { fehler: fehler.length }); });
})();
