/* Optional collection browser. No persistence or changes to existing work routes. */
window.PMVFragmentCollections = (() => {
  // This module ships only in the isolated trial; ordinary navigation should
  // not silently lose its collections. Explicit off remains the rollback.
  const enabled = new URLSearchParams(location.search).get('collections') !== 'off';
  const escape = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalize = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ς/g,'σ');
  const href = fields => {const u=new URL(location.href); ['w','fragment','collection','allworks','author','scope','genre','browse','focus','cols','right','right2','right3','right4','right5','right6'].forEach(k=>u.searchParams.delete(k)); u.searchParams.set('collections','1'); for(const [k,v] of Object.entries(fields)) u.searchParams.set(k,v); return u.pathname+u.search;};
  let data;
  // Explicit initial genre membership: extant dramatic works in this catalog.
  // Cyclops and Ichneutae are excluded; fragmentary genre is not inferred
  // from author identity or from absence of a satyr-play label.
  const tragedyKeys = new Set([
    ...Array.from({length:7},(_,i)=>'tlg0085.tlg00'+(i+1)),
    ...Array.from({length:7},(_,i)=>'tlg0011.tlg00'+(i+1)),
    ...Array.from({length:18},(_,i)=>'tlg0006.tlg'+String(i+2).padStart(3,'0'))
  ]);
  function workTarget(w) {
    return w.pmv_work_key ? {w:w.pmv_work_key,focus:w.pmv_focus,cols:'1'} : w.fragments ? {fragment:w.id} : {w:w.id};
  }
  // Count whitespace-delimited tokens containing letters only in the quoted
  // authorial lines. Punctuation and lacuna marks alone do not count as words.
  function wordCount(w) {
    return (w.fragments||[]).reduce((n,f)=>n+f.lines.reduce((m,l)=>m+l.text.split(/\s+/u).filter(t=>/\p{L}/u.test(t)).length,0),0);
  }
  function fragmentNumbers(w) {
    const nums=w.fragments.map(f=>String(f.number)), ranges=[];
    for(let i=0;i<nums.length;i++) {
      const start=nums[i];let end=start;
      while(i+1<nums.length && /^\d+$/.test(end) && /^\d+$/.test(nums[i+1]) && Number(nums[i+1])===Number(end)+1)end=nums[++i];
      ranges.push(start===end?start:start+'–'+end);
    }
    return ranges.join(', ');
  }
  function fragmentTotals(works) {
    const n=works.reduce((n,w)=>n+(w.fragments||[]).length,0),words=works.reduce((n,w)=>n+wordCount(w),0);
    return n+' fragment'+(n===1?'':'s')+' · '+words.toLocaleString()+' word'+(words===1?'':'s')+' of Aeschylus';
  }
  function fragmentMeta(w) {
    if(!w.fragments) {
      const stats=(data.tragedy_statistics||{})[w.id];
      return stats ? `<div class="fc-fragment-refs">Lines ${escape(stats.citation_span)} · ${stats.words.toLocaleString()} Greek words</div><div class="fc-meta" title="Citation span, not a count of encoded verse segments. Words count the printed Greek verse, including bracketed text; notes and speaker labels are excluded.">${escape(stats.edition)}</div>` : '';
    }
    const refs=fragmentNumbers(w);
    return `<div class="fc-fragment-refs">${refs?(w.fragments.length===1?'Fragment ':'Fragments ')+escape(refs)+' (Nauck)':'No numbered fragments'}</div><div class="fc-meta" title="Word count includes only quoted authorial lines in this transcription; sources and editorial notes are excluded. Punctuation-only tokens are not counted.">${fragmentTotals([w])}${w.line_count?'':' · Evidence only'}</div>`;
  }
  function browseNavigation(catalog) {
    const p=new URLSearchParams(location.search), raw=p.get('w')||'';
    const globalLibrary=p.has('browse');
    const tg=globalLibrary ? null : p.get('author') || (raw.startsWith('urn:cts:') ? raw.split(':')[3].split('.')[0] : raw.split('.')[0]) || 'tlg0085';
    const author=tg&&((catalog.authors||{})[tg]||tg);
    const nav=document.createElement('nav');nav.className='fc-browse-nav';nav.setAttribute('aria-label','Browse the library');
    const links=[['Fragments',{collection:'aeschylus-fragments'}]];
    if(tg==='tlg0085') {
      links.push(['Surviving works of '+author,{author:tg,scope:'surviving'}]);
    }
    if(tg) links.push(['All works of '+author,{author:tg}]);
    links.push(['Tragedy',{genre:'tragedy'}],['All works',{browse:'all'}]);
    nav.innerHTML='<span>Browse:</span>'+links.map(([label,route])=>`<a href="${escape(href(route))}">${escape(label)}</a>`).join('');
    const banner=document.getElementById('perseus-banner');if(banner)banner.after(nav);
    const indexNav=nav.cloneNode(true);indexNav.classList.add('fc-index-nav');
    document.getElementById('splash-view-root').prepend(indexNav);
  }
  function renderLibrary(root,catalog,params) {
    const author=params.get('author'), genre=params.get('genre'), scope=params.get('scope');
    const authorName=author&&((catalog.authors||{})[author]||author);
    const title=genre ? 'Tragedy' : author ? (scope==='surviving'?'Surviving works of ':'All works of ')+authorName : 'All works';
    const standard=Object.entries(catalog.works).filter(([id,w])=>!w.experimental_fragment && (!author||w.textgroup===author) && (!genre||tragedyKeys.has(id))).map(([id,w])=>({...w,id,author:(catalog.authors||{})[w.textgroup]||w.textgroup}));
    const fragments=!genre&&scope!=='surviving'&&(!author||author==='tlg0085') ? Object.values(data.works).map(w=>({...w,author:'Aeschylus'})) : [];
    const works=[...standard,...fragments].sort((a,b)=>a.author.localeCompare(b.author)||a.title.localeCompare(b.title));
    const authorScope=author==='tlg0085' ? `<nav class="fc-scope-links" aria-label="Aeschylus work scope"><a href="${escape(href({author,scope:'surviving'}))}" ${scope==='surviving'?'aria-current="page"':''}>Surviving works</a><span>→</span><a href="${escape(href({author}))}" ${scope!=='surviving'?'aria-current="page"':''}>All works</a></nav>` : '';
    root.innerHTML=`<main class="fc-page"><h1>${escape(title)}</h1>${authorScope}${genre?'<p>Currently cataloged surviving plays of Aeschylus, Sophocles and Euripides. Fragmentary works await genre review; satyr plays are excluded.</p>':''}<label class="fc-library-filter">Find a work or author<input id="fc-library-filter" type="search" placeholder="Title or author"></label><p id="fc-library-count" aria-live="polite"></p><div id="fc-library-results"></div></main>`;
    const input=root.querySelector('#fc-library-filter');
    let expanded={};
    // Global All works is a reset point: it starts with no author privileged.
    // Author and genre views may remember independently opened groups.
    if(!params.has('browse')) try {expanded=JSON.parse(sessionStorage.getItem('pmv-author-groups')||'{}');} catch(e) {}
    const draw=()=>{
      const q=normalize(input.value.trim());
      const matches=works.filter(w=>normalize(w.title+' '+w.author+' '+(w.source_title||'')+' '+(w.fragments||[]).map(f=>f.number).join(' ')).includes(q));
      const groups=new Map();
      matches.forEach(w=>{if(!groups.has(w.author))groups.set(w.author,[]);groups.get(w.author).push(w);});
      root.querySelector('#fc-library-count').textContent=matches.length+(matches.length===1?' work':' works');
      const results=root.querySelector('#fc-library-results');
      results.innerHTML=[...groups].map(([name,items])=>{
        const open=q || author || expanded[name];
        return `<details class="fc-author-group" data-author-name="${escape(name)}" ${open?'open':''}><summary>${escape(name)} <span>(${items.length})</span>${items.some(w=>w.fragments)?`<small class="fc-author-fragments">${fragmentTotals(items)}</small>`:''}</summary><div class="fc-work-list">${items.map(w=>`<a class="fc-work" href="${escape(href(workTarget(w)))}"><strong>${escape(w.title)}</strong>${fragmentMeta(w)}</a>`).join('')}</div></details>`;
      }).join('')||'<p>No matching works.</p>';
      results.querySelectorAll('.fc-author-group').forEach(group=>group.addEventListener('toggle',()=>{
        if(q)return;
        expanded[group.dataset.authorName]=group.open;
        if(!params.has('browse')) try {sessionStorage.setItem('pmv-author-groups',JSON.stringify(expanded));} catch(e) {}
      }));
    };
    input.addEventListener('input',draw);draw();
  }
  async function attach(catalog) {
    if (!enabled) return;
    const root=document.getElementById('splash-view-root');
    const banner=document.createElement('div'); banner.className='fc-experiment';
    banner.innerHTML=`<span>Collection preview</span><a href="${escape(href({collections:'off'}))}">Turn off experiment</a>`;
    document.body.prepend(banner);
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
        row.innerHTML=`<a href="${escape(href({collection:'aeschylus-fragments'}))}"><strong>Fragments</strong><span>Collection · ${data.scope.play_headings} play headings · ${fragmentTotals(Object.values(data.works))}</span></a>`;
        group.querySelector('ul').append(row);
        const all=document.createElement('a'); all.className='fc-all-link'; all.href=href({allworks:'aeschylus'}); all.textContent='Browse surviving and fragmentary works together'; group.append(all);
      }
      const params=new URLSearchParams(location.search);
      if(params.has('browse') || params.has('author') || params.has('genre')) renderLibrary(root,catalog,params);
      else if(params.has('fragment')) renderWork(root,params.get('fragment'));
      else if(params.has('collection') || params.has('allworks')) renderCollection(root,catalog,params.has('allworks'),params.get('collection'));
      browseNavigation(catalog);
    } catch(e) {banner.append(document.createTextNode(' · '+e.message));}
  }
  function renderCollection(root,catalog,all,collectionId) {
    const coll=data.collections.find(c=>c.id===collectionId) || data.collections[0];
    const ids=new Set(coll.members);
    const fragmentWorks=Object.values(data.works).filter(w=>ids.has(w.id));
    const extant=Object.entries(catalog.works).filter(([k,w])=>w.textgroup==='tlg0085'&&!w.experimental_fragment).map(([k,w])=>({id:k,title:w.title,status:'Survives complete',extant:true})).sort((a,b)=>a.title.localeCompare(b.title));
    const pool=(all?[...extant,...fragmentWorks]:fragmentWorks).sort((a,b)=>a.title.localeCompare(b.title));
    const survivingContext=!all&&coll.id==='aeschylus-fragments' ? `<details class="fc-surviving-context" open><summary>Surviving works <span>(${extant.length})</span></summary><div class="fc-work-list">${extant.map(w=>`<a class="fc-work" href="${escape(href({w:w.id}))}"><strong>${escape(w.title)}</strong>${fragmentMeta(w)}</a>`).join('')}</div></details>` : '';
    root.innerHTML=`<main class="fc-page"><nav><a href="${escape(href({}))}">All authors</a> / Aeschylus</nav>
      <h1>${all?'Aeschylus — works':escape(coll.title)}</h1>
      <div class="fc-tabs"><a href="${escape(href({collection:'aeschylus-fragments'}))}">Fragments</a><a href="${escape(href({allworks:'aeschylus'}))}">All Aeschylus works</a><a href="${escape(href({collection:'nauck1889'}))}">Nauck 1889</a></div>
      <p>${all ? 'Surviving plays and individually identified fragmentary works.' : data.scope.play_headings+' play headings · '+fragmentTotals(fragmentWorks)+' in the supplied Nauck file.'}</p>
      ${survivingContext}
      ${!all?'<h2 class="fc-fragment-heading">Fragmentary works</h2>':''}
      <div class="fc-controls"><label>Find a work or fragment number<input id="fc-filter" placeholder="Athamas, Danaides, 149…"></label><label>Search fragment verses<input id="fc-search" placeholder="ποδῶκες"></label></div>
      <div id="fc-count" aria-live="polite"></div><div id="fc-results" class="fc-work-list"></div>
      <details class="fc-scope"><summary>About this experimental collection</summary><p>${escape(data.editorial_note)}</p><p>${data.scope.outside_play_containers} numbered fragments outside play containers are not included in this preview. Counts describe markup, not a settled total of historical plays. Verse search covers this collection, not the surviving plays. Word counts count space-separated tokens containing letters in the encoded authorial lines; transmitting sources, editorial notes, and punctuation-only tokens are excluded.</p></details></main>`;
    const filter=root.querySelector('#fc-filter'), search=root.querySelector('#fc-search');
    function draw() {
      const q=normalize(search.value.trim()), title=normalize(filter.value.trim());
      let hits=0;
      const rows=pool.filter(w=>normalize(w.title+' '+(w.source_title||'')+' '+(w.fragments||[]).map(f=>f.number).join(' ')).includes(title)).map(w=>{
        const matched=q&&!w.extant ? w.fragments.flatMap(f=>f.lines.filter(l=>normalize(l.text).includes(q)).map(l=>({ref:f.number+'.'+l.ref,text:l.text}))) : [];
        if(q&&!matched.length) return '';
        hits++;
        const target=w.extant?{w:w.id}:w.pmv_work_key?{w:w.pmv_work_key,focus:w.pmv_focus,cols:'1'}:{fragment:w.id};
        return `<a class="fc-work" href="${escape(href(target))}"><div><strong>${escape(w.title)}</strong>${w.source_title?`<span lang="grc">${escape(w.source_title)}</span>`:''}</div>${fragmentMeta(w)}${matched.slice(0,3).map(m=>`<p class="fc-hit" lang="grc">${escape(m.ref)} · ${escape(m.text)}</p>`).join('')}</a>`;
      }).join('');
      root.querySelector('#fc-results').innerHTML=rows||'<p>No matching works.</p>';
      root.querySelector('#fc-count').textContent=hits+(hits===1?' work':' works')+(q?' with matching verses':'');
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
