"use strict";

const TOKEN = document.querySelector('meta[name="factory-token"]').content;
const app = document.getElementById("app");
let pollTimer = null;
let currentView = null;

// ---------------------------------------------------------------- helpers

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

async function api(method, path, body) {
  const response = await fetch("/api" + path, {
    method,
    headers: { "Content-Type": "application/json", "X-Factory-Token": TOKEN },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "Erreur " + response.status);
  }
  return data;
}

function render(html) {
  app.innerHTML = html;
}

function showError(target, error) {
  const box = document.getElementById(target);
  if (box) {
    box.innerHTML = '<div class="notice danger" role="alert">' + esc(error.message || error) + "</div>";
  }
}

function busy(button, label) {
  if (button) {
    button.disabled = true;
    button.textContent = label;
  }
}

function stopPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

// ---------------------------------------------------------------- routing

async function route() {
  stopPolling();
  const hash = location.hash.replace(/^#/, "") || "/";
  const parts = hash.split("/").filter(Boolean);

  try {
    if (parts[0] === "projects" && parts[1]) {
      await showProject(parts[1]);
    } else if (parts[0] === "projects") {
      await showProjects();
    } else if (parts[0] === "settings") {
      await showSettings();
    } else {
      await showHome();
    }
  } catch (error) {
    render('<div class="narrow"><div class="notice danger" role="alert">' + esc(error.message) + "</div></div>");
  }
  app.focus({ preventScroll: true });
}

window.addEventListener("hashchange", route);

// ---------------------------------------------------------------- home

async function showHome() {
  const settings = await api("GET", "/settings");
  const keyMissing = settings.provider === "openai" && !settings.api_key_set;

  render(`
    <div class="narrow">
      <div style="display:flex;flex-direction:column;gap:12px">
        <h1>Qu'est-ce que tu veux construire&#8239;?</h1>
        <p class="lead">Décris ton idée avec tes mots. Une équipe d'agents (produit, design, architecture, code, tests, sécurité) te posera ses questions, puis construira le projet étape par étape. Tu valides chaque étape.</p>
      </div>
      ${keyMissing ? '<div class="notice warn">Avant de commencer, ajoute ta clé OpenAI dans les <a href="#/settings">réglages</a>. Pour juste essayer, choisis le « Mode démo » dans les réglages : c\'est gratuit.</div>' : ""}
      <form class="card" id="new-project">
        <label class="field">Nom du projet
          <input type="text" name="name" required maxlength="80" placeholder="Exemple : Réservations Salon">
        </label>
        <label class="field">Ton idée
          <textarea name="idea" rows="5" required placeholder="Exemple : une application pour gérer les réservations de mon salon de coiffure. Les clientes choisissent un créneau en ligne, je reçois une notification et je vois mon planning de la semaine."></textarea>
        </label>
        <fieldset style="border:0;margin:0;padding:0;display:flex;flex-direction:column;gap:10px">
          <legend class="field" style="font-weight:600;font-size:14px;margin-bottom:10px">Ton profil</legend>
          <div class="choices">
            <button type="button" class="choice" data-profile="novice" aria-pressed="true"><strong>Je ne code pas</strong><span>Le moteur choisit la technique pour moi et m'explique ses choix simplement.</span></button>
            <button type="button" class="choice" data-profile="developer" aria-pressed="false"><strong>Je suis développeur</strong><span>Je choisis ma stack et je vois tout le détail technique.</span></button>
          </div>
        </fieldset>
        <div id="form-error"></div>
        <div class="row spread">
          <span class="muted">Les agents te poseront leurs questions au fil du projet.</span>
          <button type="submit" class="btn primary">Lancer le projet</button>
        </div>
      </form>
    </div>`);

  let profile = "novice";
  app.querySelectorAll("[data-profile]").forEach((button) => {
    button.addEventListener("click", () => {
      profile = button.dataset.profile;
      app.querySelectorAll("[data-profile]").forEach((other) => {
        other.setAttribute("aria-pressed", String(other === button));
      });
    });
  });

  document.getElementById("new-project").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const submit = form.querySelector('button[type="submit"]');
    busy(submit, "Création…");
    try {
      const view = await api("POST", "/projects", {
        name: form.name.value,
        idea: form.idea.value,
        profile,
      });
      location.hash = "#/projects/" + view.id;
    } catch (error) {
      submit.disabled = false;
      submit.textContent = "Lancer le projet";
      showError("form-error", error);
    }
  });
}

// ---------------------------------------------------------------- projects

async function showProjects() {
  const data = await api("GET", "/projects");
  const items = data.projects
    .map((p) => `<a href="#/projects/${esc(p.id)}"><strong>${esc(p.name)}</strong><span class="muted">${esc(phaseLabel(p.phase))}</span></a>`)
    .join("");

  render(`
    <div class="narrow">
      <h1>Mes projets</h1>
      <div class="card">
        ${items ? `<div class="project-list">${items}</div>` : '<p class="muted">Aucun projet pour l\'instant. <a href="#/">Crée le premier</a>.</p>'}
      </div>
    </div>`);
}

function phaseLabel(phase) {
  const labels = {
    discovery: "Cadrage", design: "Design", architecture: "Architecture",
    implementation: "Développement", qa: "Tests", security: "Sécurité",
    devops: "Livraison", sre: "Fiabilité", completed: "Terminé",
  };
  return labels[phase] || phase || "";
}

// ---------------------------------------------------------------- settings

async function showSettings() {
  const settings = await api("GET", "/settings");

  render(`
    <div class="narrow">
      <h1>Réglages</h1>
      <form class="card" id="settings">
        <label class="field">Moteur d'IA
          <select name="provider">
            <option value="openai" ${settings.provider === "openai" ? "selected" : ""}>OpenAI</option>
            <option value="mock" ${settings.provider === "mock" ? "selected" : ""}>Mode démo (sans IA, gratuit)</option>
          </select>
        </label>
        <label class="field">Modèle pour écrire le code
          <input type="text" name="model" value="${esc(settings.model)}">
        </label>
        <label class="field">Modèle pour les documents et les relectures (facultatif)
          <input type="text" name="writing_model" value="${esc(settings.writing_model || "")}" placeholder="ex. gpt-5.4-mini — vide = même modèle partout">
        </label>
        <p class="muted">Le premier modèle écrit le code. Le second, moins cher, rédige les documents et fait les relectures : c'est là que part la plus grande partie des tokens.</p>
        <label class="field">Clé API OpenAI ${settings.api_key_set ? '<span class="tag ok">Enregistrée</span>' : '<span class="tag neutral">Absente</span>'}
          <input type="password" name="key" autocomplete="off" placeholder="${settings.api_key_set ? "Laisse vide pour garder la clé actuelle" : "sk-…"}">
        </label>
        <p class="muted">La clé reste sur ton ordinateur. Projets enregistrés dans : ${esc(settings.workspace)}</p>
        <div id="settings-msg"></div>
        <div class="row"><button type="submit" class="btn primary">Enregistrer</button></div>
      </form>
    </div>`);

  document.getElementById("settings").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await api("POST", "/settings", {
        provider: form.provider.value,
        model: form.model.value,
        writing_model: form.writing_model.value,
        openai_api_key: form.key.value,
      });
      document.getElementById("settings-msg").innerHTML = '<div class="notice warn" role="status">Réglages enregistrés. Ils s\'appliquent aux nouveaux projets.</div>';
      form.key.value = "";
    } catch (error) {
      showError("settings-msg", error);
    }
  });
}

// ---------------------------------------------------------------- project

async function showProject(id) {
  const view = await api("GET", "/projects/" + encodeURIComponent(id));
  currentView = view;
  renderProject(view);

  if (view.running) {
    pollTimer = setTimeout(() => refresh(id), 2000);
  }
}

async function refresh(id) {
  if (!location.hash.startsWith("#/projects/" + id)) return;
  try {
    const view = await api("GET", "/projects/" + encodeURIComponent(id));
    const changed = JSON.stringify(view) !== JSON.stringify(currentView);
    currentView = view;
    if (changed) renderProject(view);
    app.querySelectorAll("[data-elapsed]").forEach((el) => { el.textContent = elapsedText(el.dataset.elapsed); });
    if (view.running) pollTimer = setTimeout(() => refresh(id), 2000);
  } catch (error) {
    pollTimer = setTimeout(() => refresh(id), 4000);
  }
}

function stepsPanel(view) {
  const currentAgent = view.pending && view.pending.agent;
  const rows = view.steps.map((step, index) => {
    const done = step.status === "APPROVED";
    const current = !done && step.agent === currentAgent;
    const cls = done ? "done" : current ? "current" : "";
    const mark = done ? "✓" : String(index + 1);
    return `<div class="step ${cls}"><span class="dot" aria-hidden="true">${mark}</span><span>${esc(step.label)}${done ? '<span class="visually-hidden"> (validé)</span>' : ""}</span></div>`;
  }).join("");
  const done = view.steps.filter((s) => s.status === "APPROVED").length;
  return `<nav class="steps" aria-label="Étapes du projet"><h2>Avancement · ${done}/8</h2>${rows}</nav>`;
}

function outputsList(paths) {
  if (!paths || !paths.length) return "";
  return `<div class="files">${paths.map((p) => `<button type="button" data-file="${esc(p)}">${esc(p)}</button>`).join("")}</div>`;
}

function renderProject(view) {
  const p = view.pending || {};
  let body = "";

  if (p.kind === "running") {
    body = `
      <span class="badge run"><span class="spinner" aria-hidden="true"></span>Les agents travaillent</span>
      <h1>${p.label ? esc(p.label) + " en cours…" : "Étape en cours…"}</h1>
      <p class="lead">Ça prend généralement une à quelques minutes. Cette page se met à jour toute seule.</p>
      ${p.started_at ? `<p class="muted" data-elapsed="${esc(p.started_at)}">${elapsedText(p.started_at)}</p>` : ""}`;
  } else if (p.kind === "questions") {
    body = `
      <span class="badge wait">${esc(p.label)} · des questions pour toi</span>
      <h1>Quelques questions avant de continuer</h1>
      <p class="lead">Chaque question a une réponse recommandée. Si tu ne sais pas, garde-la.</p>
      <form id="answers" style="display:flex;flex-direction:column;gap:16px">
        ${p.questions.map((q, qi) => questionCard(q, qi)).join("")}
        <div id="action-error"></div>
        <div class="row">
          <button type="submit" class="btn primary">Envoyer mes réponses</button>
          <button type="button" class="btn" data-let-decide>Laisser l'agent décider</button>
        </div>
      </form>`;
  } else if (p.kind === "review") {
    body = `
      <span class="badge wait">En attente de ta validation</span>
      <h1>${esc(p.label)} : étape terminée</h1>
      ${p.summary ? `<p class="lead">${esc(p.summary)}</p>` : ""}
      ${p.technology && p.technology.length ? technologyCard(p.technology) : ""}
      ${autoFixes(p.auto_fixes)}
      ${ownerSummary(p.owner_summary)}
      ${detailedDocuments(p.outputs, view.profile)}
      <div id="viewer"></div>
      ${changesForm(p.agent)}
      <div id="action-error"></div>
      <div class="row">
        <button type="button" class="btn primary" data-approve="${esc(p.agent)}">Valider cette étape</button>
        <button type="button" class="btn" data-toggle-changes>Demander une modification</button>
      </div>`;
  } else if (p.kind === "attention") {
    body = `
      <span class="badge danger">Un point demande ton attention</span>
      <h1>${esc(p.label)} : étape bloquée</h1>
      ${p.summary ? `<p class="lead">${esc(p.summary)}</p>` : ""}
      ${p.error ? `<div class="notice danger">${esc(p.error)}</div>` : ""}
      ${(p.reasons || []).filter(Boolean).length ? `<section class="card"><h2>Pourquoi</h2><ul>${p.reasons.filter(Boolean).map((r) => `<li>${esc(r)}</li>`).join("")}</ul></section>` : ""}
      ${(p.items || []).length ? `<section class="card"><h2>Problèmes trouvés</h2><ul>${p.items.map((i) => `<li><strong>${esc(i.id || "")}</strong> ${esc(i.title || i.description || "")} <span class="muted">${esc(i.severity || "")}</span></li>`).join("")}</ul></section>` : ""}
      ${autoFixes(p.auto_fixes)}
      ${ownerSummary(p.owner_summary)}
      ${detailedDocuments(p.outputs, view.profile)}
      <div id="viewer"></div>
      ${changesForm(p.agent)}
      <div id="action-error"></div>
      <div class="row">
        ${p.can_send_back ? `<button type="button" class="btn primary" data-send-back="${esc(p.agent)}">Renvoyer au développeur pour correction</button>` : ""}
        <button type="button" class="btn" data-retry="${esc(p.agent)}">Réessayer l'étape</button>
        <button type="button" class="btn" data-toggle-changes>Donner une consigne</button>
      </div>`;
  } else if (p.kind === "production") {
    body = `
      <span class="badge wait">Dernière validation</span>
      <h1>Toutes les étapes sont validées</h1>
      <p class="lead">Les tests, la revue de sécurité, la livraison et la fiabilité sont au vert. Valide pour clore le projet.</p>
      <div id="action-error"></div>
      <div class="row"><button type="button" class="btn primary" data-approve="production">Valider le projet</button></div>`;
  } else if (p.kind === "completed") {
    body = `
      <span class="badge ok">8 étapes sur 8 validées</span>
      <h1>Ton projet est prêt</h1>
      <p class="lead">Voici tout ce qui a été produit. L'aperçu en direct et la mise en ligne arrivent dans une prochaine version.</p>
      <section class="card"><h2>Fichiers du projet</h2>${outputsList(view.files)}</section>
      <div id="viewer"></div>`;
  } else {
    body = `
      ${p.error ? `<span class="badge danger">L'étape s'est arrêtée</span><div class="notice danger" role="alert">${esc(p.error)}</div>` : '<span class="badge run">Prêt à continuer</span>'}
      <h1>${p.label ? esc(p.label) : "Projet"}</h1>
      <p class="lead">${p.error ? "Corrige le problème (par exemple la clé OpenAI dans les réglages), puis relance." : "Les agents peuvent reprendre le travail."}</p>
      <div id="action-error"></div>
      <div class="row"><button type="button" class="btn primary" data-run>${p.error ? "Relancer" : "Continuer"}</button></div>`;
  }

  render(`
    <div class="wide">
      <aside class="side">
        <div class="card" style="gap:6px"><span class="muted">Projet</span><strong style="font-size:18px">${esc(view.name)}</strong><span class="muted">${view.profile === "developer" ? "Profil développeur" : "Profil : je ne code pas"}${view.provider === "mock" ? " · mode démo" : ""}</span></div>
        ${stepsPanel(view)}
      </aside>
      <section class="content">${body}</section>
    </div>`);

  bindProjectActions(view);
}

function elapsedText(startedAt) {
  const seconds = Math.max(0, Math.round((Date.now() - new Date(startedAt).getTime()) / 1000));
  if (seconds < 60) return "Démarré il y a " + seconds + " s";
  return "Démarré il y a " + Math.floor(seconds / 60) + " min " + (seconds % 60) + " s";
}

function questionCard(q, qi) {
  const options = (q.options || []).map((o, oi) => `
    <button type="button" class="choice" data-q="${qi}" data-label="${esc(o.label)}" data-detail="${esc(o.detail || "")}" aria-pressed="${o.recommended ? "true" : "false"}">
      <span class="row" style="gap:8px"><strong>${esc(o.label)}</strong>${o.recommended ? '<span class="tag ok">Recommandé</span>' : ""}</span>
      ${o.detail ? `<span>${esc(o.detail)}</span>` : ""}
    </button>`).join("");
  return `
    <section class="card" data-question="${qi}" data-text="${esc(q.question)}">
      <h2>${esc(q.question)}</h2>
      ${q.why ? `<p class="muted">${esc(q.why)}</p>` : ""}
      ${options ? `<div class="choices">${options}</div>` : ""}
      ${q.needs_owner_text
        ? `<label class="field">Ta réponse (c'est une information que toi seul connais)
            <textarea data-free="${qi}" rows="4" placeholder="Écris-la ici, ou choisis une option ci-dessus."></textarea>
          </label>`
        : `<label class="field">${options ? "Ou ta propre réponse (facultatif)" : "Ta réponse"}
            <input type="text" data-free="${qi}" ${options ? "" : "required"}>
          </label>`}
    </section>`;
}

function bulletCard(title, hint, items, tone) {
  if (!items || !items.length) return "";
  return `<section class="card ${tone || ""}"><h2>${esc(title)}</h2>${hint ? `<p class="muted">${esc(hint)}</p>` : ""}<ul class="plain-list">${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul></section>`;
}

function autoFixes(list) {
  const fixes = (list || []).filter((fix) => fix && fix.cause);
  if (!fixes.length) return "";
  return `<section class="card"><h2>Corrigé automatiquement par la Factory</h2>
    <p class="muted">L'agent a buté sur ces problèmes ; la Factory les a diagnostiqués et lui a donné la consigne elle-même.</p>
    <ul class="plain-list">${fixes.map((fix) => `<li>${esc(fix.cause)}${fix.needs_human ? " <strong>(il faut ton avis)</strong>" : ""}</li>`).join("")}</ul></section>`;
}

function ownerSummary(summary) {
  if (!summary) return "";
  return bulletCard("Ce qui a été décidé", "", summary.will_do)
    + bulletCard("À vérifier par toi", "L'agent a choisi ces points à ta place. Si l'un ne te convient pas, demande une modification.", summary.assumptions, "check")
    + bulletCard("Pas dans cette première version", "", summary.wont_do);
}

function detailedDocuments(paths, profile) {
  if (!paths || !paths.length) return "";
  return `<details class="card" ${profile === "developer" ? "open" : ""}>
    <summary><strong>Voir les documents détaillés (${paths.length})</strong> <span class="muted">— pour les curieux, pas besoin de les lire pour valider</span></summary>
    ${outputsList(paths)}
  </details>`;
}

function technologyCard(components) {
  const rows = components.map((c) => `<li><strong>${esc(c.name)}</strong> : ${esc(c.technology)}<br><span class="muted">${esc(c.rationale)}</span></li>`).join("");
  return `<section class="card"><h2>Technologies proposées</h2><ul style="display:flex;flex-direction:column;gap:8px">${rows}</ul></section>`;
}

function changesForm(agent) {
  return `
    <form class="card" id="changes" data-agent="${esc(agent)}" hidden>
      <label class="field">Qu'est-ce que tu veux changer ?
        <textarea name="text" rows="3" required></textarea>
      </label>
      <div class="row"><button type="submit" class="btn primary">Envoyer la demande</button></div>
    </form>`;
}

function bindProjectActions(view) {
  const id = view.id;
  const act = async (button, label, call) => {
    busy(button, label);
    try {
      const next = await call();
      currentView = next;
      renderProject(next);
      if (next.running) pollTimer = setTimeout(() => refresh(id), 2000);
    } catch (error) {
      showError("action-error", error);
      button.disabled = false;
      button.textContent = button.dataset.originalLabel || "Réessayer";
    }
  };

  app.querySelectorAll("button").forEach((b) => { b.dataset.originalLabel = b.textContent.trim(); });

  app.querySelectorAll(".choice[data-q]").forEach((button) => {
    button.addEventListener("click", () => {
      app.querySelectorAll(`.choice[data-q="${button.dataset.q}"]`).forEach((other) => {
        other.setAttribute("aria-pressed", String(other === button));
      });
    });
  });

  app.querySelectorAll("[data-let-decide]").forEach((button) => {
    button.addEventListener("click", () => {
      const collected = view.pending.questions.map((q) => {
        const recommended = (q.options || []).find((o) => o.recommended);
        return {
          question: q.question,
          answer: recommended
            ? recommended.label + (recommended.detail ? " — " + recommended.detail : "") + " (the owner let the agent decide: this recommended option is final)"
            : "The owner lets the agent decide: choose the safest, simplest option and record it as an assumption.",
        };
      });
      act(button, "Envoi…", () => api("POST", `/projects/${id}/answers`, { agent: view.pending.agent, answers: collected }));
    });
  });

  const answers = document.getElementById("answers");
  if (answers) {
    answers.addEventListener("submit", (event) => {
      event.preventDefault();
      const collected = [...app.querySelectorAll("[data-question]")].map((card) => {
        const qi = card.dataset.question;
        const free = card.querySelector(`[data-free="${qi}"]`).value.trim();
        const picked = card.querySelector(`.choice[data-q="${qi}"][aria-pressed="true"]`);
        const chosen = picked
          ? picked.dataset.label + (picked.dataset.detail ? " — " + picked.dataset.detail : "")
          : "";
        return { question: card.dataset.text, answer: free || chosen };
      });
      const submit = answers.querySelector('button[type="submit"]');
      act(submit, "Envoi…", () => api("POST", `/projects/${id}/answers`, { agent: view.pending.agent, answers: collected }));
    });
  }

  app.querySelectorAll("[data-approve]").forEach((button) => {
    button.addEventListener("click", () => act(button, "Validation…", () => api("POST", `/projects/${id}/approve`, { step: button.dataset.approve })));
  });

  app.querySelectorAll("[data-send-back]").forEach((button) => {
    button.addEventListener("click", () => act(button, "Envoi…", () => api("POST", `/projects/${id}/send-back`, { source: button.dataset.sendBack })));
  });

  app.querySelectorAll("[data-retry]").forEach((button) => {
    button.addEventListener("click", () => act(button, "Relance…", () => api("POST", `/projects/${id}/retry`, { agent: button.dataset.retry })));
  });

  app.querySelectorAll("[data-run]").forEach((button) => {
    button.addEventListener("click", () => act(button, "Relance…", () => api("POST", `/projects/${id}/run`, {})));
  });

  app.querySelectorAll("[data-toggle-changes]").forEach((button) => {
    button.addEventListener("click", () => {
      const form = document.getElementById("changes");
      form.hidden = !form.hidden;
      if (!form.hidden) form.querySelector("textarea").focus();
    });
  });

  const changes = document.getElementById("changes");
  if (changes) {
    changes.addEventListener("submit", (event) => {
      event.preventDefault();
      const submit = changes.querySelector('button[type="submit"]');
      act(submit, "Envoi…", () => api("POST", `/projects/${id}/changes`, { agent: changes.dataset.agent, text: changes.text.value }));
    });
  }

  app.querySelectorAll("[data-file]").forEach((button) => {
    button.addEventListener("click", async () => {
      const viewer = document.getElementById("viewer");
      try {
        const file = await api("GET", `/projects/${id}/file?path=${encodeURIComponent(button.dataset.file)}`);
        viewer.innerHTML = `<section class="card"><div class="row spread"><h2 style="font-family:'IBM Plex Mono',monospace;font-size:15px">${esc(file.path)}</h2><button type="button" class="btn" data-close-viewer>Fermer</button></div><pre class="viewer">${esc(file.content)}</pre></section>`;
        viewer.querySelector("[data-close-viewer]").addEventListener("click", () => { viewer.innerHTML = ""; });
        viewer.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (error) {
        showError("viewer", error);
      }
    });
  });
}

route();
