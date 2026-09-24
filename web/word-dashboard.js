(() => {
  "use strict";
  let DATA;
  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
  const fmt = value => Number(value || 0).toLocaleString();
  const items = list => (list || []);
  const countFor = (list, label) => items(list).find(item => item.label === label)?.count || 0;

  function rankList(target, values, empty = "No evidence in this sample") {
    $(target).innerHTML = items(values).length
      ? values.map(item => `<div class="rank-item"><span title="${esc(item.label)}">${esc(item.label)}</span><b>${fmt(item.count)}</b></div>`).join("")
      : `<p class="footnote">${esc(empty)}</p>`;
  }

  function bars(target, values, rateMode = false) {
    const max = Math.max(1, ...values.map(value => rateMode ? value.rate : value.count));
    $(target).innerHTML = values.map(value => {
      const metric = rateMode ? value.rate : value.count;
      const detail = rateMode ? `${fmt(value.count)} hits · ${fmt(value.tokens)} tokens` : `${fmt(value.count)} hits`;
      return `<div class="bar-row">
        <div class="bar-label"><strong>${esc(value.label)}</strong><small>${detail}</small></div>
        <div class="bar-track"><div class="bar-fill" style="width:${Math.max(1.5, metric / max * 100)}%"></div></div>
        <div class="bar-value">${rateMode ? Number(metric).toFixed(2) : fmt(metric)}</div>
      </div>`;
    }).join("");
  }

  function reliability(lemma) {
    $("reliability-cards").innerHTML = DATA.reliability.map(report => {
      const row = report.rows.find(entry => entry.lemma === lemma);
      const control = DATA.layers[report.control];
      const delta = row.rate_delta > 0 ? `+${row.rate_delta.toFixed(2)}` : row.rate_delta.toFixed(2);
      const relative = row.relative_delta_percent === null ? "control has no hits" : `${row.relative_delta_percent > 0 ? "+" : ""}${row.relative_delta_percent}%`;
      return `<div class="reliability-card ${esc(report.control)}">
        <header><strong>OGA vs ${esc(control.label)}</strong><span class="delta">${delta} / 10k</span></header>
        <p>OGA ${row.primary_count} hits (${row.primary_rate.toFixed(2)}) · control ${row.control_count} (${row.control_rate.toFixed(2)}) · ${relative} · ${report.shared_works.length} shared works</p>
      </div>`;
    }).join("") + `<p class="footnote">Next production step: align occurrences, then report lemma, morphology, and dependency agreement with reviewed error samples. Aggregate rate deltas alone cannot distinguish tokenization from annotation errors.</p>`;
  }

  function highlightedSentence(example) {
    const words = example.sentence.split(" ");
    if (example.token_index >= 0 && example.token_index < words.length) words[example.token_index] = `<mark>${esc(words[example.token_index])}</mark>`;
    return words.map((word, index) => index === example.token_index ? word : esc(word)).join(" ");
  }

  function render() {
    const lemma = $("lemma-select").value;
    const layerId = $("layer-select").value;
    const layer = DATA.layers[layerId];
    const item = layer.lemmas[lemma];
    const sense = DATA.sense_evidence[lemma];
    const params = new URLSearchParams(location.search);
    params.set("lemma", lemma); params.set("layer", layerId);
    history.replaceState(null, "", `${location.pathname}?${params}`);

    $("layer-description").innerHTML = `<strong>${esc(layer.role)}</strong> · ${esc(layer.scheme)} · ${fmt(layer.tokens)} sampled tokens`;
    $("full-search-link").href = `./search/index.html?q=${encodeURIComponent(lemma)}&mode=lemma`;
    $("stat-occurrences").textContent = fmt(item.occurrences);
    $("stat-rate").textContent = Number(item.rate).toFixed(2);
    $("stat-works").textContent = fmt(items(item.works).filter(row => row.count > 0).length);
    $("stat-forms").textContent = fmt(item.distinct_forms);
    bars("register-bars", item.register_detail, true);
    bars("genre-bars", item.genres, false);
    rankList("form-list", item.forms);
    rankList("feature-list", item.features);
    rankList("relation-list", item.relations);
    rankList("head-list", item.heads);
    rankList("dependent-list", item.dependents);
    reliability(lemma);

    $("sense-status").textContent = sense.status;
    $("gloss-list").innerHTML = items(sense.glosses).length
      ? sense.glosses.map(row => `<span class="gloss"><span>${esc(row.label)}</span><b>${fmt(row.count)}</b></span>`).join("")
      : `<p class="footnote">No gloss evidence for this lemma in the two glossed pilot controls.</p>`;
    $("gloss-sources").textContent = items(sense.sources).length
      ? `Coverage: ${sense.sources.map(row => `${row.label} (${row.count})`).join("; ")}. A gloss is evidence, not a one-to-one word sense.`
      : "No glossed occurrences in the current semantic pilot.";

    $("work-table").innerHTML = layer.works.map(work => {
      const hits = work.hits[lemma] || 0;
      const rate = work.tokens ? 10000 * hits / work.tokens : 0;
      return `<tr class="${hits ? "" : "zero-row"}"><td><span class="work-title">${esc(work.title)}<small>${esc(work.author)}</small></span></td><td>${esc(work.genre)}</td><td>${fmt(work.tokens)}</td><td>${fmt(hits)}</td><td>${rate.toFixed(2)}</td></tr>`;
    }).join("");

    $("provenance-summary").textContent = items(item.provenance).map(row => `${row.label}: ${row.count}`).join(" · ") || "status unavailable";
    $("example-list").innerHTML = items(item.examples).length ? item.examples.map(example => {
      const location = example.reference ? `${example.title} ${example.reference}` : example.title;
      const href = `./?w=${encodeURIComponent(example.urn + (example.reference ? `:${example.reference}` : ""))}`;
      return `<div class="example">
        <div class="example-meta"><strong>${esc(location)}</strong>${esc(example.author)} · ${esc(example.genre)}<br>${esc(example.relation || "unlabelled")} · ${esc(example.analysis)}</div>
        <div class="greek">${highlightedSentence(example)}</div>
        <a class="inspect-link" href="${href}">Open in PMV →</a>
      </div>`;
    }).join("") : `<p class="footnote">No occurrences in this sampled layer.</p>`;
  }

  function initialize() {
    $("page-title").textContent = DATA.title;
    $("page-subtitle").textContent = DATA.subtitle;
    $("production-goal").textContent = DATA.production_goal;
    $("warning").textContent = DATA.warning;
    $("method-copy").textContent = DATA.method;
    const query = new URLSearchParams(location.search);
    $("lemma-select").innerHTML = DATA.pilot_lemmas.map(lemma => `<option value="${esc(lemma)}">${esc(lemma)}</option>`).join("");
    $("layer-select").innerHTML = Object.values(DATA.layers).map(layer => `<option value="${esc(layer.id)}">${esc(layer.label)} — ${esc(layer.role)}</option>`).join("");
    $("lemma-select").value = DATA.pilot_lemmas.includes(query.get("lemma")) ? query.get("lemma") : "λόγος";
    $("layer-select").value = DATA.layers[query.get("layer")] ? query.get("layer") : "oga";
    $("source-cards").innerHTML = Object.values(DATA.layers).map(layer => `<div class="source-card"><strong>${esc(layer.label)} · ${esc(layer.scheme)}</strong><span>${esc(layer.role)}</span><span>${fmt(layer.files)} files · ${fmt(layer.sentences)} sentences · ${fmt(layer.tokens)} words</span><span>${esc(layer.note)}</span></div>`).join("");
    $("inventory-list").innerHTML = Object.entries(DATA.inventory).map(([key, value]) => `<dt>${esc(key.replaceAll("_", " "))}</dt><dd>${fmt(value)}</dd>`).join("");
    $("lemma-select").addEventListener("change", render);
    $("layer-select").addEventListener("change", render);
    document.querySelectorAll(".help").forEach(button => {
      button.addEventListener("mouseenter", event => {
        const tip = $("tooltip"); tip.textContent = button.dataset.help; tip.hidden = false;
        const box = event.target.getBoundingClientRect(); tip.style.left = `${Math.min(innerWidth - 300, box.left)}px`; tip.style.top = `${box.bottom + 7}px`;
      });
      button.addEventListener("mouseleave", () => $("tooltip").hidden = true);
    });
    render();
  }

  fetch("word-dashboard-data.json", {cache: "no-store"})
    .then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
    .then(data => { DATA = data; initialize(); })
    .catch(error => { document.querySelector("main").innerHTML = `<div class="error"><h1>Dashboard data unavailable</h1><p>${esc(error.message)}</p></div>`; });
})();
