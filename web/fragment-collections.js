/* Complete collection browser; the compact legacy contents remain available via collections=off. */
window.PMVFragmentCollections = (() => {
  // The complete contents are the default. Explicit "off" retains the older,
  // compact contents page as a rollback and comparison view.
  const enabled = new URLSearchParams(location.search).get('collections') !== 'off';
  const escape = s => String(s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const normalize = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/ς/g,'σ');
  const href = fields => {const u=new URL(location.href); ['w','fragment','collection','allworks','author','scope','genre','language','browse','home','focus','cols','right','right2','right3','right4','right5','right6'].forEach(k=>u.searchParams.delete(k)); u.searchParams.set('collections','1'); for(const [k,v] of Object.entries(fields)) u.searchParams.set(k,v); return u.pathname+u.search;};
  let data, sophoclesData, euripidesData, aristophanesData, tocMetadata={authors:{},works:{}};
  // Explicit initial genre membership: extant dramatic works in this catalog.
  // Cyclops and Ichneutae are excluded; fragmentary genre is not inferred
  // from author identity or from absence of a satyr-play label.
  const tragedyKeys = new Set([
    ...Array.from({length:7},(_,i)=>'tlg0085.tlg00'+(i+1)),
    ...Array.from({length:7},(_,i)=>'tlg0011.tlg00'+(i+1)),
    ...Array.from({length:18},(_,i)=>'tlg0006.tlg'+String(i+2).padStart(3,'0'))
  ]);
  const dramaTextgroups = new Set(['tlg0085','tlg0011','tlg0006','tlg0019']);
  const hexameterKeys = new Set([
    'tlg0012.tlg001','tlg0012.tlg002',
    'tlg0020.tlg001','tlg0020.tlg002','tlg0020.tlg003',
    'tlg0001.tlg001','tlg2045.tlg001'
  ]);
  const historyKeys = new Set(['tlg0003.tlg001']);
  const languageNames = {greek:'Greek',latin:'Latin','old-english':'Old English',persian:'Persian',italian:'Italian',japanese:'Japanese'};
  const languageClasses = {greek:'greek-text',latin:'latin-text','old-english':'old-english-text',persian:'persian-text',italian:'italian-text',japanese:'japanese-text'};
  const genreNames = {tragedy:'Tragedy','greek-drama':'Greek drama',hexameter:'Hexametrical poetry',history:'History'};
  function workLanguage(w) {
    const edition=(w.versions||[]).find(v=>v.doc_type==='edition' && Object.values(languageClasses).includes(v.text_class));
    return edition ? Object.keys(languageClasses).find(key=>languageClasses[key]===edition.text_class) : null;
  }
  function inGenre(id,w,genre) {
    if(genre==='tragedy') return tragedyKeys.has(id);
    if(genre==='greek-drama') return dramaTextgroups.has(w.textgroup);
    if(genre==='hexameter') return hexameterKeys.has(id);
    if(genre==='history') return historyKeys.has(id);
    return true;
  }
  function workTarget(w) {
    if(w.pmv_work_key) {
      const target={w:w.pmv_work_key,focus:w.pmv_focus,cols:String(w.pmv_cols||1)};
      const routeKeys=['right','right2','right3','right4','right5','right6'];
      const prefix=w.pmv_work_key.replace('.','_')+'_';
      (w.versions||[]).slice(1,w.pmv_cols||1).forEach((version,index)=>{
        const edition=version.short_id.replace(/grc\d+$/,'').replace(/[-_]$/,'');
        target[routeKeys[index]]=prefix+edition;
      });
      return target;
    }
    if(w.fragments) return {fragment:w.id};
    // Link straight to the first real passage when the catalog exposes its
    // chapter sequence. Previously a TOC card linked only to the work id and
    // the reader immediately rewrote that intermediate URL. WebKit could
    // preserve both reader states, making Back appear to return to the work
    // rather than to the contents page that launched it.
    const firstPart=(w.parts||[]).find(part=>Array.isArray(part.chapters)&&part.chapters.length);
    const firstChapter=firstPart&&firstPart.chapters[0];
    return {w:firstChapter?`${w.id}:${firstChapter}`:w.id};
  }
  function workKeyFor(w) {
    return w.pmv_work_key||w.id||(w.textgroup&&w.work?`${w.textgroup}.${w.work}`:'');
  }
  function workAnchorId(w) {
    return 'work-'+workKeyFor(w).replace(/[^A-Za-z0-9_-]+/g,'-');
  }
  function workCard(w) {
    const body=`<strong>${escape(w.title)}</strong>${fragmentMeta(w)}`;
    const anchor=` id="${escape(workAnchorId(w))}"`;
    return w.evidence_only
      ? `<div${anchor} class="fc-work fc-evidence-only" aria-label="${escape(w.title)}: evidence only">${body}</div>`
      : `<a${anchor} class="fc-work" href="${escape(href(workTarget(w)))}">${body}</a>`;
  }
  function tocForWork(w) {
    const key=workKeyFor(w);
    return (tocMetadata.works||{})[key]||null;
  }
  function fragmentSearchText(w) {
    const toc=tocForWork(w);
    if(toc&&toc.record_type==='fragmentary_play')return (toc.editions||[]).flatMap(edition=>[edition.edition,...(edition.numbers||[])]).join(' ');
    return (w.fragments||[]).map(f=>f.number).join(' ');
  }
  // Count whitespace-delimited tokens containing letters only in the quoted
  // authorial lines. Punctuation and lacuna marks alone do not count as words.
  function wordCount(w) {
    return (w.fragments||[]).reduce((n,f)=>n+f.lines.reduce((m,l)=>m+l.text.split(/\s+/u).filter(t=>/\p{L}/u.test(t)).length,0),0);
  }
  function fragmentNumbers(values) {
    const nums=(Array.isArray(values)?values:(values.fragments||[]).map(f=>f.number)).map(String), ranges=[];
    for(let i=0;i<nums.length;i++) {
      const start=nums[i];let end=start;
      while(i+1<nums.length && /^\d+$/.test(end) && /^\d+$/.test(nums[i+1]) && Number(nums[i+1])===Number(end)+1)end=nums[++i];
      ranges.push(start===end?start:start+'–'+end);
    }
    return ranges.join(', ');
  }
  function fragmentTotals(works) {
    const n=works.reduce((n,w)=>n+(w.fragments||[]).length,0),words=works.reduce((n,w)=>n+wordCount(w),0);
    return n+' fragment'+(n===1?'':'s')+' · '+words.toLocaleString()+' word'+(words===1?'':'s');
  }
  function authorCollectionSummary(name,catalog) {
    const textgroup=Object.keys(catalog.authors||{}).find(key=>catalog.authors[key]===name);
    const stats=textgroup&&(tocMetadata.authors||{})[textgroup];
    if(!stats)return '';
    const surviving=stats.surviving_play_count||0, plays=stats.fragmentary_play_count||0;
    const bits=[];
    if(surviving)bits.push(`${surviving.toLocaleString()} surviving play${surviving===1?'':'s'}`);
    if((stats.editions||[]).length===1) {
      const edition=stats.editions[0], fragments=edition.fragment_count||0;
      if(plays)bits.push(`${plays.toLocaleString()} play${plays===1?'':'s'}`);
      bits.push(`${fragments.toLocaleString()} fragment${fragments===1?'':'s'}`);
      bits.push(edition.edition);
    } else if(plays) {
      bits.push(`${plays.toLocaleString()} fragmentary work${plays===1?'':'s'}`);
      (stats.editions||[]).forEach(edition=>bits.push(`${edition.edition} ${edition.fragment_count.toLocaleString()} fragments`));
    }
    return bits.join(' · ');
  }
  function authorWordTotal(name,catalog) {
    const textgroup=Object.keys(catalog.authors||{}).find(key=>catalog.authors[key]===name);
    if(!textgroup)return null;
    const completeWords=Object.entries(tocMetadata.works||{}).reduce((total,[workKey,work])=>
      workKey.startsWith(textgroup+'.') && work.record_type==='complete_work' && Number.isFinite(work.word_count)
        ? total+work.word_count : total,0);
    const stats=(tocMetadata.authors||{})[textgroup];
    const chronological=((stats&&stats.editions)||[]).map((edition,index)=>({edition,index}));
    // One fragment witness only: the latest scholarly collection. Do not use
    // the date of the physical source edition here: our Dindorf text is from
    // the eighth edition (1893), but the collection dates to 1830 and precedes
    // Nauck. Alternative collections are never added together.
    chronological.sort((a,b)=>(b.edition.collection_order??-1)-(a.edition.collection_order??-1)||b.index-a.index);
    const latest=chronological.length?chronological[0].edition:null;
    const fragmentWords=latest&&Number.isFinite(latest.word_count)?latest.word_count:0;
    const total=completeWords+fragmentWords;
    if(!total)return null;
    return {total,latestEdition:latest?latest.edition:null,completeWords,fragmentWords};
  }
  function versionLang(shortId) {
    let found=null;
    String(shortId||'').split('-').forEach(part=>{const code=part.replace(/\d+$/,'').toLowerCase();if(/^[a-z]{2,4}$/.test(code)&&code!=='tb')found=code;});
    return found;
  }
  function resourceMeta(w) {
    const counts={edition:0,translation:0,commentary:0,scholia:0}, treebanks={};
    const versions=w.versions||[];
    const sourceVersion=versions.find(v=>v&&v.doc_type==='edition');
    const sourceLang=sourceVersion&&versionLang(sourceVersion.short_id);
    versions.forEach(v=>{
      if(!v)return;
      if(Object.prototype.hasOwnProperty.call(counts,v.doc_type))counts[v.doc_type]++;
      else if(v.doc_type==='treebank') {
        const raw=versionLang(v.short_id), scriptCodes=new Set(['grc','ara','fas']);
        const source=raw&&scriptCodes.has(raw)?raw:(sourceLang||'?');
        const annotation=raw&&scriptCodes.has(raw)?'en':(raw||'en');
        const pair=source+'-'+annotation;treebanks[pair]=(treebanks[pair]||0)+1;
      }
    });
    const bits=[];
    if(counts.edition)bits.push(counts.edition+' ed'+(counts.edition===1?'':'s'));
    if(counts.translation)bits.push(counts.translation+' tr');
    if(counts.commentary)bits.push(counts.commentary+' comm');
    if(counts.scholia)bits.push(counts.scholia+' schol');
    Object.keys(treebanks).sort().forEach(lang=>bits.push(treebanks[lang]+' tb '+lang));
    return bits.join(' · ');
  }
  function fragmentMeta(w) {
    const toc=tocForWork(w);
    if(!toc||toc.record_type!=='fragmentary_play') {
      const resources=resourceMeta(w);
      const count=toc&&toc.word_count;
      return `${resources?`<div class="fc-resources">${escape(resources)}</div>`:''}${count!=null?`<div class="fc-word-count">${count.toLocaleString()} words</div><div class="fc-meta" title="${escape(tocMetadata.counting_note||'')}">Counted in ${escape(toc.counted_edition||toc.counted_version||'source edition')}</div>`:''}`;
    }
    const rows=(toc.editions||[]).map(edition=>{
      const numbers=fragmentNumbers(edition.numbers||[]);
      const fragments=edition.fragment_count||0, words=edition.word_count||0;
      return `<div class="fc-fragment-edition"><span><b>${escape(edition.edition)}</b>${numbers?' '+escape(numbers):''}</span><small>${fragments.toLocaleString()} fr · ${words.toLocaleString()} word${words===1?'':'s'}</small></div>`;
    }).join('');
    return rows
      ? `<div class="fc-fragment-editions" title="${escape(tocMetadata.counting_note||'')}">${rows}</div>`
      : '<div class="fc-meta">Evidence only; no separately quoted fragment in this edition</div>';
  }
  function browseNavigation(catalog) {
    const p=new URLSearchParams(location.search), raw=p.get('w')||'';
    const globalLibrary=p.has('browse');
    const workTextgroup=raw ? (raw.startsWith('urn:cts:') ? raw.split(':')[3].split('.')[0] : raw.split('.')[0]) : null;
    const tg=globalLibrary ? null : p.get('author') || workTextgroup || (p.has('collection')||p.has('fragment')||p.has('allworks')?'tlg0085':null);
    const author=tg&&((catalog.authors||{})[tg]||tg);
    const nav=document.createElement('nav');nav.className='fc-browse-nav';nav.setAttribute('aria-label','Browse the library');
    const links=[['Languages',{home:'languages'}]];
    const greekContext=(tg&&tg.startsWith('tlg'))||p.get('language')==='greek'||p.has('genre');
    if(greekContext) {
      links.push(['Greek',{language:'greek'}],['Fragments',tg==='tlg0011'?{author:'tlg0011',scope:'fragments'}:{collection:'aeschylus-fragments'}]);
      if(tg==='tlg0085') links.push(['Surviving works of '+author,{author:tg,scope:'surviving'}]);
      if(tg) links.push(['All works of '+author,{author:tg}]);
      links.push(['Tragedy',{genre:'tragedy',language:'greek'}]);
    }
    links.push(['All works',{browse:'all'}]);
    nav.innerHTML='<span>Browse:</span>'+links.map(([label,route])=>`<a href="${escape(href(route))}">${escape(label)}</a>`).join('');
    const banner=document.getElementById('perseus-banner');if(banner)banner.after(nav);
    const indexNav=nav.cloneNode(true);indexNav.classList.add('fc-index-nav');
    document.getElementById('splash-view-root').prepend(indexNav);
  }
  function renderHome(root,catalog) {
    const visible=Object.values(catalog.works).filter(w=>!w.fragment_corpus);
    const counts={};
    Object.keys(languageNames).forEach(lang=>counts[lang]=visible.filter(w=>workLanguage(w)===lang).length);
    const greekLinks=[['Tragedy','tragedy'],['Greek drama','greek-drama'],['Hexametrical poetry','hexameter'],['History','history']];
    root.innerHTML=`<main class="fc-page fc-home"><h1>Language collections</h1><p>Choose the language of the original work.</p><div class="fc-language-grid">${Object.entries(languageNames).map(([id,title])=>`<section class="fc-language-card"><a class="fc-language-title" href="${escape(href({language:id}))}">${escape(title)} <span>${counts[id]} work${counts[id]===1?'':'s'}</span></a>${id==='greek'?`<nav aria-label="Greek collections">${greekLinks.map(([label,genre])=>`<a href="${escape(href({language:'greek',genre}))}">${escape(label)}</a>`).join('')}</nav>`:''}</section>`).join('')}</div><p class="fc-home-all"><a href="${escape(href({browse:'all'}))}">Browse all works and authors</a></p></main>`;
  }
  function renderLibrary(root,catalog,params) {
    const author=params.get('author'), genre=params.get('genre'), language=params.get('language'), scope=params.get('scope');
    const authorName=author&&((catalog.authors||{})[author]||author);
    const title=genre ? genreNames[genre] : author ? (scope==='surviving'?'Surviving works of ':scope==='fragments'?'Fragments of ':'All works of ')+authorName : language ? languageNames[language] : 'All works';
    const standard=Object.entries(catalog.works).filter(([id,w])=>scope!=='fragments'&&!w.experimental_fragment && (!author||w.textgroup===author) && (!language||workLanguage(w)===language) && (!genre||inGenre(id,w,genre))).map(([id,w])=>({...w,id,author:(catalog.authors||{})[w.textgroup]||w.textgroup}));
    const catalogFragments=Object.entries(catalog.works).filter(([id,w])=>w.experimental_fragment && !w.fragment_corpus && w.textgroup!=='tlg0085' && w.textgroup!=='tlg0011' && w.textgroup!=='tlg0006' && w.textgroup!=='tlg0019' && (!author||w.textgroup===author) && (!language||language==='greek') && (!genre||genre==='greek-drama')).map(([id,w])=>({...w,id,author:(catalog.authors||{})[w.textgroup]||w.textgroup}));
    const includeFragments=scope!=='surviving'&&(!author||author==='tlg0085')&&(!language||language==='greek')&&(!genre||genre==='greek-drama');
    const fragments=includeFragments ? Object.values(data.works).map(w=>{
      const versions=w.versions||[], first=versions[0];
      const edition=first&&first.short_id.replace(/grc\d+$/,'').replace(/[-_]$/,'');
      return {...w,author:'Aeschylus',pmv_work_key:'tlg0085.'+w.work,
        pmv_focus:edition?'tlg0085_'+w.work+'_'+edition:'',
        pmv_cols:Math.min(2,versions.length)||1};
    }) : [];
    const includeSophoclesFragments=scope!=='surviving'&&(!author||author==='tlg0011')&&(!language||language==='greek')&&(!genre||genre==='greek-drama');
    const sophoclesFragments=includeSophoclesFragments&&sophoclesData ? Object.values(sophoclesData.works).map(w=>{
      const versions=w.versions||[], first=versions[0];
      const edition=first&&first.short_id.replace(/grc\d+$/,'').replace(/[-_]$/,'');
      return {...w,author:'Sophocles',pmv_work_key:'tlg0011.'+w.work,pmv_focus:edition?'tlg0011_'+w.work+'_'+edition:'',pmv_cols:Math.min(3,versions.length)||1};
    }) : [];
    const includeEuripidesFragments=scope!=='surviving'&&(!author||author==='tlg0006')&&(!language||language==='greek')&&(!genre||genre==='greek-drama');
    const euripidesFragments=includeEuripidesFragments&&euripidesData ? Object.values(euripidesData.works).map(w=>{
      const versions=w.versions||[], first=versions[0];
      const edition=first&&first.short_id.replace(/grc\d+$/,'').replace(/[-_]$/,'');
      return {...w,author:'Euripides',pmv_work_key:'tlg0006.'+w.work,pmv_focus:edition?'tlg0006_'+w.work+'_'+edition:'',pmv_cols:Math.min(2,versions.length)||1};
    }) : [];
    const includeAristophanesFragments=scope!=='surviving'&&(!author||author==='tlg0019')&&(!language||language==='greek')&&(!genre||genre==='greek-drama');
    const aristophanesFragments=includeAristophanesFragments&&aristophanesData ? Object.values(aristophanesData.works).map(w=>{
      const versions=w.versions||[], first=versions[0];
      const edition=first&&first.short_id.replace(/grc\d+$/,'').replace(/[-_]$/,'');
      return {...w,author:'Aristophanes',pmv_work_key:'tlg0019.'+w.work,pmv_focus:edition?'tlg0019_'+w.work+'_'+edition:'',pmv_cols:1};
    }) : [];
    const workRank=w=>{const toc=tocForWork(w);return toc&&toc.surviving_play?0:toc&&toc.record_type==='fragmentary_play'?1:2;};
    const works=[...standard,...catalogFragments,...fragments,...sophoclesFragments,...euripidesFragments,...aristophanesFragments].sort((a,b)=>a.author.localeCompare(b.author)||workRank(a)-workRank(b)||a.title.localeCompare(b.title));
    const scopedAuthors={tlg0085:'Aeschylus',tlg0011:'Sophocles',tlg0006:'Euripides',tlg0019:'Aristophanes'};
    const authorScope=scopedAuthors[author] ? `<nav class="fc-scope-links" aria-label="${scopedAuthors[author]} work scope"><a href="${escape(href({author,scope:'surviving'}))}" ${scope==='surviving'?'aria-current="page"':''}>Surviving works</a><span>→</span><a href="${escape(href({author}))}" ${!scope?'aria-current="page"':''}>All works</a><span>→</span><a href="${escape(href({author,scope:'fragments'}))}" ${scope==='fragments'?'aria-current="page"':''}>Fragments</a></nav>` : '';
    const greekCollections=(language==='greek'||genre) ? `<nav class="fc-subcollections" aria-label="Greek collections"><a href="${escape(href({language:'greek'}))}">All Greek</a><a href="${escape(href({language:'greek',genre:'tragedy'}))}">Tragedy</a><a href="${escape(href({language:'greek',genre:'greek-drama'}))}">Greek drama</a><a href="${escape(href({language:'greek',genre:'hexameter'}))}">Hexametrical poetry</a><a href="${escape(href({language:'greek',genre:'history'}))}">History</a></nav>` : '';
    const description=genre==='tragedy' ? 'Currently cataloged surviving tragedies of Aeschylus, Sophocles and Euripides. Fragmentary works await genre review; satyr plays are excluded.' : genre==='greek-drama' ? 'Surviving tragedy, satyr drama and comedy, together with fragmentary Aeschylean, Sophoclean, Euripidean, and Aristophanic work records in this trial.' : genre==='history' ? 'Thucydides is the historical work currently available.' : '';
    const breadcrumb=language ? languageNames[language] : genre ? 'Greek' : '';
    root.innerHTML=`<main class="fc-page"><nav><a href="${escape(href({home:'languages'}))}">Language collections</a>${breadcrumb?' / '+escape(breadcrumb):''}</nav><h1>${escape(title)}</h1>${greekCollections}${authorScope}${description?`<p>${escape(description)}</p>`:''}<label class="fc-library-filter">Find a work or author<input id="fc-library-filter" type="search" placeholder="Title or author"></label><p id="fc-library-count" aria-live="polite"></p><div id="fc-library-results"></div></main>`;
    const input=root.querySelector('#fc-library-filter');
    let expanded={};
    // Global All works is a reset point: it starts with no author privileged.
    // Author and genre views may remember independently opened groups.
    if(!params.has('browse')) try {expanded=JSON.parse(sessionStorage.getItem('pmv-author-groups')||'{}');} catch(e) {}
    const draw=()=>{
      const q=normalize(input.value.trim());
      const matches=works.filter(w=>normalize(w.title+' '+w.author+' '+(w.source_title||'')+' '+fragmentSearchText(w)).includes(q));
      const groups=new Map();
      matches.forEach(w=>{if(!groups.has(w.author))groups.set(w.author,[]);groups.get(w.author).push(w);});
      root.querySelector('#fc-library-count').textContent=matches.length+(matches.length===1?' work':' works');
      const results=root.querySelector('#fc-library-results');
      results.innerHTML=[...groups].map(([name,items])=>{
        const open=q || author || expanded[name];
        const collectionSummary=authorCollectionSummary(name,catalog);
        const wordTotal=authorWordTotal(name,catalog);
        const wordSummary=wordTotal?`<span class="fc-author-word-total" title="One counted edition per complete work plus the latest fragment collection in scholarly chronology${wordTotal.latestEdition?' ('+escape(wordTotal.latestEdition)+')':''}">— ${wordTotal.total.toLocaleString()} words</span>`:'';
        const authorSummary=collectionSummary?`<small class="fc-author-fragments">${escape(collectionSummary)}</small>`:'';
        const surviving=items.filter(w=>tocForWork(w)&&tocForWork(w).surviving_play);
        const fragmentary=items.filter(w=>tocForWork(w)&&tocForWork(w).record_type==='fragmentary_play');
        const other=items.filter(w=>!surviving.includes(w)&&!fragmentary.includes(w));
        const sections=[];
        if(surviving.length)sections.push(`<section class="fc-work-section"><h3>Surviving plays</h3><div class="fc-work-list">${surviving.map(workCard).join('')}</div></section>`);
        if(fragmentary.length)sections.push(`<section class="fc-work-section"><h3>Fragmentary plays and attributed works</h3><div class="fc-work-list">${fragmentary.map(workCard).join('')}</div></section>`);
        if(other.length)sections.push(`<section class="fc-work-section"><h3>${surviving.length||fragmentary.length?'Other works':'Works'}</h3><div class="fc-work-list">${other.map(workCard).join('')}</div></section>`);
        return `<details class="fc-author-group" data-author-name="${escape(name)}" ${open?'open':''}><summary>${escape(name)}${wordSummary}${authorSummary}</summary>${sections.join('')}</details>`;
      }).join('')||'<p>No matching works.</p>';
      results.querySelectorAll('.fc-author-group').forEach(group=>group.addEventListener('toggle',()=>{
        if(q)return;
        expanded[group.dataset.authorName]=group.open;
        if(!params.has('browse')) try {sessionStorage.setItem('pmv-author-groups',JSON.stringify(expanded));} catch(e) {}
      }));
      // The collection page is rendered after the document's normal fragment
      // navigation pass. Honor a work breadcrumb once its card now exists.
      const targetId=decodeURIComponent(location.hash.slice(1));
      if(targetId) requestAnimationFrame(()=>document.getElementById(targetId)?.scrollIntoView({block:'center'}));
    };
    input.addEventListener('input',draw);draw();
  }
  async function attach(catalog) {
    if (!enabled) return;
    const root=document.getElementById('splash-view-root');
    const banner=document.createElement('div'); banner.className='fc-experiment';
    banner.innerHTML=`<span>Complete collection contents</span><span class="fc-experiment-actions"><label class="fc-theme-picker">Theme <select class="pmv-theme-select" aria-label="Viewer color theme"><option value="aegean">Aegean</option><option value="slate">Slate &amp; amber</option><option value="olive">Olive &amp; copper</option><option value="legacy">Legacy burgundy</option></select></label><a href="${escape(href({collections:'off'}))}">Use compact contents</a></span>`;
    const collectionThemePicker=banner.querySelector('.pmv-theme-select');
    collectionThemePicker.value=document.documentElement.dataset.pmvTheme||'aegean';
    collectionThemePicker.addEventListener('change',()=>window.setPmvColorTheme(collectionThemePicker.value));
    document.body.prepend(banner);
    try {
      const tocResponse=await fetch('./site/toc-metadata.json', {cache:'no-store'});
      if(!tocResponse.ok)throw new Error('Contents metadata could not be loaded');
      tocMetadata=await tocResponse.json();
      const embedded=document.getElementById('fragment-collection-data');
      if(embedded) data=JSON.parse(embedded.textContent);
      else {
        const [aeschylusResponse,sophoclesResponse,euripidesResponse,aristophanesResponse]=await Promise.all([
          fetch('./site/fragment-collections.json', {cache:'no-store'}),
          fetch('./site/tlg0011-fragment-collections.json', {cache:'no-store'}),
          fetch('./site/tlg0006-fragment-collections.json', {cache:'no-store'}),
          fetch('./site/tlg0019-fragment-collections.json', {cache:'no-store'})
        ]);
        if(!aeschylusResponse.ok) throw new Error('Fragment collection could not be loaded');
        data=await aeschylusResponse.json();
        sophoclesData=sophoclesResponse.ok?await sophoclesResponse.json():{works:{}};
        euripidesData=euripidesResponse.ok?await euripidesResponse.json():{works:{}};
        aristophanesData=aristophanesResponse.ok?await aristophanesResponse.json():{works:{}};
      }
      Object.values(data.works||{}).forEach(w=>{
        const versions=w.versions||[], first=versions[0];
        const edition=first&&first.short_id.replace(/grc\d+$/,'').replace(/[-_]$/,'');
        w.pmv_work_key='tlg0085.'+w.work;
        w.pmv_focus=edition?'tlg0085_'+w.work+'_'+edition:'';
        w.pmv_cols=Math.min(2,versions.length)||1;
      });
      const params=new URLSearchParams(location.search);
      if(params.get('home')==='languages') renderHome(root,catalog);
      else if(params.has('fragment')) renderWork(root,params.get('fragment'));
      else if(params.has('collection') || params.has('allworks')) renderCollection(root,catalog,params.has('allworks'),params.get('collection'));
      else if(params.has('browse') || params.has('author') || params.has('genre') || params.has('language') || !params.has('w')) renderLibrary(root,catalog,params);
      browseNavigation(catalog);
    } catch(e) {banner.append(document.createTextNode(' · '+e.message));}
  }
  function renderCollection(root,catalog,all,collectionId) {
    const coll=data.collections.find(c=>c.id===collectionId) || data.collections[0];
    const ids=new Set(coll.members);
    const fragmentWorks=Object.values(data.works).filter(w=>ids.has(w.id));
    const extant=Object.entries(catalog.works).filter(([k,w])=>w.textgroup==='tlg0085'&&!w.experimental_fragment).map(([k,w])=>({...w,id:k,title:w.title,status:'Survives complete',extant:true})).sort((a,b)=>a.title.localeCompare(b.title));
    const pool=(all?[...extant,...fragmentWorks]:fragmentWorks).sort((a,b)=>a.title.localeCompare(b.title));
    const survivingContext=!all&&coll.id==='aeschylus-fragments' ? `<details class="fc-surviving-context" open><summary>Surviving works <span>(${extant.length})</span></summary><div class="fc-work-list">${extant.map(w=>`<a class="fc-work" href="${escape(href({w:w.id}))}"><strong>${escape(w.title)}</strong>${fragmentMeta(w)}</a>`).join('')}</div></details>` : '';
    const incertae=data.works['aeschylus-incertae'], dubia=data.works['aeschylus-dubia-spuria'];
    const assigned=fragmentWorks.filter(w=>w!==incertae&&w!==dubia);
    const authorStats=(tocMetadata.authors||{}).tlg0085||{fragmentary_play_count:fragmentWorks.length,editions:[]};
    const editionSummary=(authorStats.editions||[]).map(edition=>`${edition.edition} ${edition.fragment_count.toLocaleString()} fragments, ${edition.word_count.toLocaleString()} words`).join(' · ');
    const collectionSummary=`${authorStats.fragmentary_play_count.toLocaleString()} fragmentary work headings${editionSummary?' · '+editionSummary:''}`;
    const categorySummary=!all&&coll.id==='aeschylus-fragments' ? `<div class="fc-fragment-categories"><a href="#fragmentary-works"><strong>Named and attributed works</strong><span>${assigned.length.toLocaleString()} work headings</span></a><a href="${escape(href(workTarget(incertae)))}"><strong>Uncertain-play fragments</strong><span>Dindorf 266–427 · Nauck 282–451</span></a><a href="${escape(href(workTarget(dubia)))}"><strong>Dubious and spurious fragments</strong><span>Nauck 452–466</span></a></div>` : '';
    root.innerHTML=`<main class="fc-page"><nav><a href="${escape(href({}))}">All authors</a> / Aeschylus</nav>
      <h1>${all?'Aeschylus — works':'Aeschylus — '+escape(coll.title)}</h1>
      <div class="fc-tabs"><a href="${escape(href({collection:'aeschylus-fragments'}))}">Fragments</a><a href="${escape(href({allworks:'aeschylus'}))}">All Aeschylus works</a><a href="${escape(href({collection:'nauck1889'}))}">Nauck 1889</a></div>
      <p>${all ? 'Surviving plays and individually identified fragmentary works.' : escape(collectionSummary)}</p>
      ${categorySummary}
      ${survivingContext}
      ${!all?'<h2 id="fragmentary-works" class="fc-fragment-heading">Fragmentary works</h2>':''}
      <div class="fc-controls"><label>Find a work or fragment number<input id="fc-filter" placeholder="Athamas, Danaides, 149…"></label><label>Search fragment verses<input id="fc-search" placeholder="ποδῶκες"></label></div>
      <div id="fc-count" aria-live="polite"></div><div id="fc-results" class="fc-work-list"></div>
      <details class="fc-scope"><summary>About this fragment collection</summary><p>${escape(data.editorial_note)}</p><p>The collection preserves each edition's native numbering and reports its fragment and word counts separately. Counts describe the encoding, not a settled total of historical plays. Verse search covers this collection, not the surviving plays. Word counts include tokens containing letters in the encoded authorial lines; transmitting sources, editorial notes, and punctuation-only tokens are excluded.</p></details></main>`;
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
