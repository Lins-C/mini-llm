// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
/* JOSHI – Just On-demand Software from Human Intent.
 *
 * Eigene Arbeitsfläche innerhalb von Mini LLM. Der Chat bleibt darunter
 * bestehen; die Ansicht wird nur ein- und ausgeblendet. Aufträge laufen auf
 * dem Mac mini weiter, egal ob hier jemand zusieht – diese Datei hört nur zu.
 *
 * Die fertige Anwendung läuft in einem Sandkasten-iframe (allow-scripts ohne
 * eigene Herkunft): kein Zugriff auf Mini LLM, Sitzung oder Netz.
 */
(() => {
  const $$ = (auswahl) => document.querySelector(auswahl);
  const ansicht = $$("#joshi-view");
  if (!ansicht) return;

  const LETZTES_PRODUKT = "mini-llm-joshi-produkt";
  const GERAETE = { desktop: "100%", tablet: "820px", phone: "390px" };
  const SCHRITT_ZEICHEN = { offen: "○", aktiv: "●", fertig: "✓", fehler: "✕", reparatur: "↻", unbewiesen: "?" };
  // Die Pipeline verwendet englische, persistierbare Zustände. Die Oberfläche
  // hält sie getrennt von ihren bisherigen globalen Phasen (verstehen,
  // erstellen, prüfen), damit Schritt 1 nicht als aktuell aussieht, während
  // Schritt 2 schon generiert oder geprüft wird.
  const STUFEN_ZUSTAENDE = Object.freeze({
    planned: { anzeige: "offen", text: "Geplant" },
    generating: { anzeige: "aktiv", text: "Änderung wird erstellt …" },
    connecting: { anzeige: "aktiv", text: "Laufzeit wird verbunden …" },
    validating: { anzeige: "aktiv", text: "Änderung wird geprüft …" },
    repairing: { anzeige: "reparatur", text: "Änderung wird repariert …" },
    passed: { anzeige: "fertig", text: "geprüft · Checkpoint gespeichert" },
    failed: { anzeige: "fehler", text: "Nicht umgesetzt" },
    not_proven: { anzeige: "unbewiesen", text: "Nicht nachweisbar" },
    aborted: { anzeige: "fehler", text: "Abgebrochen" },
    deferred: { anzeige: "offen", text: "Zurückgestellt" },
  });
  const AKTIVE_STUFEN = new Set(["generating", "connecting", "validating", "repairing"]);
  const STATUSTEXT = {
    draft: "Entwurf", building: "JOSHI arbeitet", ready: "Bereit",
    needs_attention: "Mit Einschränkungen", failed: "Nicht erstellt",
  };

  const zustand = {
    produkte: [],
    aktuell: localStorage.getItem(LETZTES_PRODUKT) || "",
    daten: null,
    live: null,            // { jobId, produktId, schritte, stufen, fortschritt, hinweise, technik }
    leser: null,
    anhaenge: [],
    geraet: "desktop",
    vorschau: { produkt: "", version: 0 },
    laufzeitFehler: [],
    zustandUhr: null,
    zustandOffen: null,
    statusUhr: null,
    fertigSeitAbwesenheit: false,
    bereich: "stage",
  };

  const knoten = {
    oeffnen: $$("#joshi-open"),
    oeffnenText: $$("#joshi-open-label"),
    oeffnenPunkt: $$("#joshi-open-status"),
    zurueck: $$("#joshi-back"),
    produkteKnopf: $$("#joshi-products-toggle"),
    produkte: $$("#joshi-products"),
    produkteSchleier: $$("#joshi-products-scrim"),
    liste: $$("#joshi-product-list"),
    nebenanzeigen: $$("#joshi-nebenanzeigen"),
    neu: $$("#joshi-new"),
    modell: $$("#joshi-model"),
    feed: $$("#joshi-feed"),
    form: $$("#joshi-form"),
    eingabe: $$("#joshi-prompt"),
    senden: $$("#joshi-send"),
    dateiEingabe: $$("#joshi-file-input"),
    anhangKnopf: $$("#joshi-attach"),
    webKnopf: $$("#joshi-web"),
    webInfo: $$("#joshi-web-info"),
    anhangListe: $$("#joshi-attachments"),
    ablage: $$("#joshi-drop"),
    hinweis: $$("#joshi-hint"),
    titel: $$("#joshi-title"),
    version: $$("#joshi-version"),
    status: $$("#joshi-state"),
    rueckgaengig: $$("#joshi-undo"),
    exportKnopf: $$("#joshi-export-toggle"),
    exportMenue: $$("#joshi-export-menu"),
    teilenKnopf: $$("#joshi-share-toggle"),
    teilenMenue: $$("#joshi-share-menu"),
    besprechen: $$("#joshi-discuss"),
    mehrKnopf: $$("#joshi-more-toggle"),
    mehrMenue: $$("#joshi-more-menu"),
    behaltenText: $$("#joshi-keep-label"),
    pruefung: $$("#joshi-check"),
    neuLaden: $$("#joshi-reload"),
    leinwand: $$("#joshi-canvas"),
    leer: $$("#joshi-empty"),
    rahmenHuelle: $$("#joshi-frame-wrap"),
    rahmen: $$("#joshi-frame"),
    fortschritt: $$("#joshi-progress"),
    laufzeitFehler: $$("#joshi-runtime-error"),
    laufzeitFehlerText: $$("#joshi-runtime-error-text"),
    details: $$("#joshi-details-dialog"),
    detailsInhalt: $$("#joshi-details-body"),
    detailsTitel: $$("#joshi-details-title"),
    codeKopieren: $$("#joshi-copy-code"),
    mail: $$("#joshi-mail-dialog"),
    modus: $$("#joshi-modus"),
    empfehlung: $$("#joshi-empfehlung"),
    vorschlaege: $$("#joshi-vorschlaege"),
    eingabenAn: $$("#joshi-eingaben-an"),
    eingabenPfad: $$("#joshi-eingaben-pfad"),
    eingabenInfo: $$("#joshi-eingaben-info"),
    eingabenKurz: $$("#joshi-eingaben-kurz"),
    eingabenListe: $$("#joshi-eingaben-liste"),
    eingabenUpload: $$("#joshi-eingaben-upload"),
    workspaceAn: $$("#joshi-workspace-an"),
    workspacePfad: $$("#joshi-workspace-pfad"),
    workspaceInfo: $$("#joshi-workspace-info"),
    workspaceKurz: $$("#joshi-workspace-kurz"),
    workspaceAktion: $$("#joshi-workspace-aktion"),
    workspaceAktionInfo: $$("#joshi-workspace-aktion-info"),
    workspaceUpload: $$("#joshi-workspace-upload"),
    mailBetreff: $$("#joshi-mail-subject"),
    mailText: $$("#joshi-mail-text"),
  };

  // ------------------------------------------------------------- Hilfen
  async function hole(pfad, einstellungen = {}) {
    const antwort = await fetch(pfad, { cache: "no-store", ...einstellungen });
    let daten = {};
    try { daten = await antwort.json(); } catch (fehler) { /* kein JSON */ }
    if (antwort.status === 401) throw new Error("Bitte zuerst anmelden.");
    if (!antwort.ok) throw new Error(daten.detail || `Fehler ${antwort.status}`);
    return daten;
  }

  function json(methode, daten) {
    return { method: methode, headers: { "Content-Type": "application/json" }, body: JSON.stringify(daten) };
  }

  function element(tag, klasse = "", text = "") {
    const knoten_ = document.createElement(tag);
    if (klasse) knoten_.className = klasse;
    if (text) knoten_.textContent = text;
    return knoten_;
  }

  let meldungsUhr = null;
  function melde(text, art = "hinweis") {
    let leiste = $$(".joshi-toast");
    if (!leiste) {
      leiste = element("div", "joshi-toast");
      leiste.setAttribute("role", "status");
      document.body.append(leiste);
    }
    leiste.textContent = text;
    leiste.dataset.art = art;
    leiste.hidden = false;
    clearTimeout(meldungsUhr);
    meldungsUhr = setTimeout(() => { leiste.hidden = true; }, art === "fehler" ? 7000 : 3800);
  }

  function zeitText(sekunden) {
    if (!sekunden) return "";
    const datum = new Date(sekunden * 1000);
    const heute = new Date();
    const uhrzeit = datum.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
    return datum.toDateString() === heute.toDateString()
      ? uhrzeit : `${datum.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })} ${uhrzeit}`;
  }

  function modell() {
    return knoten.modell.value || $$("#model")?.value || "";
  }

  function spiegleModelle() {
    const quelle = $$("#model");
    if (!quelle) return;
    const gewaehlt = quelle.value;
    knoten.modell.innerHTML = "";
    [...quelle.options].forEach((option) => {
      const kopie = new Option(option.text, option.value);
      kopie.title = option.title;
      knoten.modell.add(kopie);
    });
    knoten.modell.value = gewaehlt;
    aktualisiereSendenKnopf();
  }

  // ----------------------------------------------- Übersicht aus dem Chat
  // Cloud-Nutzung und Auslastung werden gespiegelt. Für Tokens übernehmen
  // wir nur die Darstellung: Die Werte gehören zum gewählten JOSHI-Auftrag.
  const SPIEGEL = ["#task-tokens", "#cloud-usage", "#system-metrics"];
  let spiegelUhr = null;

  function spiegleAnzeigen() {
    if (!knoten.nebenanzeigen) return;
    SPIEGEL.forEach((auswahl) => {
      const quelle = $$(auswahl);
      if (!quelle) return;
      let kopie = knoten.nebenanzeigen.querySelector(`[data-spiegel="${auswahl}"]`);
      if (!kopie) {
        kopie = document.createElement("section");
        kopie.dataset.spiegel = auswahl;
        if (auswahl === "#task-tokens") kopie.setAttribute("aria-label", "Tokenverbrauch dieses JOSHI-Laufs");
        knoten.nebenanzeigen.append(kopie);
      }
      if (auswahl === "#task-tokens" && kopie.dataset.tokenVorlage) return;
      kopie.className = quelle.className;
      kopie.hidden = quelle.hidden;
      if (kopie.innerHTML !== quelle.innerHTML) {
        kopie.innerHTML = quelle.innerHTML;
        kopie.querySelectorAll("[id]").forEach((el) => {
          if (auswahl === "#task-tokens") el.dataset.tokenPart = el.id;
          el.removeAttribute("id");
        });
        if (auswahl === "#task-tokens") kopie.dataset.tokenVorlage = "1";
        kopie.querySelectorAll("[aria-live]").forEach((el) => el.removeAttribute("aria-live"));
        const knoepfe = [...quelle.querySelectorAll("button")];
        kopie.querySelectorAll("button").forEach((zwilling, nummer) => {
          zwilling.addEventListener("click", () => knoepfe[nummer]?.click());
        });
      }
    });
    window.miniLLM?.renderJoshiTokens?.();
  }

  function beobachteAnzeigen() {
    if (!knoten.nebenanzeigen || !window.MutationObserver) return;
    const beobachter = new MutationObserver(() => {
      clearTimeout(spiegelUhr);
      spiegelUhr = setTimeout(spiegleAnzeigen, 250);
    });
    SPIEGEL.forEach((auswahl) => {
      const quelle = $$(auswahl);
      if (quelle) beobachter.observe(quelle, { subtree: true, childList: true, characterData: true, attributes: true });
    });
    spiegleAnzeigen();
  }

  // ------------------------------- Asset-/Eingabeordner und Projekt-Workspace
  // Zwei getrennte Ordner: „Hier darf JOSHI Material finden“ und „hier darf
  // JOSHI an einem Projekt arbeiten“. Neue Dateien werden nur angezeigt — an
  // ein Modell geht erst, was ein Auftrag wirklich braucht.
  const ordner = { einstellungen: null, dateien: [], bekannt: null, uhr: null };

  async function ladeEinstellungen() {
    try {
      ordner.einstellungen = await hole("/api/joshi/einstellungen");
    } catch (fehler) { return; }
    zeichneOrdner();
    await ladeEingaben();
  }

  function zeichneOrdner() {
    const e = ordner.einstellungen;
    if (!e) return;
    knoten.eingabenAn.checked = Boolean(e.eingaben.aktiv);
    knoten.workspaceAn.checked = Boolean(e.workspace.aktiv);
    if (document.activeElement !== knoten.eingabenPfad) knoten.eingabenPfad.value = e.eingaben.anzeige || e.eingaben.pfad || "";
    if (document.activeElement !== knoten.workspacePfad) knoten.workspacePfad.value = e.workspace.anzeige || e.workspace.pfad || "";
    zeichneWorkspaceInfo();
  }

  function zeichneWorkspaceInfo() {
    const e = ordner.einstellungen;
    if (!e) return;
    const projekt = zustand.daten?.produkt?.quelle?.workspace;
    knoten.workspaceKurz.textContent = e.workspace.aktiv ? (projekt ? "Projekt" : "an") : "aus";
    knoten.workspaceInfo.textContent = e.workspace.aktiv && !e.workspace.gueltig ? e.workspace.fehler
      : projekt ? `📁 Workspace-Projekt: ${projekt.ordner}`
      : e.workspace.aktiv ? "⚡ Automatisch: JOSHI nutzt den Workspace bei großen, mehrteiligen Aufgaben und bleibt sonst bei einer einzelnen HTML-Datei. Auf iPhone/iPad: Dateien über „Vom Gerät importieren“ hinzufügen."
          : "⚡ Schnell-Anwendung (Einzeldatei)";
  }

  function zeichneEingaben() {
    const e = ordner.einstellungen;
    const aktiv = Boolean(e?.eingaben?.aktiv);
    knoten.eingabenListe.innerHTML = "";
    if (!aktiv) {
      knoten.eingabenKurz.textContent = "aus";
      knoten.eingabenInfo.textContent = "Aus: JOSHI ignoriert diesen Ordner vollständig.";
      return;
    }
    const verwendbar = ordner.dateien.filter((d) => d.aktiv).length;
    knoten.eingabenKurz.textContent = ordner.dateien.length
      ? `${ordner.dateien.length} Datei${ordner.dateien.length === 1 ? "" : "en"}` : "an · leer";
    knoten.eingabenInfo.textContent = ordner.fehler || (ordner.dateien.length
      ? `${verwendbar} von ${ordner.dateien.length} verwendbar · JOSHI nimmt nur, was ein Auftrag braucht (@name). Auf iPhone/iPad: „Vom Gerät importieren“ nutzen.`
      : "Ordner ist bereit, aber noch leer. Bilder, Tabellen oder Dokumente hineinlegen — auf iPhone/iPad über „Vom Gerät importieren“.");
    ordner.dateien.slice(0, 60).forEach((datei) => {
      const eintrag = element("li", datei.aktiv ? "is-on" : "");
      const knopf = element("button", "joshi-datei", `${datei.aktiv ? "✓" : "○"} ${datei.name}`);
      knopf.type = "button";
      knopf.title = `${datei.aktiv ? "Nicht verwenden" : "Verwenden"} · ${datei.art} · ${Math.max(1, Math.round(datei.groesse / 1024))} KB`;
      knopf.addEventListener("click", () => schalteDatei(datei));
      eintrag.append(knopf);
      knoten.eingabenListe.append(eintrag);
    });
  }

  async function ladeEingaben({ melden = false } = {}) {
    if (!ordner.einstellungen?.eingaben?.aktiv) {
      ordner.dateien = [];
      ordner.bekannt = null;
      zeichneEingaben();
      return;
    }
    let daten;
    try { daten = await hole("/api/joshi/eingaben"); } catch (fehler) { return; }
    ordner.fehler = daten.fehler || "";
    const neu = new Map((daten.dateien || []).map((d) => [d.name, d]));
    if (melden && ordner.bekannt) {
      const hinzu = [...neu.keys()].filter((name) => !ordner.bekannt.has(name));
      const geaendert = [...neu.values()].filter((d) => ordner.bekannt.has(d.name) && ordner.bekannt.get(d.name) !== d.geaendert);
      if (hinzu.length) melde(`Neue Datei${hinzu.length > 1 ? "en" : ""} erkannt: ${hinzu.slice(0, 3).join(", ")}${hinzu.length > 3 ? " …" : ""}`);
      else if (geaendert.length) melde(`Geänderte Datei erkannt: ${geaendert[0].name}`);
    }
    ordner.bekannt = new Map([...neu.values()].map((d) => [d.name, d.geaendert]));
    ordner.dateien = daten.dateien || [];
    zeichneEingaben();
  }

  async function schalteDatei(datei) {
    try {
      await hole("/api/joshi/eingaben/datei", json("PUT", { name: datei.name, aktiv: !datei.aktiv }));
      datei.aktiv = !datei.aktiv;
      zeichneEingaben();
    } catch (fehler) { melde(fehler.message, "fehler"); }
  }

  async function speichereOrdner(bereich, werte) {
    try {
      ordner.einstellungen = await hole("/api/joshi/einstellungen", json("PUT", { [bereich]: werte }));
      zeichneOrdner();
      await ladeEingaben();
      return true;
    } catch (fehler) {
      melde(fehler.message, "fehler");
      zeichneOrdner();
      return false;
    }
  }

  async function importiereOrdnerDateien(bereich, dateien) {
    const auswahl = [...(dateien || [])].filter((datei) => datei instanceof File && datei.size);
    if (!auswahl.length) return;
    // Ein bewusster Geräte-Import ist zugleich die Freigabe für diesen Bereich.
    if (!ordner.einstellungen?.[bereich]?.aktiv && !(await speichereOrdner(bereich, { aktiv: true }))) return;
    const formular = new FormData();
    auswahl.slice(0, 300).forEach((datei) => {
      // webkitdirectory liefert auf Desktop und iPad relative Namen; der Server
      // reduziert sie auf sichere Dateinamen innerhalb der gewählten Wurzel.
      formular.append("dateien", datei, datei.webkitRelativePath || datei.name);
    });
    try {
      const daten = await hole(`/api/joshi/ordner/${bereich}/importieren`, { method: "POST", body: formular });
      await ladeEingaben();
      const anzahl = (daten.dateien || []).length;
      melde(`${anzahl} Datei${anzahl === 1 ? "" : "en"} vom Gerät in ${bereich === "eingaben" ? "Assets / Eingaben" : "den Workspace"} übernommen.`);
    } catch (fehler) {
      melde(fehler.message, "fehler");
    }
  }

  // Offen oder zu merkt sich jedes Gerät selbst; Einschalten klappt auf.
  function panelOeffnen(bereich, offen, merken = true) {
    const panel = bereich === "eingaben" ? $$("#joshi-eingaben") : $$("#joshi-workspace");
    if (!panel) return;
    panel.querySelector(".joshi-panel-inhalt").hidden = !offen;
    panel.querySelector(".joshi-panel-titel").setAttribute("aria-expanded", String(offen));
    if (merken) {
      try { localStorage.setItem(`mini-llm-joshi-ordner-${bereich}`, offen ? "1" : "0"); } catch (fehler) { /* egal */ }
    }
  }

  function panelZustandLaden() {
    ["eingaben", "workspace"].forEach((bereich) => {
      let offen = false;
      try { offen = localStorage.getItem(`mini-llm-joshi-ordner-${bereich}`) === "1"; } catch (fehler) { /* egal */ }
      panelOeffnen(bereich, offen, false);
    });
  }

  async function schalteOrdner(bereich, an) {
    const gespeichert = await speichereOrdner(bereich, { aktiv: an });
    if (!gespeichert) {
      panelOeffnen(bereich, true);
      return;
    }
    panelOeffnen(bereich, an);
    if (!an) return;
    const e = ordner.einstellungen?.[bereich] || {};
    melde(bereich === "eingaben"
      ? `Asset-/Eingabeordner an: ${e.anzeige || e.pfad}. Bilder, Tabellen oder Dokumente dort ablegen.`
      : `Projekt-Workspace erlaubt: ${e.anzeige || e.pfad}. Ein Projektordner entsteht nur, wenn ein Auftrag ihn braucht.`);
  }

  function starteOrdnerabfrage() {
    // Leichtes Nachsehen statt Dateiwächter: nur solange JOSHI offen und sichtbar ist.
    if (ordner.uhr) return;
    ordner.uhr = setInterval(() => {
      if (!ansicht.hidden && !document.hidden && ordner.einstellungen?.eingaben?.aktiv) ladeEingaben({ melden: true });
    }, 6000);
  }

  function stoppeOrdnerabfrage() {
    clearInterval(ordner.uhr);
    ordner.uhr = null;
  }

  // @-Verweise: Beim Tippen von @ werden Dateien aus dem Eingabeordner vorgeschlagen.
  function zeigeVorschlaege() {
    const vor = knoten.eingabe.value.slice(0, knoten.eingabe.selectionStart || 0);
    const treffer = /@([\w.\-äöüÄÖÜß]*)$/.exec(vor);
    if (!treffer || !ordner.dateien.length) { knoten.vorschlaege.hidden = true; return; }
    const suche = treffer[1].toLowerCase();
    const passend = ordner.dateien.filter((d) => d.name.toLowerCase().includes(suche)).slice(0, 6);
    knoten.vorschlaege.innerHTML = "";
    passend.forEach((datei) => {
      const knopf = element("button", "", datei.name);
      knopf.type = "button";
      knopf.setAttribute("role", "option");
      knopf.addEventListener("mousedown", (ereignis) => {
        ereignis.preventDefault();
        const start = vor.length - treffer[0].length;
        const rest = knoten.eingabe.value.slice(vor.length);
        knoten.eingabe.value = `${knoten.eingabe.value.slice(0, start)}@${datei.name} ${rest}`;
        knoten.vorschlaege.hidden = true;
        knoten.eingabe.focus();
        aktualisiereSendenKnopf();
      });
      knoten.vorschlaege.append(knopf);
    });
    knoten.vorschlaege.hidden = !passend.length;
  }

  // Empfehlung statt automatischer Eskalation: Der Nutzer entscheidet.
  function zeigeEmpfehlung(empfehlung, formular, pfad) {
    const karte = knoten.empfehlung;
    karte.innerHTML = "";
    karte.append(element("p", "", empfehlung.text));
    if ((empfehlung.gruende || []).length) karte.append(element("small", "", `Erkannt: ${empfehlung.gruende.join(" · ")}`));
    const reihe = element("div", "joshi-empfehlung-knoepfe");
    const ueberfuehren = empfehlung.art === "ueberfuehren";
    const ja = element("button", "joshi-mini is-primary", ueberfuehren ? "In Workspace überführen" : "Workspace aktivieren");
    const nein = element("button", "joshi-mini", ueberfuehren ? "Als Einzeldatei weiterführen" : "Weiter als Einzeldatei");
    [ja, nein].forEach((k) => { k.type = "button"; });
    ja.addEventListener("click", async () => {
      if (!ordner.einstellungen?.workspace?.aktiv && !(await speichereOrdner("workspace", { aktiv: true }))) return;
      if (ueberfuehren) {
        try {
          const antwort = await hole(`/api/joshi/produkte/${encodeURIComponent(zustand.daten.produkt.id)}/workspace`, { method: "POST" });
          melde(`Projekt angelegt: ${antwort.workspace.pfad}`);
        } catch (fehler) { melde(fehler.message, "fehler"); return; }
      }
      formular.set("modus", "workspace");
      karte.hidden = true;
      await sendeFormular(formular, pfad);
    });
    nein.addEventListener("click", async () => {
      formular.set("modus", "einzeldatei");
      karte.hidden = true;
      await sendeFormular(formular, pfad);
    });
    reihe.append(ja, nein);
    karte.append(reihe);
    karte.hidden = false;
  }

  // ------------------------------------------------------------ Ansicht
  function oeffneAnsicht({ auswahl = true } = {}) {
    ansicht.hidden = false;
    document.body.classList.add("joshi-offen");
    zustand.fertigSeitAbwesenheit = false;
    zeichneKopfstatus();
    ladeEinstellungen();
    starteOrdnerabfrage();
    spiegleModelle();
    spiegleAnzeigen();
    ladeProdukte().then(() => {
      if (!auswahl) return;
      if (zustand.aktuell && zustand.produkte.some((p) => p.id === zustand.aktuell)) {
        waehleProdukt(zustand.aktuell);
      } else {
        zeigeNeu();
      }
    });
    setTimeout(() => knoten.eingabe.focus(), 60);
  }

  function schliesseAnsicht() {
    // Nur die Ansicht verschwindet; ein laufender Auftrag arbeitet weiter.
    ansicht.hidden = true;
    document.body.classList.remove("joshi-offen");
    stoppeOrdnerabfrage();
    schliesseMenues();
    speichereZustandJetzt();
    if (zustand.live) starteStatusabfrage();
  }

  function setzeBereich(bereich) {
    zustand.bereich = bereich;
    ansicht.dataset.bereich = bereich;
    ansicht.querySelectorAll(".joshi-tabs-mobile button").forEach((knopf) => {
      knopf.classList.toggle("is-active", knopf.dataset.bereich === bereich);
    });
  }

  function zeigeProduktliste(offen) {
    knoten.produkte.classList.toggle("is-open", offen);
    knoten.produkteSchleier.classList.toggle("is-open", offen);
    knoten.produkteKnopf.setAttribute("aria-expanded", String(offen));
  }

  // ------------------------------------------------------------ Produkte
  async function ladeProdukte() {
    try {
      const daten = await hole("/api/joshi/produkte");
      zustand.produkte = daten.produkte || [];
    } catch (fehler) {
      zustand.produkte = [];
      knoten.liste.innerHTML = "";
      knoten.liste.append(element("p", "joshi-list-empty", fehler.message));
      return;
    }
    zeichneProduktliste();
  }

  function zeichneProduktliste() {
    knoten.liste.innerHTML = "";
    if (!zustand.produkte.length) {
      knoten.liste.append(element("p", "joshi-list-empty", "Noch keine Produkte. Beschreibe rechts deine erste Idee."));
      return;
    }
    zustand.produkte.forEach((produkt) => {
      const zeile = element("button", "joshi-product");
      zeile.type = "button";
      zeile.classList.toggle("is-active", produkt.id === zustand.aktuell);
      const punkt = element("i", `joshi-dot is-${produkt.laeuft ? "building" : produkt.status}`);
      const mitte = element("span", "joshi-product-text");
      mitte.append(element("strong", "", produkt.titel || "Neues Produkt"));
      const unter = produkt.laeuft ? "JOSHI arbeitet …"
        : `${produkt.version ? `v${produkt.version} · ` : ""}${zeitText(produkt.geaendert)}`;
      mitte.append(element("small", "", unter));
      zeile.append(punkt, mitte);
      if (produkt.behalten) zeile.append(element("span", "joshi-kept", "★"));
      zeile.addEventListener("click", () => {
        waehleProdukt(produkt.id);
        zeigeProduktliste(false);
      });
      knoten.liste.append(zeile);
    });
  }

  function zeigeNeu() {
    loeseStrom();
    window.miniLLM?.joshiTokenstand?.({});
    zustand.aktuell = "";
    zustand.daten = null;
    localStorage.removeItem(LETZTES_PRODUKT);
    zeichneProduktliste();
    zeichneFeed();
    zeichneWerkzeuge();
    zeigeVorschau(null);
    knoten.eingabe.placeholder = "Beschreibe, was JOSHI für dich erstellen soll …";
    setzeBereich("dialog");
  }

  async function waehleProdukt(produktId, { vorschauErzwingen = false } = {}) {
    if (zustand.aktuell !== produktId) loeseStrom();
    zustand.aktuell = produktId;
    localStorage.setItem(LETZTES_PRODUKT, produktId);
    zeichneProduktliste();
    let daten;
    try {
      daten = await hole(`/api/joshi/produkte/${encodeURIComponent(produktId)}`);
    } catch (fehler) {
      melde(fehler.message, "fehler");
      if (/nicht \(mehr\)/.test(fehler.message)) zeigeNeu();
      return;
    }
    if (zustand.aktuell !== produktId) return;
    zustand.daten = daten;
    const letzter = (daten.auftraege || []).at(-1);
    const gespeichert = daten.laufend?.tokens || letzter?.tokenstand;
    if (gespeichert && typeof gespeichert.tokens === "number") {
      window.miniLLM?.joshiTokenstand?.({ ...gespeichert, sekunden: gespeichert.modellsekunden,
        laufend: Boolean(daten.laufend) && gespeichert.laufend !== false });
    } else if (!zustand.live || zustand.live.produktId !== produktId) {
      window.miniLLM?.joshiTokenstand?.({ tokens: letzter?.verbrauch?.completion_tokens || 0,
        aufrufe: letzter?.verbrauch?.calls || 0 });
    }
    knoten.eingabe.placeholder = daten.produkt.version
      ? "Was soll JOSHI ändern? Zum Beispiel: „Mach den Hintergrund heller.“"
      : "Beschreibe, was JOSHI für dich erstellen soll …";
    zeichneFeed();
    zeichneWerkzeuge();
    if (daten.laufend && !daten.laufend.beendet) {
      if (zustand.live?.jobId !== daten.laufend.job) verbinde(daten.laufend.job, produktId);
    }
    const nummer = daten.produkt.version;
    if (vorschauErzwingen || zustand.vorschau.produkt !== produktId || zustand.vorschau.version !== nummer) {
      await zeigeVorschau(nummer ? produktId : null, nummer);
    }
    zeichneFortschritt();
  }

  // --------------------------------------------------------------- Verlauf
  function zeichneFeed() {
    knoten.feed.innerHTML = "";
    const daten = zustand.daten;
    if (!daten) {
      const willkommen = element("div", "joshi-welcome");
      willkommen.append(
        element("strong", "", "Denke es. Nutze es. Teile es."),
        element("p", "", "Beschreibe, was du gerade brauchst – einen Rechner, eine Umfrage, einen Vergleich, ein Dashboard. Bilder und Dateien kannst du einfach dazulegen."),
      );
      knoten.feed.append(willkommen);
      return;
    }
    const verstaendnis = daten.produkt.verstaendnis || {};
    if ((verstaendnis.funktionen || []).length) {
      const karte = element("details", "joshi-understanding");
      const kopf = element("summary", "", "So hat JOSHI die Idee verstanden");
      karte.append(kopf);
      if (verstaendnis.zweck) karte.append(element("p", "", verstaendnis.zweck));
      const liste = element("ul");
      verstaendnis.funktionen.forEach((funktion) => liste.append(element("li", "", funktion)));
      karte.append(liste);
      knoten.feed.append(karte);
    }
    (daten.auftraege || []).forEach((auftrag) => {
      knoten.feed.append(nutzerBlase(auftrag));
      if (zustand.live && zustand.live.jobId === auftrag.id) {
        const karte = element("div", "joshi-message joshi-live");
        karte.id = "joshi-live-card";
        knoten.feed.append(karte);
        zeichneLivekarte();
      } else {
        knoten.feed.append(antwortBlase(auftrag));
      }
    });
    knoten.feed.scrollTop = knoten.feed.scrollHeight;
  }

  function nutzerBlase(auftrag) {
    const blase = element("div", "joshi-message joshi-user");
    const herkunft = { chat: "Aus dem Chat", browser: "Fehler in der Anwendung" }[auftrag.herkunft];
    if (herkunft) blase.append(element("span", "joshi-origin", herkunft));
    blase.append(element("div", "joshi-text", auftrag.text || "(ohne Text)"));
    if ((auftrag.dateien || []).length) {
      const dateien = element("div", "joshi-files");
      auftrag.dateien.forEach((datei) => dateien.append(element("span", "joshi-file-pill",
        `${datei.art === "bild" ? "🖼" : "📄"} ${datei.name}`)));
      blase.append(dateien);
    }
    return blase;
  }

  // Die Schritte bleiben nach dem Auftrag sichtbar: gestufte Änderungen mit
  // ihren Stufen, alle anderen mit ihren Phasen.
  const ABLAUF_ZEICHEN = { passed: "✓", fertig: "✓", failed: "✕", fehler: "✕", aborted: "–", deferred: "⏸",
    not_proven: "?", reparatur: "↻", aktiv: "…", offen: "○", planned: "○" };
  function ablaufListe(auftrag) {
    const ablauf = auftrag.ablauf || {};
    const stufen = ablauf.stufen || [];
    const schritte = (ablauf.schritte || []).filter((s) => s.zustand && s.zustand !== "offen");
    if (!stufen.length && !schritte.length) return null;
    const box = element("details", "joshi-ablauf");
    if (auftrag.status !== "ready") box.open = true;
    const titel = stufen.length
      ? `Umfangreiche Änderung · ${stufen.length} Schritte · ${stufen.filter((s) => s.zustand === "passed").length} geprüft`
      : `Ablauf · ${schritte.length} Schritte`;
    box.append(element("summary", "", titel));
    const liste = element("ol", "joshi-steps");
    (stufen.length ? stufen : schritte).forEach((s) => {
      const zustandName = String(s.zustand || "offen").toLowerCase();
      const eintrag = element("li", `is-${zustandName}`);
      eintrag.append(element("span", "joshi-step-mark", ABLAUF_ZEICHEN[zustandName] || "○"));
      const text = element("span", "joshi-step-text");
      text.append(element("strong", "", stufen.length ? `${s.nummer}. ${s.titel}` : s.text));
      const detail = stufen.length ? (s.grund || (STUFEN_ZUSTAENDE[zustandName]?.text || "")) : s.detail;
      if (detail) text.append(element("small", "", detail));
      eintrag.append(text);
      liste.append(eintrag);
    });
    box.append(liste);
    return box;
  }

  function antwortBlase(auftrag) {
    const blase = element("div", `joshi-message joshi-answer is-${auftrag.status}`);
    const kopf = element("div", "joshi-answer-head");
    const symbol = { ready: "✓", failed: "!", cancelled: "–" }[auftrag.status] || "●";
    kopf.append(element("span", "joshi-answer-mark", symbol), element("strong", "", "JOSHI"));
    if (auftrag.version && auftrag.status === "ready") kopf.append(element("span", "joshi-pill", `v${auftrag.version}`));
    blase.append(kopf);
    const text = auftrag.antwort || (auftrag.status === "cancelled" ? "Abgebrochen." : "Auftrag ohne Ergebnis beendet.");
    blase.append(element("div", "joshi-text", text));
    const ablauf = ablaufListe(auftrag);
    if (ablauf) blase.append(ablauf);
    if ((auftrag.warnungen || []).length) {
      const liste = element("ul", "joshi-warnings");
      auftrag.warnungen.forEach((w) => liste.append(element("li", "", w)));
      blase.append(liste);
    }
    const fuss = element("div", "joshi-answer-foot");
    const technik = element("button", "joshi-link", "Technische Details");
    technik.type = "button";
    technik.addEventListener("click", () => oeffneDetails("ablauf", auftrag.id));
    fuss.append(technik);
    const tokenstand = auftrag.tokenstand || auftrag.verbrauch?.tokenstand || {};
    const tokens = tokenstand.tokens ?? ((auftrag.verbrauch?.prompt_tokens || 0) + (auftrag.verbrauch?.completion_tokens || 0));
    if (tokens) {
      const ungefaehr = tokenstand.usage_status && tokenstand.usage_status !== "actual";
      fuss.append(element("small", "", `${ungefaehr ? "≈ " : ""}${Number(tokens).toLocaleString("de-DE")} Tokens · ${auftrag.modell}`));
    }
    blase.append(fuss);
    return blase;
  }

  function schritteListe(live) {
    const liste = element("ol", "joshi-steps");
    live.schritte.forEach((schritt) => {
      const eintrag = element("li", `is-${schritt.zustand}`);
      eintrag.append(element("span", "joshi-step-mark", SCHRITT_ZEICHEN[schritt.zustand] || "○"));
      const text = element("span", "joshi-step-text");
      text.append(element("strong", "", schritt.text));
      const detail = schritt.zustand === "aktiv" && live.fortschritt ? live.fortschritt : schritt.detail;
      if (detail) text.append(element("small", "", detail));
      eintrag.append(text);
      liste.append(eintrag);
    });
    return liste;
  }

  // ------------------------------------------------ Gestufter Fortschritt
  function stufenStatus(zustand) {
    return STUFEN_ZUSTAENDE[String(zustand || "planned").toLowerCase()] || STUFEN_ZUSTAENDE.planned;
  }

  function hatStufen(live) {
    return Array.isArray(live.stufen) && live.stufen.length > 0;
  }

  function stufenUeberschrift(live) {
    const von = live.stufenVon || live.stufen?.length || 0;
    return `Umfangreiche Änderung · ${von} ${von === 1 ? "Schritt" : "Schritte"}`;
  }

  function stufenEreignisDetail(ereignis, zustand) {
    const detail = String(ereignis.detail || "").trim();
    if (detail) return detail;
    const grund = String(ereignis.grund || "").trim();
    if (zustand === "failed" && grund) return grund;
    if (zustand === "passed" && Number(ereignis.nicht_bewiesen || 0) > 0) {
      const anzahl = Number(ereignis.nicht_bewiesen);
      return `geprüft · Checkpoint gespeichert · ${anzahl} nicht nachweisbar`;
    }
    if (zustand === "generating" && ereignis.zweiter_versuch) return "Knapperer zweiter Versuch wird erstellt …";
    return stufenStatus(zustand).text;
  }

  function uebernehmeStufenplan(live, ereignis) {
    const vorher = new Map((live.stufen || []).map((stufe) => [stufe.nummer, stufe]));
    const roh = Array.isArray(ereignis.stufen) ? ereignis.stufen : [];
    const von = Math.max(Number(ereignis.von) || 0, roh.length);
    const start = Math.max(0, Number(ereignis.start) || 0);
    live.stufenVon = von;
    live.stufen = roh.map((eintrag, index) => {
      const nummer = Math.max(1, Number(eintrag.nummer) || index + 1);
      const alt = vorher.get(nummer);
      const zustand = String(alt?.zustand || eintrag.zustand || (index < start ? "passed" : "planned")).toLowerCase();
      return {
        nummer, von,
        titel: String(alt?.titel || eintrag.titel || `Schritt ${nummer}`),
        kriterien: Number(eintrag.kriterien) || 0,
        zustand,
        detail: String(alt?.detail || eintrag.detail || stufenEreignisDetail(eintrag, zustand)),
      };
    });
    live.fortschritt = "";
  }

  function uebernehmeStufe(live, ereignis) {
    const roh = Number(ereignis.nummer);
    if (!Number.isFinite(roh) || roh < 1) return;
    const nummer = Math.round(roh);
    const von = Math.max(Number(ereignis.von) || 0, live.stufenVon || 0, nummer);
    live.stufenVon = von;
    let stufe = (live.stufen || []).find((eintrag) => eintrag.nummer === nummer);
    if (!stufe) {
      live.stufen ||= [];
      stufe = { nummer, von, titel: `Schritt ${nummer}`, kriterien: 0, zustand: "planned", detail: "" };
      live.stufen.push(stufe);
      live.stufen.sort((a, b) => a.nummer - b.nummer);
    }
    const zustand = String(ereignis.zustand || stufe.zustand || "planned").toLowerCase();
    stufe.von = von;
    stufe.titel = String(ereignis.titel || stufe.titel || `Schritt ${nummer}`);
    stufe.zustand = zustand;
    stufe.detail = stufenEreignisDetail(ereignis, zustand);
    // Fortschrittszeilen gehören zum vorherigen Modellstrom. Beim Phasen- oder
    // Stufenwechsel dürfen sie nicht unter der neuen Stage weiter angezeigt werden.
    live.fortschritt = "";
  }

  function aktuelleStufe(live) {
    if (!hatStufen(live)) return null;
    return [...live.stufen].reverse().find((stufe) => AKTIVE_STUFEN.has(stufe.zustand))
      || live.stufen.find((stufe) => stufe.zustand === "planned")
      || live.stufen[live.stufen.length - 1];
  }

  function stufenDetail(stufe, live) {
    if (AKTIVE_STUFEN.has(stufe.zustand) && live.fortschritt) return live.fortschritt;
    return stufe.detail || stufenStatus(stufe.zustand).text;
  }

  function stufenZusammenfassung(live) {
    const stufe = aktuelleStufe(live);
    if (!stufe) return stufenUeberschrift(live);
    const von = stufe.von || live.stufenVon || live.stufen.length;
    return `Schritt ${stufe.nummer} von ${von} · ${stufe.titel} · ${stufenDetail(stufe, live)}`;
  }

  function stufenListe(live) {
    const liste = element("ol", "joshi-steps joshi-stage-steps");
    live.stufen.forEach((stufe) => {
      const status = stufenStatus(stufe.zustand);
      const eintrag = element("li", `is-${status.anzeige}`);
      eintrag.dataset.stageState = stufe.zustand;
      eintrag.append(element("span", "joshi-step-mark", SCHRITT_ZEICHEN[status.anzeige] || "○"));
      const text = element("span", "joshi-step-text");
      const von = stufe.von || live.stufenVon || live.stufen.length;
      text.append(element("strong", "", `${stufe.nummer}/${von} ${stufe.titel}`));
      const detail = stufenDetail(stufe, live);
      if (detail) text.append(element("small", "", detail));
      eintrag.append(text);
      liste.append(eintrag);
    });
    return liste;
  }

  function zeichneLivekarte() {
    const karte = $$("#joshi-live-card");
    const live = zustand.live;
    if (!karte || !live) return;
    karte.innerHTML = "";
    const kopf = element("div", "joshi-answer-head");
    kopf.append(element("span", "joshi-answer-mark is-live", "●"), element("strong", "", "JOSHI arbeitet"));
    const abbrechen = element("button", "joshi-link", "Abbrechen");
    abbrechen.type = "button";
    abbrechen.addEventListener("click", abbrechenAuftrag);
    kopf.append(abbrechen);
    karte.append(kopf);
    if (hatStufen(live)) karte.append(element("p", "joshi-stage-summary", stufenUeberschrift(live)), stufenListe(live));
    else karte.append(schritteListe(live));
    live.hinweise.slice(-3).forEach((hinweis) => karte.append(element("p", "joshi-live-note", hinweis)));
  }

  function zeichneFortschritt() {
    const live = zustand.live && zustand.live.produktId === zustand.aktuell ? zustand.live : null;
    const ohneVersion = !zustand.daten?.produkt?.version;
    knoten.fortschritt.hidden = !live;
    knoten.fortschritt.classList.toggle("is-overlay", Boolean(live && ohneVersion));
    if (!live) return;
    knoten.fortschritt.innerHTML = "";
    if (ohneVersion) {
      const karte = element("div", "joshi-progress-card");
      karte.append(element("div", "joshi-progress-mark", "✦"),
        element("strong", "", zustand.daten?.produkt?.titel || "Neues Produkt"));
      if (hatStufen(live)) karte.append(element("p", "joshi-stage-summary", stufenUeberschrift(live)), stufenListe(live));
      else karte.append(schritteListe(live));
      knoten.fortschritt.append(karte);
    } else {
      const aktiv = live.schritte.find((s) => s.zustand === "aktiv" || s.zustand === "reparatur");
      const text = hatStufen(live)
        ? `JOSHI ändert die Anwendung – ${stufenZusammenfassung(live)}`
        : `JOSHI ändert die Anwendung – ${aktiv ? aktiv.text : "Vorbereitung"}${live.fortschritt ? ` · ${live.fortschritt}` : ""}`;
      knoten.fortschritt.append(element("span", "joshi-progress-dot"),
        element("span", "joshi-progress-text", text));
    }
  }

  // ------------------------------------------------------------ Werkzeuge
  function zeichneWerkzeuge() {
    const produkt = zustand.daten?.produkt;
    const hatVersion = Boolean(produkt?.version);
    const laeuft = Boolean(zustand.live && zustand.live.produktId === zustand.aktuell);
    knoten.titel.disabled = !produkt;
    knoten.titel.value = produkt?.titel || "";
    knoten.version.hidden = !hatVersion;
    knoten.version.textContent = hatVersion ? `v${produkt.version}` : "";
    knoten.status.hidden = !produkt;
    const status = laeuft ? "building" : produkt?.status;
    knoten.status.textContent = STATUSTEXT[status] || "";
    knoten.status.dataset.status = status || "";
    const frueher = (zustand.daten?.versionen || []).some((v) => v.nummer < (produkt?.version || 0) && !v.abgelehnt);
    knoten.rueckgaengig.disabled = !frueher || laeuft;
    [knoten.exportKnopf, knoten.teilenKnopf, knoten.besprechen, knoten.neuLaden].forEach((knopf) => {
      knopf.disabled = !hatVersion;
    });
    knoten.mehrKnopf.disabled = !produkt;
    const projekt = produkt?.quelle?.workspace;
    const intern = produkt?.quelle?.intern || {};
    knoten.modus.hidden = !hatVersion;
    // Kein Workspace-Schalter mehr: JOSHI entscheidet selbst und sagt, woran es arbeitet.
    knoten.modus.textContent = intern.gross ? "📁 Projekt" : "⚡ Schnell-Anwendung";
    knoten.modus.title = intern.gross
      ? `Groß: ${Number(intern.zeichen || 0).toLocaleString("de-DE")} Zeichen – JOSHI arbeitet intern in Projektdateien`
      : "Eine einzelne, weitergebbare HTML-Datei";
    const shareInfo = document.getElementById("joshi-share-html-info");
    if (shareInfo) shareInfo.textContent = intern.zip
      ? "ZIP mit HTML und den nötigen Dateien – mit aktuellem Stand"
      : "Eine Datei, läuft überall – mit aktuellem Stand";
    knoten.workspaceAktion.textContent = projekt ? "Projektordner öffnen" : "In Workspace überführen";
    knoten.workspaceAktionInfo.textContent = projekt ? projekt.ordner : "Projektordner mit Dokumentation anlegen";
    zeichneWorkspaceInfo();
    knoten.behaltenText.textContent = produkt?.behalten ? "Nicht mehr behalten" : "Behalten";
    const pruefung = zustand.daten?.pruefung || {};
    knoten.pruefung.textContent = hatVersion
      ? `${pruefung.ok ? "✓" : "!"} ${pruefung.kurz || ""}${pruefung.browser === false ? " (ohne Browserprüfung)" : ""}`
      : "";
    knoten.pruefung.dataset.ok = pruefung.ok ? "1" : "0";
    aktualisiereSendenKnopf();
  }

  // Websuche für JOSHI-Aufträge: wie im Chat ein Schalter, gemerkt je Gerät.
  function webAn() {
    try { return localStorage.getItem("joshi-web") === "1"; } catch (fehler) { return false; }
  }
  function zeichneWeb() {
    const an = webAn();
    knoten.webKnopf?.classList.toggle("active", an);
    knoten.webKnopf?.setAttribute("aria-pressed", String(an));
    if (knoten.webInfo) knoten.webInfo.hidden = !an;
  }
  knoten.webKnopf?.addEventListener("click", () => {
    try { localStorage.setItem("joshi-web", webAn() ? "0" : "1"); } catch (fehler) { /* privat */ }
    zeichneWeb();
  });
  zeichneWeb();

  function aktualisiereSendenKnopf() {
    const laeuft = Boolean(zustand.live && zustand.live.produktId === zustand.aktuell && zustand.aktuell);
    knoten.form.classList.toggle("is-running", laeuft);
    knoten.senden.title = laeuft ? "JOSHI stoppen" : "An JOSHI senden";
    knoten.senden.setAttribute("aria-label", knoten.senden.title);
    const hatInhalt = knoten.eingabe.value.trim() || zustand.anhaenge.length;
    knoten.senden.disabled = !laeuft && (!hatInhalt || !modell());
  }

  // ------------------------------------------------------------- Vorschau
  async function zeigeVorschau(produktId, version = 0) {
    zustand.laufzeitFehler = [];
    knoten.laufzeitFehler.hidden = true;
    if (!produktId) {
      zustand.vorschau = { produkt: "", version: 0 };
      knoten.rahmen.srcdoc = "";
      knoten.rahmenHuelle.hidden = true;
      knoten.leer.hidden = Boolean(zustand.daten);
      return;
    }
    try {
      const daten = await hole(`/api/joshi/produkte/${encodeURIComponent(produktId)}/laufzeit?version=${version}`);
      if (zustand.aktuell !== produktId) return;
      zustand.vorschau = { produkt: produktId, version: daten.version };
      knoten.rahmen.srcdoc = daten.dokument;
      knoten.rahmenHuelle.hidden = false;
      knoten.leer.hidden = true;
    } catch (fehler) {
      melde(`Vorschau nicht ladbar: ${fehler.message}`, "fehler");
    }
  }

  function setzeGeraet(geraet) {
    zustand.geraet = geraet;
    knoten.leinwand.dataset.geraet = geraet;
    knoten.rahmenHuelle.style.maxWidth = GERAETE[geraet];
    ansicht.querySelectorAll(".joshi-devices button").forEach((knopf) => {
      const aktiv = knopf.dataset.geraet === geraet;
      knopf.classList.toggle("is-active", aktiv);
      knopf.setAttribute("aria-checked", String(aktiv));
    });
  }

  // Nachrichten aus der Anwendung: nur aus genau diesem Rahmen, nur bekannte Arten.
  window.addEventListener("message", (ereignis) => {
    if (ereignis.source !== knoten.rahmen.contentWindow) return;
    const daten = ereignis.data;
    if (!daten || daten.joshi !== 1 || typeof daten.art !== "string") return;
    if (daten.art === "zustand" && daten.daten && typeof daten.daten === "object") {
      planeZustandSpeichern(daten.daten);
    } else if (daten.art === "export" && daten.daten && typeof daten.daten === "object") {
      exportWunsch(daten.daten);
    } else if (daten.art === "fehler" && daten.daten) {
      const text = String(daten.daten.text || "").slice(0, 400);
      if (!text || zustand.laufzeitFehler.includes(text)) return;
      zustand.laufzeitFehler.push(text);
      if (zustand.live) return;
      knoten.laufzeitFehlerText.textContent = `In der Anwendung ist ein Fehler aufgetreten: ${text}`;
      knoten.laufzeitFehler.hidden = false;
    }
  });

  function planeZustandSpeichern(werte) {
    const produktId = zustand.vorschau.produkt;
    if (!produktId) return;
    zustand.zustandOffen = { produktId, werte };
    clearTimeout(zustand.zustandUhr);
    zustand.zustandUhr = setTimeout(speichereZustandJetzt, 900);
  }

  async function speichereZustandJetzt() {
    clearTimeout(zustand.zustandUhr);
    const offen = zustand.zustandOffen;
    zustand.zustandOffen = null;
    if (!offen) return;
    try {
      await hole(`/api/joshi/produkte/${encodeURIComponent(offen.produktId)}/zustand`, json("PUT", offen.werte));
      if (zustand.daten?.produkt?.id === offen.produktId) zustand.daten.produkt.zustand = offen.werte;
    } catch (fehler) {
      console.warn("JOSHI-Zustand nicht gespeichert:", fehler.message);
    }
  }

  // ------------------------------------------------------------- Anhänge
  function istBild(datei) {
    return /^image\//.test(datei.type) || /\.(png|jpe?g|gif|webp)$/i.test(datei.name);
  }

  function zeichneAnhaenge() {
    knoten.anhangListe.innerHTML = "";
    knoten.anhangListe.hidden = !zustand.anhaenge.length;
    zustand.anhaenge.forEach((anhang) => {
      const karte = element("div", "joshi-attachment");
      if (anhang.vorschau) {
        const bild = element("img");
        bild.src = anhang.vorschau;
        bild.alt = "";
        karte.append(bild);
      } else {
        karte.append(element("span", "joshi-attachment-icon", "📄"));
      }
      karte.append(element("span", "joshi-attachment-name", anhang.datei.name));
      const weg = element("button", "joshi-attachment-remove", "×");
      weg.type = "button";
      weg.title = "Anhang entfernen";
      weg.setAttribute("aria-label", `${anhang.datei.name} entfernen`);
      weg.addEventListener("click", () => {
        if (anhang.vorschau) URL.revokeObjectURL(anhang.vorschau);
        zustand.anhaenge = zustand.anhaenge.filter((a) => a !== anhang);
        zeichneAnhaenge();
      });
      karte.append(weg);
      knoten.anhangListe.append(karte);
    });
    aktualisiereSendenKnopf();
  }

  function fuegeDateienHinzu(dateien) {
    [...dateien].forEach((datei) => {
      if (!(datei instanceof File) || !datei.size) return;
      if (zustand.anhaenge.some((a) => a.datei.name === datei.name && a.datei.size === datei.size)) return;
      zustand.anhaenge.push({ datei, vorschau: istBild(datei) ? URL.createObjectURL(datei) : "" });
    });
    zeichneAnhaenge();
  }

  function leereAnhaenge() {
    zustand.anhaenge.forEach((a) => a.vorschau && URL.revokeObjectURL(a.vorschau));
    zustand.anhaenge = [];
    knoten.dateiEingabe.value = "";
    zeichneAnhaenge();
  }

  function zwischenablage(ereignis) {
    const daten = ereignis.clipboardData;
    if (!daten) return;
    const dateien = [...daten.items].filter((e) => e.kind === "file").map((e) => e.getAsFile()).filter(Boolean)
      .map((datei, nummer) => {
        if (datei.name && datei.name !== "image.png") return datei;
        const endung = (datei.type.split("/")[1] || "png").replace("jpeg", "jpg");
        const stempel = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 15);
        return new File([datei], `eingefuegtes-bild-${stempel}-${nummer + 1}.${endung}`, { type: datei.type || "image/png" });
      });
    if (dateien.length) {
      ereignis.preventDefault();
      fuegeDateienHinzu(dateien);
      melde(`${dateien.length === 1 ? "Ein Bild" : `${dateien.length} Bilder`} aus der Zwischenablage angehängt.`);
      return;
    }
    const text = daten.getData("text/plain");
    if (text.length >= 6000) {
      ereignis.preventDefault();
      fuegeDateienHinzu([new File([text], "eingefuegter-text.txt", { type: "text/plain" })]);
      melde("Langer Text wurde als Datei angehängt.");
    }
  }

  // ------------------------------------------------------------- Aufträge
  async function senden() {
    if (zustand.live && zustand.live.produktId === zustand.aktuell && zustand.aktuell) {
      abbrechenAuftrag();
      return;
    }
    const text = knoten.eingabe.value.trim();
    if (!text && !zustand.anhaenge.length) return;
    if (!modell()) {
      melde("Bitte zuerst ein Modell wählen.", "fehler");
      return;
    }
    const formular = new FormData();
    formular.append("text", text);
    formular.append("modell", modell());
    // Web: nur wenn eingeschaltet, recherchiert JOSHI aktuelle Daten im Netz.
    if (webAn()) formular.append("web", "1");
    zustand.anhaenge.forEach((a) => formular.append("dateien", a.datei, a.datei.name));
    const produkt = zustand.daten?.produkt;
    const pfad = produkt ? `/api/joshi/produkte/${encodeURIComponent(produkt.id)}/auftrag` : "/api/joshi/produkte";
    if (produkt) formular.append("art", "aendern");
    knoten.empfehlung.hidden = true;
    await sendeFormular(formular, pfad);
  }

  async function sendeFormular(formular, pfad) {
    knoten.senden.disabled = true;
    try {
      const daten = await hole(pfad, { method: "POST", body: formular });
      if (daten.empfehlung) {
        zeigeEmpfehlung(daten.empfehlung, formular, pfad);
        return;
      }
      knoten.eingabe.value = "";
      passeEingabeAn();
      leereAnhaenge();
      await starteBeobachtung(daten);
    } catch (fehler) {
      melde(fehler.message, "fehler");
    } finally {
      aktualisiereSendenKnopf();
    }
  }

  async function starteBeobachtung(daten) {
    const produktId = daten.produkt.id;
    zustand.aktuell = produktId;
    localStorage.setItem(LETZTES_PRODUKT, produktId);
    verbinde(daten.job.id, produktId);
    await ladeProdukte();
    await waehleProdukt(produktId);
    setzeBereich(daten.produkt.version ? "stage" : "dialog");
    starteStatusabfrage();
  }

  function loeseStrom() {
    // Nur das Zuhören endet; der Auftrag läuft auf dem Mac weiter und bleibt
    // über die Statusabfrage im Blick.
    const warLive = Boolean(zustand.live);
    if (zustand.leser) {
      try { zustand.leser.cancel(); } catch (fehler) { /* schon zu */ }
    }
    zustand.leser = null;
    zustand.live = null;
    if (warLive) starteStatusabfrage();
  }

  async function verbinde(jobId, produktId) {
    loeseStrom();
    const live = { jobId, produktId, schritte: [], stufen: [], stufenVon: 0,
      fortschritt: "", hinweise: [], technik: [], tokens: null };
    zustand.live = live;
    // Der Strom beginnt bei Ereignis 0, die echten Werte folgen sofort.
    window.miniLLM?.joshiTokenstand?.({ tokens: 0, sekunden: 0, laufend: true });
    zeichneWerkzeuge();
    if (zustand.aktuell === produktId && zustand.daten) zeichneFeed();
    let antwort;
    try {
      antwort = await fetch(`/api/joshi/auftraege/${encodeURIComponent(jobId)}/ereignisse?ab=0`, { cache: "no-store" });
    } catch (fehler) {
      if (zustand.live === live) setTimeout(() => zustand.live === live && verbinde(jobId, produktId), 3000);
      return;
    }
    if (!antwort.ok || !antwort.body) {
      if (zustand.live === live) zustand.live = null;
      return;
    }
    const leser = antwort.body.getReader();
    zustand.leser = leser;
    const dekodierer = new TextDecoder();
    let puffer = "";
    let beendet = false;
    try {
      while (true) {
        const { value, done } = await leser.read();
        if (done) break;
        puffer += dekodierer.decode(value, { stream: true });
        const zeilen = puffer.split("\n");
        puffer = zeilen.pop();
        for (const zeile of zeilen) {
          if (!zeile.trim()) continue;
          let ereignis;
          try { ereignis = JSON.parse(zeile); } catch (fehler) { continue; }
          if (zustand.live !== live) return;
          if (verarbeite(ereignis, live)) beendet = true;
        }
      }
    } catch (fehler) {
      // Verbindung weg (Netz, Tailscale): neu anmelden, der Auftrag läuft weiter.
      if (zustand.live === live && !beendet) {
        setTimeout(() => zustand.live === live && verbinde(jobId, produktId), 2500);
        return;
      }
    }
    if (zustand.live !== live) return;
    zustand.live = null;
    zustand.leser = null;
    await ladeProdukte();
    if (zustand.aktuell === produktId) await waehleProdukt(produktId);
    aktualisiereKopfstatus();
  }

  // JOSHIs eigener Zähler nutzt die serverseitigen Werte dieses Auftrags.
  const ENDE = ["fertig", "fehler", "abgeschlossen"];
  const ENDSTATUS = ["ready", "needs_attention", "failed", "cancelled"];

  function meldeTokens(ereignis, live, laeuft) {
    if (typeof ereignis.tokens === "number") {
      // Nicht auf die alte Kurzform kürzen: die zentrale Modellschicht liefert
      // bestätigte und geschätzte Ausgabe getrennt. Dieser Stand muss über
      // SSE, Spiegelanzeige und Produkt-Neuladen unverändert erhalten bleiben.
      live.tokens = { ...ereignis, sekunden: ereignis.modellsekunden,
        laufend: ereignis.laufend !== false };
    }
    if (!live.tokens) return;
    window.miniLLM?.joshiTokenstand?.({
      ...live.tokens,
      laufend: laeuft && live.tokens.laufend,
    });
  }

  function verarbeite(ereignis, live) {
    const art = ereignis.type;
    meldeTokens(ereignis, live, !ENDE.includes(art)
      && !(art === "status" && ENDSTATUS.includes(ereignis.status)));
    if (art === "plan") {
      live.schritte = (ereignis.schritte || []).map((s) => ({ ...s, zustand: "offen", detail: "" }));
    } else if (art === "stufen") {
      uebernehmeStufenplan(live, ereignis);
    } else if (art === "stufe") {
      uebernehmeStufe(live, ereignis);
    } else if (art === "schritt") {
      const schritt = live.schritte.find((s) => s.id === ereignis.schritt);
      if (schritt) {
        schritt.zustand = ereignis.zustand;
        schritt.detail = ereignis.text || "";
        if (ereignis.zustand !== "aktiv") live.fortschritt = "";
      }
    } else if (art === "fortschritt") {
      live.fortschritt = ereignis.text || "";
    } else if (art === "hinweis") {
      live.hinweise.push(ereignis.text);
    } else if (art === "technik") {
      live.technik.push(ereignis.text);
    } else if (art === "verstaendnis") {
      ladeProdukte();
      if (zustand.daten?.produkt && zustand.aktuell === live.produktId) {
        zustand.daten.produkt.verstaendnis = ereignis.verstaendnis;
        zustand.daten.produkt.titel = ereignis.titel || zustand.daten.produkt.titel;
        zeichneWerkzeuge();
        zeichneFeed();
      }
    } else if (art === "fertig" || art === "fehler" || art === "abgeschlossen") {
      if (art === "fehler" && ereignis.text) live.hinweise.push(ereignis.text);
      if (ansicht.hidden) zustand.fertigSeitAbwesenheit = true;
      if (art === "fertig") melde(ereignis.text || "Fertig.");
      else if (art === "fehler") melde(ereignis.text || "JOSHI ist gescheitert.", "fehler");
      return true;
    } else if (art === "status" && ENDSTATUS.includes(ereignis.status)) {
      return true;
    }
    if (zustand.aktuell === live.produktId) {
      zeichneLivekarte();
      zeichneFortschritt();
    }
    return false;
  }

  async function abbrechenAuftrag() {
    const live = zustand.live;
    if (!live) return;
    try {
      await hole(`/api/joshi/auftraege/${encodeURIComponent(live.jobId)}/abbrechen`, { method: "POST" });
      melde("JOSHI wird gestoppt …");
    } catch (fehler) {
      melde(fehler.message, "fehler");
    }
  }

  // ----------------------------------------------------- Status im Chat-Kopf
  function zeichneKopfstatus(aktive = null) {
    const laeuft = aktive ? aktive.length > 0 : Boolean(zustand.live);
    let text = "JOSHI";
    let art = "";
    if (laeuft) { text = "JOSHI arbeitet …"; art = "laeuft"; }
    else if (zustand.fertigSeitAbwesenheit) { text = "JOSHI fertig"; art = "fertig"; }
    knoten.oeffnenText.textContent = text;
    knoten.oeffnenPunkt.hidden = !art;
    knoten.oeffnenPunkt.dataset.art = art;
    knoten.oeffnen.classList.toggle("is-active", Boolean(art));
  }

  async function aktualisiereKopfstatus() {
    try {
      const daten = await hole("/api/joshi/status");
      const aktive = daten.aktiv || [];
      if (!aktive.length && zustand.statusUhr && !zustand.live && ansicht.hidden) {
        zustand.fertigSeitAbwesenheit = true;
      }
      zeichneKopfstatus(aktive);
      if (!aktive.length) stoppeStatusabfrage();
      return aktive;
    } catch (fehler) {
      stoppeStatusabfrage();
      return [];
    }
  }

  function starteStatusabfrage() {
    if (zustand.statusUhr) return;
    zustand.statusUhr = setInterval(aktualisiereKopfstatus, 3000);
    zeichneKopfstatus();
  }

  function stoppeStatusabfrage() {
    clearInterval(zustand.statusUhr);
    zustand.statusUhr = null;
  }

  // ------------------------------------------------------------- Aktionen
  function schliesseMenues(ausser = null) {
    [[knoten.exportKnopf, knoten.exportMenue], [knoten.teilenKnopf, knoten.teilenMenue], [knoten.mehrKnopf, knoten.mehrMenue]]
      .forEach(([knopf, menue]) => {
        if (menue === ausser) return;
        menue.hidden = true;
        knopf.setAttribute("aria-expanded", "false");
      });
  }

  function umschalten(knopf, menue) {
    const offen = menue.hidden;
    schliesseMenues(menue);
    menue.hidden = !offen;
    knopf.setAttribute("aria-expanded", String(offen));
  }

  function dateinameAus(antwort, rueckfall) {
    const kopf = antwort.headers.get("Content-Disposition") || "";
    const utf8 = kopf.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf8) {
      try { return decodeURIComponent(utf8[1]); } catch (fehler) { /* weiter */ }
    }
    return kopf.match(/filename="([^"]+)"/i)?.[1] || rueckfall;
  }

  async function ladeHerunter(antwort, rueckfall) {
    const blob = await antwort.blob();
    const url = URL.createObjectURL(blob);
    const link = element("a");
    link.href = url;
    link.download = dateinameAus(antwort, rueckfall);
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    return link.download;
  }

  // ------------------------------------------- Exportwunsch aus der Anwendung
  // Die Anwendung im Sandkasten darf selbst nichts Privilegiertes tun. Sie
  // schickt einen Wunsch, JOSHI prüft ihn, erzeugt die Datei über den Server
  // und bietet sie zum Download an.
  const EXPORTFORMATE = ["pdf", "docx", "png", "jpg"];
  const MAX_GLEICHZEITIG = 2;
  let laufendeExporte = 0;

  function exportAntwort(anfrage, ok, dateiname = "", fehler = "") {
    try {
      knoten.rahmen.contentWindow?.postMessage(
        { joshi: 1, art: "export-antwort", anfrage, ok, dateiname, fehler }, "*");
    } catch (versehen) { /* Rahmen ist weg */ }
  }

  async function exportWunsch(wunsch) {
    const anfrage = String(wunsch.anfrage || "");
    const typ = String(wunsch.typ || "").toLowerCase();
    const produkt = zustand.daten?.produkt;
    if (!EXPORTFORMATE.includes(typ)) return exportAntwort(anfrage, false, "", "Diesen Exporttyp gibt es nicht.");
    if (!produkt || !produkt.version) return exportAntwort(anfrage, false, "", "Es gibt noch keine Version zum Export.");
    // Nur die Version, die gerade wirklich in der Vorschau läuft.
    if (zustand.vorschau.produkt !== produkt.id || zustand.vorschau.version !== produkt.version) {
      return exportAntwort(anfrage, false, "", "Diese Fassung ist nicht die aktive Version.");
    }
    if (laufendeExporte >= MAX_GLEICHZEITIG) return exportAntwort(anfrage, false, "", "Es laufen schon Exporte.");
    const namen = { pdf: "PDF", docx: "Word-Datei", png: "Bild", jpg: "Bild" };
    melde(`${namen[typ]} wird erstellt …`);
    laufendeExporte += 1;
    try {
      const antwort = await fetch(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}/export/${typ}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          version: produkt.version,
          ziel: String(wunsch.ziel || "").slice(0, 200),
          dateiname: String(wunsch.dateiname || "").slice(0, 200),
          titel: String(wunsch.titel || produkt.titel || "").slice(0, 120),
          html: String(wunsch.html || ""),
          css: String(wunsch.css || ""),
        }),
      });
      if (!antwort.ok) {
        let detail = "";
        try { detail = (await antwort.json()).detail; } catch (versehen) { /* leer */ }
        throw new Error(detail || `Export fehlgeschlagen (${antwort.status})`);
      }
      const name = await ladeHerunter(antwort, `joshi.${typ}`);
      melde(`${namen[typ]} ist fertig: ${name}`);
      exportAntwort(anfrage, true, name);
    } catch (fehler) {
      melde(fehler.message, "fehler");
      exportAntwort(anfrage, false, "", fehler.message);
    } finally {
      laufendeExporte -= 1;
    }
  }

  async function exportiere(format) {
    const produkt = zustand.daten?.produkt;
    if (!produkt?.version) return;
    schliesseMenues();
    await speichereZustandJetzt();
    const namen = { png: "Bild", jpg: "Bild", pdf: "PDF", docx: "Word-Dokument", html: "HTML-Anwendung", eml: "E-Mail" };
    melde(`${namen[format]} wird erzeugt …`);
    const breite = zustand.geraet === "phone" ? 390 : 1280;
    try {
      const antwort = await fetch(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}/export/${format}?breite=${breite}`);
      if (!antwort.ok) {
        let detail = "";
        try { detail = (await antwort.json()).detail; } catch (fehler) { /* leer */ }
        throw new Error(detail || `Export fehlgeschlagen (${antwort.status})`);
      }
      const name = await ladeHerunter(antwort, `joshi.${format}`);
      melde(`${namen[format]} ist fertig: ${name}`);
    } catch (fehler) {
      melde(fehler.message, "fehler");
    }
  }

  async function emailVorbereiten() {
    const produkt = zustand.daten?.produkt;
    if (!produkt?.version) return;
    schliesseMenues();
    await speichereZustandJetzt();
    try {
      const vorlage = await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}/email`);
      knoten.mailBetreff.value = vorlage.betreff || produkt.titel;
      knoten.mailText.value = vorlage.text || "";
      knoten.mail.showModal();
    } catch (fehler) {
      melde(fehler.message, "fehler");
    }
  }

  async function imChatBesprechen() {
    const produkt = zustand.daten?.produkt;
    if (!produkt?.version) return;
    await speichereZustandJetzt();
    knoten.besprechen.disabled = true;
    try {
      const daten = await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}/uebergabe`);
      if (!window.miniLLM?.chatMitKontext) throw new Error("Der Chat ist noch nicht bereit.");
      schliesseAnsicht();
      window.miniLLM.chatMitKontext(`Über: ${daten.titel}`, daten.text, produkt.id);
    } catch (fehler) {
      melde(fehler.message, "fehler");
    } finally {
      knoten.besprechen.disabled = false;
    }
  }

  async function rueckgaengig() {
    const produkt = zustand.daten?.produkt;
    if (!produkt) return;
    try {
      await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}/rueckgaengig`, { method: "POST" });
      await waehleProdukt(produkt.id, { vorschauErzwingen: true });
      await ladeProdukte();
      melde(`Zurück auf Version ${zustand.daten.produkt.version}.`);
    } catch (fehler) {
      melde(fehler.message, "fehler");
    }
  }

  async function versionAktivieren(nummer, abgelehnt = false) {
    const produkt = zustand.daten?.produkt;
    if (!produkt) return;
    // Ein abgelehnter Kandidat war nie freigegeben: nur mit ausdrücklicher Zustimmung.
    if (abgelehnt && !window.confirm(`Version ${nummer} hat JOSHIs Prüfung nicht bestanden und war nie freigegeben. `
      + "Export und Teilen verwenden danach diese ungeprüfte Fassung. Trotzdem verwenden?")) return;
    try {
      await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}/versionen/${nummer}/aktivieren${abgelehnt ? "?bewusst=1" : ""}`, { method: "POST" });
      knoten.details.close();
      await waehleProdukt(produkt.id, { vorschauErzwingen: true });
      melde(abgelehnt ? `Version ${nummer} ist aktiv — ungeprüft.` : `Version ${nummer} ist wieder aktiv.`);
    } catch (fehler) {
      melde(fehler.message, "fehler");
    }
  }

  async function mehrAktion(aktion) {
    const produkt = zustand.daten?.produkt;
    schliesseMenues();
    if (!produkt) return;
    if (aktion === "keep") {
      try {
        const daten = await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}`, json("PATCH", { behalten: !produkt.behalten }));
        zustand.daten.produkt = { ...zustand.daten.produkt, ...daten.produkt };
        zeichneWerkzeuge();
        await ladeProdukte();
        melde(daten.produkt.behalten ? "Produkt wird dauerhaft behalten." : "Produkt ist wieder ein Entwurf.");
      } catch (fehler) { melde(fehler.message, "fehler"); }
    } else if (aktion === "versions") {
      oeffneDetails("versionen");
    } else if (aktion === "workspace") {
      const pfadBasis = `/api/joshi/produkte/${encodeURIComponent(produkt.id)}/workspace`;
      if (produkt.quelle?.workspace) {
        try { await hole(`${pfadBasis}/oeffnen`, { method: "POST" }); } catch (fehler) { melde(fehler.message, "fehler"); }
        return;
      }
      if (!window.confirm(`„${produkt.titel}“ in den Projekt-Workspace überführen? Die aktive Version bleibt, `
        + "JOSHI legt einen Projektordner mit index.html, Assets und Dokumentation an.")) return;
      if (!ordner.einstellungen?.workspace?.aktiv && !(await speichereOrdner("workspace", { aktiv: true }))) return;
      try {
        const antwort = await hole(pfadBasis, { method: "POST" });
        zustand.daten.produkt = { ...zustand.daten.produkt, ...antwort.produkt };
        zeichneWerkzeuge();
        zeichneOrdner();
        melde(`Projekt angelegt: ${antwort.workspace.pfad}`);
      } catch (fehler) { melde(fehler.message, "fehler"); }
    } else if (aktion === "details") {
      oeffneDetails("bericht");
    } else if (aktion === "delete") {
      if (!window.confirm(`„${produkt.titel}“ mit allen Versionen löschen?`)) return;
      try {
        await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}`, { method: "DELETE" });
        await ladeProdukte();
        zeigeNeu();
        melde("Produkt gelöscht.");
      } catch (fehler) { melde(fehler.message, "fehler"); }
    }
  }

  // --------------------------------------------------- Technische Details
  // Kompakt, was ein Versuch war: Linie, Umfang, Ausgabe, Patch, Abnahme.
  function diagnoseTabelle(d) {
    const zahlDE = (n) => Number(n || 0).toLocaleString("de-DE");
    const patch = d.patch || {};
    const abnahme = d.abnahme || {};
    const gesamttokens = d.tokens || {};
    const ausgabeIst = gesamttokens.output_tokens_actual ?? gesamttokens.tokens_actual ?? d.ausgabe_tokens ?? 0;
    const ausgabeGeschaetzt = gesamttokens.output_tokens_estimated || 0;
    const ausgabeUnvollstaendig = gesamttokens.output_tokens_incomplete || gesamttokens.abgebrochen_geschaetzt || 0;
    const tokenTeile = [];
    if (ausgabeIst) tokenTeile.push(`${zahlDE(ausgabeIst)} bestätigt`);
    if (ausgabeGeschaetzt) tokenTeile.push(`≈ ${zahlDE(ausgabeGeschaetzt)} geschätzt`);
    if (ausgabeUnvollstaendig) tokenTeile.push(`≈ ${zahlDE(ausgabeUnvollstaendig)} unvollständig`);
    const stufenUsage = (d.stufen || []).map((stufe) => {
      const u = stufe.usage || {};
      const ist = u.output_tokens_actual ?? u.ausgabe ?? 0;
      const geschaetzt = u.output_tokens_estimated ?? u.geschaetzt_abgeschlossen ?? 0;
      const unvollstaendig = u.output_tokens_incomplete ?? u.geschaetzt_abgebrochen ?? 0;
      const teile = [];
      if (ist) teile.push(`${zahlDE(ist)} bestätigt`);
      if (geschaetzt) teile.push(`≈ ${zahlDE(geschaetzt)} geschätzt`);
      if (unvollstaendig) teile.push(`≈ ${zahlDE(unvollstaendig)} unvollständig`);
      if (!teile.length) teile.push("keine Ausgabe-Usage");
      const status = u.usage_status && u.usage_status !== "actual" ? ` · ${u.usage_status}` : "";
      const aufrufe = u.aufrufe ? ` · ${u.aufrufe} Aufrufe` : "";
      const sekunden = u.modellsekunden ?? u.sekunden;
      return `Schritt ${stufe.nummer || "?"}: ${teile.join(" + ")}${status}${aufrufe}`
        + (sekunden ? ` · ${zahlDE(sekunden)} s` : "");
    }).join(" | ");
    const zeilen = [
      ["Versuch", `${d.versuch || 1}${d.aenderung ? ` · Auftrag ${String(d.aenderung).slice(0, 8)}` : ""}`],
      ["Root-Vertrag", d.kriterien ? `${d.kriterien} Kriterien${d.pflicht ? ` (${d.pflicht} Pflicht)` : ""}` : "–"],
      ["Schritte", d.gestuft ? `gestuft · ${d.stufe || "–"}` : "eine Änderung"],
      ["Ausgabe", `${zahlDE(d.ausgabe_zeichen)} Zeichen · ${tokenTeile.join(" + ") || `${zahlDE(d.ausgabe_tokens)} Tokens`}`
        + ` · Ende: ${d.grund || "–"}`],
      ...(stufenUsage ? [["Usage je Stage", stufenUsage]] : []),
      ["Patch", patch.status ? `${patch.status} · ${patch.angewendet || 0}/${patch.bloecke || 0} Blöcke · ${patch.konflikte || 0} Konflikte` : "–"],
      ["Abnahme", abnahme.PASS !== undefined ? `PASS ${abnahme.PASS} · FAIL ${abnahme.FAIL} · NOT_PROVEN ${abnahme.NOT_PROVEN}` : "–"],
      ["Reparaturen", String(d.reparaturen || 0)],
      ["Befördert", d.befoerdert ? "ja" : "nein"],
    ];
    const tabelle = element("dl", "joshi-diagnose");
    zeilen.forEach(([name, wert]) => tabelle.append(element("dt", "", name), element("dd", "", wert)));
    return tabelle;
  }

  let detailsAuftrag = "";
  async function oeffneDetails(tab = "bericht", auftragId = "") {
    detailsAuftrag = auftragId;
    knoten.detailsTitel.textContent = zustand.daten?.produkt?.titel || "Technische Details";
    if (!knoten.details.open) knoten.details.showModal();
    zeigeDetailTab(tab);
  }

  async function zeigeDetailTab(tab) {
    knoten.details.querySelectorAll(".joshi-tabs button").forEach((k) => k.classList.toggle("is-active", k.dataset.tab === tab));
    const inhalt = knoten.detailsInhalt;
    inhalt.innerHTML = "";
    knoten.codeKopieren.hidden = tab !== "code";
    const produkt = zustand.daten?.produkt;
    if (!produkt) return;
    if (tab === "bericht") {
      const pruefung = zustand.daten.pruefung || {};
      inhalt.append(element("p", "joshi-detail-lead", pruefung.kurz || "Noch keine Prüfung."));
      if (pruefung.browser === false) inhalt.append(element("p", "joshi-detail-note", "Ohne WebKit-Renderer wurde nur statisch geprüft."));
      const interaktion = pruefung.interaktion || {};
      if (Object.keys(interaktion).length) {
        inhalt.append(element("p", "joshi-detail-note",
          `Bedienprobe: ${interaktion.gefuellt || 0} von ${interaktion.felder || 0} Feldern gefüllt, ${interaktion.geklickt || 0} von ${interaktion.knoepfe || 0} Knöpfen geklickt · Reaktion: ${interaktion.reaktionEingabe || interaktion.reaktionKlick ? "ja" : "nein"} · ${pruefung.dauer || 0} s`));
      }
      const liste = element("ul", "joshi-findings");
      (pruefung.befunde || []).forEach((befund) => {
        const eintrag = element("li", `is-${befund.art}`);
        eintrag.append(element("strong", "", befund.text));
        if (befund.technik) eintrag.append(element("code", "", befund.technik));
        liste.append(eintrag);
      });
      if (!(pruefung.befunde || []).length && pruefung.ok) liste.append(element("li", "is-ok", "Keine Befunde."));
      inhalt.append(liste);
    } else if (tab === "ablauf") {
      const auftraege = zustand.daten.auftraege || [];
      const auftrag = auftraege.find((a) => a.id === detailsAuftrag) || auftraege[auftraege.length - 1];
      if (!auftrag) { inhalt.append(element("p", "", "Noch kein Auftrag.")); return; }
      inhalt.append(element("p", "joshi-detail-lead", `${auftrag.text || ""}`.slice(0, 300)));
      const diagnose = auftrag.diagnose || {};
      if (Object.keys(diagnose).length) inhalt.append(diagnoseTabelle(diagnose));
      const protokoll = element("pre", "joshi-log", "Wird geladen …");
      inhalt.append(protokoll);
      const zeilen = [];
      if (zustand.live?.jobId === auftrag.id) {
        zustand.live.technik.forEach((t) => zeilen.push(t));
        protokoll.textContent = zeilen.join("\n") || "Noch keine technischen Meldungen.";
        return;
      }
      try {
        const antwort = await fetch(`/api/joshi/auftraege/${encodeURIComponent(auftrag.id)}/ereignisse?ab=0`);
        const text = await antwort.text();
        text.split("\n").filter(Boolean).forEach((zeile) => {
          try {
            const e = JSON.parse(zeile);
            if (e.type === "technik") zeilen.push(e.text);
            else if (e.type === "schritt") zeilen.push(`[${e.zustand}] ${e.schritt}${e.text ? ` – ${e.text}` : ""}`);
            else if (e.type === "hinweis" || e.type === "fehler") zeilen.push(`» ${e.text}${e.technik ? `\n  ${e.technik}` : ""}`);
          } catch (fehler) { /* Zeile überspringen */ }
        });
        const verbrauch = auftrag.verbrauch || {};
        zeilen.push("", `Modell: ${auftrag.modell} · Aufrufe: ${verbrauch.calls || 0} · Eingabe: ${(verbrauch.prompt_tokens || 0).toLocaleString("de-DE")} · Ausgabe: ${(verbrauch.completion_tokens || 0).toLocaleString("de-DE")} Tokens`);
        protokoll.textContent = zeilen.join("\n");
      } catch (fehler) {
        protokoll.textContent = fehler.message;
      }
    } else if (tab === "code") {
      const code = element("pre", "joshi-code", "Wird geladen …");
      inhalt.append(code);
      try {
        const daten = await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}/quelltext`);
        code.textContent = daten.html;
        knoten.codeKopieren.onclick = async () => {
          await navigator.clipboard.writeText(daten.html);
          melde("Code kopiert.");
        };
      } catch (fehler) {
        code.textContent = fehler.message;
      }
    } else if (tab === "versionen") {
      const liste = element("ol", "joshi-versions");
      (zustand.daten.versionen || []).slice().reverse().forEach((version) => {
        const eintrag = element("li", version.nummer === produkt.version ? "is-current" : "");
        const text = element("div");
        const guete = version.abgelehnt ? "✕ abgelehnter Kandidat · nie freigegeben"
          : version.ok ? "✓ geprüft" : "! mit Befunden";
        if (version.abgelehnt) eintrag.classList.add("is-rejected");
        text.append(element("strong", "", `Version ${version.nummer}${version.nummer === produkt.version ? " · aktiv" : ""}`),
          element("span", "", version.aenderung || ""),
          element("small", "", `${guete} · ${zeitText(version.erstellt)} · ${version.modell}`));
        eintrag.append(text);
        if (version.nummer !== produkt.version) {
          const knopf = element("button", "secondary-button", version.abgelehnt ? "Trotzdem verwenden …" : "Zurückholen");
          knopf.type = "button";
          knopf.addEventListener("click", () => versionAktivieren(version.nummer, Boolean(version.abgelehnt)));
          eintrag.append(knopf);
        }
        liste.append(eintrag);
      });
      inhalt.append(liste);
    }
  }

  // ------------------------------------------------------- Chat → JOSHI
  async function ausChat(daten) {
    const auswahl = modell();
    if (!auswahl) {
      melde("Bitte zuerst ein Modell wählen.", "fehler");
      return;
    }
    oeffneAnsicht({ auswahl: false });
    zeigeNeu();
    const formular = new FormData();
    formular.append("text", "");
    formular.append("modell", auswahl);
    formular.append("chat", JSON.stringify(daten));
    try {
      const antwort = await hole("/api/joshi/produkte", { method: "POST", body: formular });
      await starteBeobachtung(antwort);
      melde("JOSHI übernimmt die Idee aus dem Chat.");
    } catch (fehler) {
      melde(fehler.message, "fehler");
    }
  }

  // ------------------------------------------------------------- Eingabe
  function passeEingabeAn() {
    knoten.eingabe.style.height = "auto";
    knoten.eingabe.style.height = `${Math.min(200, Math.max(44, knoten.eingabe.scrollHeight))}px`;
    aktualisiereSendenKnopf();
  }

  // ----------------------------------------------------------- Anbindung
  knoten.oeffnen.addEventListener("click", () => oeffneAnsicht());
  knoten.zurueck.addEventListener("click", schliesseAnsicht);
  knoten.neu.addEventListener("click", () => { zeigeNeu(); zeigeProduktliste(false); knoten.eingabe.focus(); });
  knoten.produkteKnopf.addEventListener("click", () => zeigeProduktliste(!knoten.produkte.classList.contains("is-open")));
  knoten.produkteSchleier.addEventListener("click", () => zeigeProduktliste(false));
  knoten.form.addEventListener("submit", (ereignis) => { ereignis.preventDefault(); senden(); });
  knoten.eingabe.addEventListener("input", passeEingabeAn);
  knoten.eingabe.addEventListener("input", zeigeVorschlaege);
  knoten.eingabe.addEventListener("blur", () => setTimeout(() => { knoten.vorschlaege.hidden = true; }, 150));
  ansicht.querySelectorAll(".joshi-panel-titel").forEach((knopf) => knopf.addEventListener("click", () => {
    const inhalt = knopf.closest(".joshi-panel").querySelector(".joshi-panel-inhalt");
    panelOeffnen(knopf.dataset.panel, inhalt.hidden);
  }));
  panelZustandLaden();
  knoten.eingabenAn.addEventListener("change", () => schalteOrdner("eingaben", knoten.eingabenAn.checked));
  knoten.workspaceAn.addEventListener("change", () => schalteOrdner("workspace", knoten.workspaceAn.checked));
  [["eingaben", knoten.eingabenPfad], ["workspace", knoten.workspacePfad]].forEach(([bereich, feld]) => {
    feld.addEventListener("keydown", (ereignis) => {
      if (ereignis.key === "Enter") { ereignis.preventDefault(); feld.blur(); }
    });
    feld.addEventListener("change", () => speichereOrdner(bereich, { pfad: feld.value }));
  });
  ansicht.querySelectorAll("[data-pfad]").forEach((knopf) => knopf.addEventListener("click", async () => {
    const bereich = knopf.dataset.pfad;
    const feld = bereich === "eingaben" ? knoten.eingabenPfad : knoten.workspacePfad;
    // Der Dienst läuft auf demselben Mac wie die Ordner. Die native Auswahl
    // kennt auch „Neuer Ordner“ und liefert den absoluten Pfad zurück. Falls
    // der Browser nicht auf dem Mac läuft, bleibt der Pfad direkt editierbar.
    const textVorher = knopf.textContent;
    knopf.disabled = true;
    knopf.textContent = "Wähle …";
    try {
      const daten = await hole(`/api/joshi/ordner/${bereich}/auswaehlen`, { method: "POST" });
      if (!daten.abgebrochen && daten.einstellungen) {
        ordner.einstellungen = daten.einstellungen;
        zeichneOrdner();
        await ladeEingaben();
        panelOeffnen(bereich, true);
        melde(`${bereich === "eingaben" ? "Assets / Eingaben" : "Projekt-Workspace"} ausgewählt: ${daten.pfad}`);
      } else if (daten.abgebrochen) {
        melde("Keine Auswahl übernommen. Im Dialog „Auswählen“ bestätigen — X bricht die Auswahl ab.");
      }
    } catch (fehler) {
      // Manuelle Eingabe bleibt als Fallback möglich und wird beim Verlassen
      // des Feldes wie bisher validiert und gespeichert.
      melde(`${fehler.message} Pfad kann unten auch direkt eingegeben werden.`, "fehler");
      feld.focus();
      feld.select();
    } finally {
      knopf.disabled = false;
      knopf.textContent = textVorher;
    }
  }));
  ansicht.querySelectorAll("[data-oeffnen]").forEach((knopf) => knopf.addEventListener("click", async () => {
    try { await hole(`/api/joshi/ordner/${knopf.dataset.oeffnen}/oeffnen`, { method: "POST" }); melde("Ordner im Finder geöffnet. Zum Ändern bitte „Ordner auswählen“ verwenden."); }
    catch (fehler) { melde(fehler.message, "fehler"); }
  }));
  ansicht.querySelectorAll("[data-import]").forEach((knopf) => knopf.addEventListener("click", () => {
    const input = knopf.dataset.import === "eingaben" ? knoten.eingabenUpload : knoten.workspaceUpload;
    input?.click();
  }));
  knoten.eingabenUpload?.addEventListener("change", () => {
    importiereOrdnerDateien("eingaben", knoten.eingabenUpload.files);
    knoten.eingabenUpload.value = "";
  });
  knoten.workspaceUpload?.addEventListener("change", () => {
    importiereOrdnerDateien("workspace", knoten.workspaceUpload.files);
    knoten.workspaceUpload.value = "";
  });
  $$("#joshi-eingaben-neu").addEventListener("click", () => ladeEingaben({ melden: true }));
  knoten.eingabe.addEventListener("paste", zwischenablage);
  knoten.eingabe.addEventListener("keydown", (ereignis) => {
    if (ereignis.key === "Enter" && !ereignis.shiftKey && !ereignis.isComposing && window.matchMedia("(hover: hover)").matches) {
      ereignis.preventDefault();
      senden();
    }
  });
  knoten.anhangKnopf.addEventListener("click", () => knoten.dateiEingabe.click());
  knoten.dateiEingabe.addEventListener("change", () => fuegeDateienHinzu(knoten.dateiEingabe.files));
  knoten.modell.addEventListener("change", () => {
    const quelle = $$("#model");
    if (quelle && quelle.value !== knoten.modell.value) {
      quelle.value = knoten.modell.value;
      quelle.dispatchEvent(new Event("change"));
    }
    aktualisiereSendenKnopf();
  });
  $$("#model")?.addEventListener("change", () => { if (!ansicht.hidden) spiegleModelle(); });
  window.addEventListener("mini-llm-modelle", spiegleModelle);

  // Dateien, die auf JOSHI fallen, gehören JOSHI – nicht dem Chat darunter.
  ["dragenter", "dragover", "dragleave", "drop"].forEach((art) => {
    window.addEventListener(art, (ereignis) => {
      if (ansicht.hidden || !ereignis.dataTransfer?.types.includes("Files")) return;
      ereignis.preventDefault();
      ereignis.stopImmediatePropagation();
      if (art === "dragenter" || art === "dragover") {
        ereignis.dataTransfer.dropEffect = "copy";
        knoten.ablage.classList.add("is-dragging");
      } else {
        knoten.ablage.classList.remove("is-dragging");
      }
      if (art === "drop") {
        fuegeDateienHinzu(ereignis.dataTransfer.files);
        setzeBereich("dialog");
      }
    }, true);
  });

  ansicht.querySelector("#joshi-examples").addEventListener("click", (ereignis) => {
    const beispiel = ereignis.target.closest("button");
    if (!beispiel) return;
    knoten.eingabe.value = beispiel.textContent.trim();
    passeEingabeAn();
    setzeBereich("dialog");
    knoten.eingabe.focus();
  });
  knoten.titel.addEventListener("change", async () => {
    const produkt = zustand.daten?.produkt;
    const titel = knoten.titel.value.trim();
    if (!produkt || !titel || titel === produkt.titel) return;
    try {
      const daten = await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}`, json("PATCH", { titel }));
      zustand.daten.produkt = { ...produkt, ...daten.produkt };
      await ladeProdukte();
    } catch (fehler) { melde(fehler.message, "fehler"); }
  });
  knoten.titel.addEventListener("keydown", (ereignis) => { if (ereignis.key === "Enter") knoten.titel.blur(); });
  knoten.rueckgaengig.addEventListener("click", rueckgaengig);
  knoten.exportKnopf.addEventListener("click", () => umschalten(knoten.exportKnopf, knoten.exportMenue));
  knoten.teilenKnopf.addEventListener("click", () => umschalten(knoten.teilenKnopf, knoten.teilenMenue));
  knoten.mehrKnopf.addEventListener("click", () => umschalten(knoten.mehrKnopf, knoten.mehrMenue));
  ansicht.querySelectorAll("[data-export]").forEach((knopf) => knopf.addEventListener("click", () => exportiere(knopf.dataset.export)));
  ansicht.querySelector('[data-action="email"]').addEventListener("click", emailVorbereiten);
  knoten.mehrMenue.querySelectorAll("[data-action]").forEach((knopf) => knopf.addEventListener("click", () => mehrAktion(knopf.dataset.action)));
  knoten.besprechen.addEventListener("click", imChatBesprechen);
  knoten.neuLaden.addEventListener("click", async () => {
    await speichereZustandJetzt();
    if (zustand.daten?.produkt) zeigeVorschau(zustand.daten.produkt.id, zustand.daten.produkt.version);
  });
  ansicht.querySelectorAll(".joshi-devices button").forEach((knopf) => knopf.addEventListener("click", () => setzeGeraet(knopf.dataset.geraet)));
  ansicht.querySelectorAll(".joshi-tabs-mobile button").forEach((knopf) => knopf.addEventListener("click", () => setzeBereich(knopf.dataset.bereich)));
  $$("#joshi-runtime-fix").addEventListener("click", async () => {
    const produkt = zustand.daten?.produkt;
    if (!produkt || !zustand.laufzeitFehler.length) return;
    knoten.laufzeitFehler.hidden = true;
    const formular = new FormData();
    formular.append("art", "reparieren");
    formular.append("modell", modell());
    formular.append("fehler", zustand.laufzeitFehler.slice(0, 4).join("\n"));
    try {
      const daten = await hole(`/api/joshi/produkte/${encodeURIComponent(produkt.id)}/auftrag`, { method: "POST", body: formular });
      await starteBeobachtung(daten);
    } catch (fehler) { melde(fehler.message, "fehler"); }
  });
  $$("#joshi-runtime-dismiss").addEventListener("click", () => { knoten.laufzeitFehler.hidden = true; });
  knoten.details.querySelectorAll(".joshi-tabs button").forEach((knopf) => knopf.addEventListener("click", () => zeigeDetailTab(knopf.dataset.tab)));
  [knoten.details, knoten.mail].forEach((dialog) => {
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
  });
  $$("#joshi-mail-copy").addEventListener("click", async () => {
    await navigator.clipboard.writeText(`${knoten.mailBetreff.value}\n\n${knoten.mailText.value}`);
    melde("E-Mail-Text kopiert.");
  });
  $$("#joshi-mail-html").addEventListener("click", () => exportiere("html"));
  $$("#joshi-mail-eml").addEventListener("click", () => {
    // Die EML-Datei enthält die Anwendung als Anhang; Mail öffnet sie als Entwurf.
    exportiere("eml");
    knoten.mail.close();
  });
  document.addEventListener("click", (ereignis) => {
    if (!ereignis.target.closest(".joshi-menu")) schliesseMenues();
  });
  document.addEventListener("keydown", (ereignis) => {
    if (ereignis.key !== "Escape" || ansicht.hidden) return;
    if (knoten.details.open || knoten.mail.open || $$("#model-manager")?.open) return;
    if (!knoten.exportMenue.hidden || !knoten.teilenMenue.hidden || !knoten.mehrMenue.hidden) {
      schliesseMenues();
      return;
    }
    schliesseAnsicht();
  });
  window.addEventListener("mini-llm-auth", () => {
    spiegleModelle();
    aktualisiereKopfstatus().then((aktive) => { if (aktive.length) starteStatusabfrage(); });
  });
  window.addEventListener("pagehide", speichereZustandJetzt);

  setzeGeraet("desktop");
  setzeBereich("stage");
  beobachteAnzeigen();
  window.joshi = { ausChat, oeffnen: () => oeffneAnsicht() };
})();
