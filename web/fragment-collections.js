/* Optional collection browser. No persistence or changes to existing work routes. */
window.PMVFragmentCollections = (() => {
  const enabled = new URLSearchParams(location.search).get('collections') === '1' ||
    (document.documentElement.dataset.collectionPreview === 'offline' && new URLSearchParams(location.search).get('collections') !== 'off');
  const escape = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalize = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ς/g,'σ');
  const href = fields => {const u=new URL(location.href); ['w','fragment','collection','allworks','focus','cols','right','right2','right3','right4','right5','right6'].forEach(k=>u.searchParams.delete(k)); for(const [k,v] of Object.entries(fields)) u.searchParams.set(k,v); return u.pathname+u.search;};
  let data;
  async function attach(catalog) {
    if (!enabled) return;
    const root=document.getElementById('splash-view-root');
    const banner=document.createElement('div'); banner.className='fc-experiment';
    banner.innerHTML=`<span>Collection preview</span><a href="${escape(href({collections:'off'}))}">Turn off experiment</a>`;
    document.body.prepend(banner);
    const toolbar=document.querySelector('.mode-toggle-panel');
    if(toolbar){const back=document.createElement('a'); back.className='toggle-btn';back.href=href({collection:'aeschylus-fragments'});back.textContent='Fragments';toolbar.append(back);}
    try {
      const embedded=document.getElementById('fragment-collection-data');
      if(embedded) data=JSON.parse(embedded.textContent);
      else {
        const r=await fetch('./site/fragment-collections.json', {cache:'no-store'});
        if(!r.ok) throw new Error('Fragment collection could not be loaded');
        data=await r.json();
      }
      const group=root.querySelector('[data-author="tlg0085"]');
      if(group) {
        group.open=true;
        const row=document.createElement('li'); row.className='fc-collection-entry';
        row.dataset.search='aeschylus fragments nauck'; row.dataset.work='collection:aeschylus-fragments';
        row.innerHTML=`<a href="${escape(href({collection:'aeschylus-fragments'}))}"><strong>Fragments</strong><span>Collection · ${data.scope.play_headings} play headings</span></a>`;
        group.querySelector('ul').append(row);
        const all=document.createElement('a'); all.className='fc-all-link'; all.href=href({allworks:'aeschylus'}); all.textContent='Browse surviving and fragmentary works together'; group.append(all);
      }
      const params=new URLSearchParams(location.search);
      if(params.has('fragment')) renderWork(root,params.get('fragment'));
      else if(params.has('collection') || params.has('allworks')) renderCollection(root,catalog,params.has('allworks'),params.get('collection'));
    } catch(e) {banner.append(document.createTextNode(' · '+e.message));}
  }
  function renderCollection(root,catalog,all,collectionId) {
    const coll=data.collections.find(c=>c.id===collectionId) || data.collections[0];
    const ids=new Set(coll.members);
    const fragmentWorks=Object.values(data.works).filter(w=>ids.has(w.id));
    const extant=all ? Object.entries(catalog.works).filter(([k,w])=>w.textgroup==='tlg0085'&&!w.experimental_fragment).map(([k,w])=>({id:k,title:w.title,status:'Survives complete',extant:true})) : [];
    const pool=[...extant,...fragmentWorks].sort((a,b)=>a.title.localeCompare(b.title));
    root.innerHTML=`<main class="fc-page"><nav><a href="${escape(href({}))}">All authors</a> / Aeschylus</nav>
      <h1>${all?'Aeschylus — works':escape(coll.title)}</h1>
      <div class="fc-tabs"><a href="${escape(href({collection:'aeschylus-fragments'}))}">Fragments</a><a href="${escape(href({allworks:'aeschylus'}))}">All Aeschylus works</a><a href="${escape(href({collection:'nauck1889'}))}">Nauck 1889</a></div>
      <p>${all ? 'Surviving plays and individually identified fragmentary works.' : data.scope.play_headings+' play headings · '+data.scope.included_fragments+' numbered fragments in the supplied Nauck file.'}</p>
      <div class="fc-controls"><label>Find a work<input id="fc-filter" placeholder="Athamas, Danaides, Niobe…"></label><label>Search fragment verses<input id="fc-search" placeholder="ποδῶκες"></label></div>
      <div id="fc-count" aria-live="polite"></div><div id="fc-results" class="fc-work-list"></div>
      <details class="fc-scope"><summary>About this experimental collection</summary><p>${escape(data.editorial_note)}</p><p>${data.scope.outside_play_containers} numbered fragments outside play containers are not included in this preview. Counts describe markup, not a settled total of historical plays. Verse search covers this collection, not the surviving plays.</p></details></main>`;
    const filter=root.querySelector('#fc-filter'), search=root.querySelector('#fc-search');
    function draw() {
      const q=normalize(search.value.trim()), title=normalize(filter.value.trim());
      let hits=0;
      const rows=pool.filter(w=>normalize(w.title+' '+(w.source_title||'')).includes(title)).map(w=>{
        const matched=q&&!w.extant ? w.fragments.flatMap(f=>f.lines.filter(l=>normalize(l.text).includes(q)).map(l=>({ref:f.number+'.'+l.ref,text:l.text}))) : [];
        if(q&&!matched.length) return '';
        hits++;
        const target=w.extant?{w:w.id}:w.pmv_work_key?{w:w.pmv_work_key,focus:w.pmv_focus,cols:'1'}:{fragment:w.id};
        return `<a class="fc-work" href="${escape(href(target))}"><div><strong>${escape(w.title)}</strong>${w.source_title?`<span lang="grc">${escape(w.source_title)}</span>`:''}</div><div class="fc-meta">${escape(w.status)}${w.extant?'':' · '+w.fragments.length+' fragments'}</div>${matched.slice(0,3).map(m=>`<p class="fc-hit" lang="grc">${escape(m.ref)} · ${escape(m.text)}</p>`).join('')}</a>`;
      }).join('');
      root.querySelector('#fc-results').innerHTML=rows||'<p>No matching works.</p>';
      root.querySelector('#fc-count').textContent=hits+' works'+(q?' with matching verses':'');
    }
    filter.addEventListener('input',draw);search.addEventListener('input',draw);draw();
  }
  function renderWork(root,id) {
    const w=data.works[id];
    if(!w) {root.innerHTML='<main class="fc-page"><h1>Work not found</h1><a href="'+escape(href({collection:'aeschylus-fragments'}))+'">Return to Fragments</a></main>';return;}
    const members=data.collections.filter(c=>c.members.includes(id));
    root.innerHTML=`<main class="fc-page fc-reader"><nav><a href="${escape(href({}))}">All authors</a> / <a href="${escape(href({allworks:'aeschylus'}))}">Aeschylus</a> / <a href="${escape(href({collection:'aeschylus-fragments'}))}">Fragments</a></nav>
      <h1>${escape(w.title)} <span lang="grc">${escape(w.source_title)}</span></h1><p>${escape(w.status)} · Nauck 1889</p>
      <div class="fc-tabs">${members.map(c=>`<a href="${escape(href({collection:c.id}))}">${escape(c.title)}</a>`).join('')}</div>
      ${w.introduction?`<details class="fc-scope" ${w.line_count?'':'open'}><summary>Editorial evidence for this play</summary><p>${escape(w.introduction)}</p></details>`:''}
      ${!w.line_count?'<p class="fc-empty">No quoted verse is encoded for this play. Its work record remains available.</p>':''}
      <div class="fc-fragment-nav">${w.fragments.map(f=>`<a href="#fr-${encodeURIComponent(f.number)}">${escape(f.number)}</a>`).join('')}</div>
      ${w.fragments.map(f=>`<section class="fc-fragment" id="fr-${escape(f.number)}"><h2>Fragment ${escape(f.number)}</h2><div class="fc-columns"><div class="fc-verse"><h3>Aeschylean text</h3>${f.lines.length?f.lines.map(l=>`<div lang="grc" class="fc-line"><span>${escape(l.ref)}</span><div>${escape(l.text)}</div></div>`).join(''):'<p>Testimonium only in this encoding.</p>'}</div><details class="fc-context" open><summary>Transmitting source and Nauck’s notes</summary><div>${escape(f.context).replace(/\n\n/g,'</div><div>')}</div></details></div></section>`).join('')}
      <details class="fc-scope"><summary>Edition and identification</summary><p>${escape(data.editorial_note)}</p><p>Experimental work identifier: <code>${escape(w.work_urn)}</code></p><p>Source region: <code>${escape(w.source+w.selector)}</code></p></details></main>`;
  }
  return {attach};
})();
