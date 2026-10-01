// Mini LLM – powered by AI-Implements · C. Lins
// Copyright (c) 2026 C. Lins / AI-Implements – MIT-Lizenz, siehe LICENSE.
// Dieser Code darf frei verwendet, verändert und erweitert werden.
// Dieser Hinweis muss in allen Kopien und abgeleiteten Werken erhalten bleiben.
/* Modellverwaltung: installierte Ollama-Modelle, Hardwareeignung, „ollama pull“.
 *
 * Früher Teil der Coding-Ansicht; jetzt eigenständig und von überall zu öffnen
 * (Knöpfe mit data-open-models: Steuerzentrale im Chat, Kopfzeile von JOSHI).
 */
(() => {
  const $$ = (auswahl) => document.querySelector(auswahl);
  const dialog = $$("#model-manager");
  if (!dialog) return;
  const PULLSCHLUESSEL = "mini-llm-ollama-pull";
  const zustand = { pullJobId: localStorage.getItem(PULLSCHLUESSEL) || "", pullUhr: null };
  const knoten = {
    schliessen: $$("#model-manager-close"),
    aktualisieren: $$("#model-manager-refresh"),
    hardware: $$("#model-hardware-summary"),
    liste: $$("#model-list"),
    log: $$("#ollama-log"),
    form: $$("#ollama-form"),
    befehl: $$("#ollama-command"),
    fortschritt: $$("#ollama-pull-progress"),
  };

  async function hole(pfad, einstellungen = {}) {
    const antwort = await fetch(pfad, {
      headers: { "Content-Type": "application/json" },
      ...einstellungen,
    });
    let daten = {};
    try { daten = await antwort.json(); } catch (fehler) { /* leer */ }
    if (!antwort.ok) throw new Error(daten.detail || `Fehler ${antwort.status}`);
    return daten;
  }

  function formatiereGroesse(bytes) {
    const wert = Number(bytes) || 0;
    if (!wert) return "–";
    return `${(wert / 1024 ** 3).toFixed(1).replace(".", ",")} GB`;
  }

  function fitSymbol(status) {
    return { good: "🟢", tight: "🟡", "too-large": "🔴", cloud: "☁️" }[status] || "⚪";
  }

  // Schreibt die Liste in die Modellauswahl des Chats; JOSHI spiegelt sie.
  function schreibeModellAuswahl(modelle) {
    const auswahl = $$("#model");
    if (!auswahl) return;
    const vorher = auswahl.value || localStorage.getItem("mini-llm-model") || "";
    auswahl.innerHTML = "";
    if (!modelle.length) {
      auswahl.add(new Option("Keine Modelle installiert", ""));
    } else {
      modelle.forEach((modell) => {
        const option = new Option(`${fitSymbol(modell.fit?.status)} ${modell.name}`, modell.name);
        option.className = `model-fit-${modell.fit?.status || "unknown"}`;
        option.title = `${modell.fit?.label || "Größe unbekannt"} · ${formatiereGroesse(modell.size)}`;
        auswahl.add(option);
      });
      if (modelle.some((modell) => modell.name === vorher)) auswahl.value = vorher;
    }
    window.dispatchEvent(new CustomEvent("mini-llm-modelle"));
  }

  function zeichneListe(modelle) {
    knoten.liste.innerHTML = "";
    if (!modelle.length) {
      knoten.liste.innerHTML = '<p class="model-empty">Noch keine Modelle installiert.</p>';
      return;
    }
    modelle.forEach((modell) => {
      const eintrag = document.createElement("div");
      eintrag.className = "model-item";
      const punkt = document.createElement("i");
      punkt.className = modell.fit?.status || "unknown";
      const mitte = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = modell.name;
      const hinweis = document.createElement("small");
      const parameter = modell.details?.parameter_size ? `${modell.details.parameter_size} · ` : "";
      hinweis.textContent = `${parameter}${modell.fit?.label || "Größe unbekannt"}`;
      mitte.append(name, hinweis);
      const groesse = document.createElement("span");
      groesse.className = "model-size";
      groesse.textContent = formatiereGroesse(modell.size);
      eintrag.append(punkt, mitte, groesse);
      knoten.liste.append(eintrag);
    });
  }

  async function aktualisieren() {
    knoten.aktualisieren.disabled = true;
    try {
      const daten = await hole("/api/ollama/manager");
      const gb = formatiereGroesse(daten.hardware?.memory_total_bytes);
      const kerne = daten.hardware?.cpu_count || "–";
      const architektur = daten.hardware?.architecture || "Mac";
      knoten.hardware.textContent = `${architektur} · ${gb} RAM · ${kerne} logische CPU-Kerne`;
      zeichneListe(daten.models || []);
      schreibeModellAuswahl(daten.models || []);
      const aktiv = (daten.pulls || []).find((job) => ["queued", "pulling"].includes(job.status));
      if (aktiv) beobachtePull(aktiv.jobId);
    } catch (fehler) {
      knoten.liste.innerHTML = '<p class="model-empty"></p>';
      knoten.liste.querySelector("p").textContent = fehler.message;
      knoten.log.textContent = `Fehler: ${fehler.message}`;
    } finally {
      knoten.aktualisieren.disabled = false;
    }
  }

  function zeigePull(job) {
    knoten.log.textContent = (job.logs || []).join("\n");
    knoten.log.scrollTop = knoten.log.scrollHeight;
    const laeuft = ["queued", "pulling"].includes(job.status);
    const anteil = job.total ? Math.min(100, Math.round(job.current / job.total * 100)) : 0;
    knoten.fortschritt.hidden = !laeuft;
    knoten.fortschritt.querySelector("span").style.width = `${anteil}%`;
    knoten.form.querySelector("button").disabled = laeuft;
  }

  function beobachtePull(jobId) {
    if (!jobId) return;
    zustand.pullJobId = jobId;
    localStorage.setItem(PULLSCHLUESSEL, jobId);
    clearInterval(zustand.pullUhr);
    let beschaeftigt = false;
    const pruefe = async () => {
      if (beschaeftigt) return;
      beschaeftigt = true;
      try {
        const daten = await hole(`/api/ollama/pulls/${jobId}`);
        zeigePull(daten.job);
        if (!["queued", "pulling"].includes(daten.job.status)) {
          clearInterval(zustand.pullUhr);
          zustand.pullUhr = null;
          localStorage.removeItem(PULLSCHLUESSEL);
          zustand.pullJobId = "";
          if (daten.job.status === "done") await aktualisieren();
        }
      } catch (fehler) {
        clearInterval(zustand.pullUhr);
        zustand.pullUhr = null;
        knoten.log.textContent += `\nFehler: ${fehler.message}`;
      } finally {
        beschaeftigt = false;
      }
    };
    pruefe();
    zustand.pullUhr = setInterval(pruefe, 900);
  }

  async function oeffnen() {
    if (!dialog.open) dialog.showModal();
    await aktualisieren();
    if (zustand.pullJobId) beobachtePull(zustand.pullJobId);
    knoten.befehl.focus();
  }

  document.addEventListener("click", (ereignis) => {
    if (ereignis.target.closest("[data-open-models]")) oeffnen();
  });
  knoten.schliessen.addEventListener("click", () => dialog.close());
  knoten.aktualisieren.addEventListener("click", aktualisieren);
  knoten.form.addEventListener("submit", async (ereignis) => {
    ereignis.preventDefault();
    const befehl = knoten.befehl.value.trim();
    if (!befehl) return;
    knoten.form.querySelector("button").disabled = true;
    try {
      const daten = await hole("/api/ollama/pull", { method: "POST", body: JSON.stringify({ command: befehl }) });
      knoten.befehl.value = "";
      zeigePull(daten.job);
      beobachtePull(daten.job.jobId);
    } catch (fehler) {
      knoten.log.textContent += `\nFehler: ${fehler.message}`;
      knoten.form.querySelector("button").disabled = false;
    }
  });
  window.miniLLMModelle = { oeffnen };
})();
