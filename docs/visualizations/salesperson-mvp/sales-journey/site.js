const scopeNames = {job:'Whole job',street:'Street A-B',side:'Side B-C',range:'Street A-B / selected range',gate:'Street gate',pool:'Pool'};
const evidenceMeta = {
  contract:{scope:'job',kind:'Signed instruction',status:'Confirmed in example',by:'Sam Example',date:'06 Sep 2026'},
  sketch:{scope:'job',kind:'Signed drawing',status:'Recorded dimensions',by:'Taylor',date:'06 Sep 2026'},
  amendment:{scope:'range',kind:'Signed instruction',status:'Confirmed / A-B, 3-8 m',by:'Sam Example',date:'06 Sep 2026'},
  message:{scope:'gate',kind:'Copied customer message',status:'Open question',by:'Sam Example',date:'06 Sep 2026'},
  photo:{scope:'gate',kind:'Illustrative photo',status:'Not measured evidence',by:'AI-generated example',date:'06 Sep 2026'},
  construction:{scope:'side',kind:'Planned drawing',status:'Final levels unconfirmed',by:'Example drawing / rev 3',date:'06 Sep 2026'},
};
function initializeSite() {
  state.site={stage:'Under construction',workArea:'Entire house / yard',pool:'Planned',poolRole:'Nearby only',poolRefs:['side','gate'],finished:'Unconfirmed',action:'Remeasure after wall completion'};
  state.siteDraft=structuredClone(state.site);
  state.bases.side='Masonry wall';
  const profile={ground:'Level',rise:0,groundStep:0.5,groundSource:'Measured',baseShape:'Follows ground',baseStart:0,baseEnd:0,baseStep:0.5,condition:'Existing',top:'Follow base',fenceStep:0.5};
  state.profiles={street:{...profile},side:{...profile,ground:'Slope',rise:0.3,groundSource:'From drawing',baseStart:0.6,baseEnd:0.6,condition:'Planned'}};
  state.profileDraft=structuredClone(state.profiles);
  state.detailTab='Fence';state.layoutTab='Fence';state.evidenceScope='job';state.notes=[];
  state.noteDraft={scope:'gate',kind:'Salesperson note',status:'Open question',text:'',source:''};
}
function siteDirty(){return !same(state.site,state.siteDraft);}
function profileDirty(run){return !same(state.profiles[run],state.profileDraft[run]);}
function groundAt(p,t){
  const rise=Number(p.rise);
  return p.ground==='Slope'?rise*t:p.ground==='Step'?(t>=Number(p.groundStep)?rise:0):0;
}
function baseAt(p,base,t){
  const ground=groundAt(p,t),a=Number(p.baseStart),b=groundAt(p,1)+Number(p.baseEnd);
  if(base==='Soil')return ground;
  if(p.baseShape==='Level top')return a;
  if(p.baseShape==='Sloped top')return a+(b-a)*t;
  if(p.baseShape==='Stepped top')return t>=Number(p.baseStep)?b:a;
  return ground+a;
}
function profileError(p,base){
  for(const key of ['rise','baseStart','baseEnd','groundStep','baseStep','fenceStep'])if(p[key]===''||!Number.isFinite(Number(p[key])))return 'Enter all profile measurements, or select Unmeasured ground.';
  if(Math.abs(Number(p.rise))>2||Number(p.baseStart)<0||Number(p.baseEnd)<0||Number(p.baseStart)>2||Number(p.baseEnd)>2)return 'Ground rise: -2 to 2 m. Base height: 0 to 2 m.';
  if(['groundStep','baseStep','fenceStep'].some(k=>Number(p[k])<=0||Number(p[k])>=1))return 'Step positions must be inside the selected stretch.';
  const samples=[...Array.from({length:101},(_,i)=>i/100),Number(p.groundStep)-0.0001,Number(p.groundStep),Number(p.baseStep)-0.0001,Number(p.baseStep)];
  if(base!=='Soil'&&samples.some(t=>baseAt(p,base,t)<groundAt(p,t)-0.001))return 'The base top cannot pass below the ground. Check both profiles.';
  return '';
}
function activeProfile(run,preview=true){
  const draft=preview&&state.step===2&&state.selected===run;
  const d=state.detailsDraft[run],p=draft?state.profileDraft[run]:state.profiles[run];
  const valid=!profileError(p,d.base)&&d.height!==''&&Number(d.height)>=0.2&&Number(d.height)<=3;
  return {p:draft&&valid?p:state.profiles[run],base:draft&&valid?d.base:state.bases[run],height:draft&&valid?Number(d.height):state.heights[run]};
}
function detailTabs(){return `<div class="detail-tabs" role="group" aria-label="Profile layer">${['Ground','Base','Fence'].map(x=>`<button data-detail-tab="${x}" aria-pressed="${state.detailTab===x}">${icon(x==='Ground'?'mountain':x==='Base'?'brick-wall':'fence')}${x}</button>`).join('')}</div>`;}
function profileFields(){
  const run=state.selected,d=state.detailsDraft[run],p=state.profileDraft[run],num='type="number" step="0.1"';
  const pos=(label,id,value)=>input(label.replace('% from start','m from start'),id,Number((Number(value)*state[run]).toFixed(2)),`type="number" min="0.1" max="${state[run]-0.1}" step="0.1"`);
  if(state.detailTab==='Ground')return `${choose('Ground profile','profile-ground',p.ground,['Level','Slope','Step','Unmeasured'])}
    ${['Slope','Step'].includes(p.ground)?input('End minus start elevation (m)','profile-rise',p.rise,num+' min="-2" max="2"'):''}
    ${p.ground==='Step'?pos('Step position (% from start)','profile-groundStep',p.groundStep):''}
    ${choose('Measurement source','profile-groundSource',p.groundSource,['Measured','From drawing','Unconfirmed'])}
    <p class="info-note">Start = 0 m local reference. Positive rise goes uphill. Final site levels are recorded separately.</p>`;
  if(state.detailTab==='Base')return `${choose('Supporting base','base',d.base,['Soil','Concrete','Masonry wall'])}
    ${choose('Base condition','profile-condition',p.condition,['Existing','Under construction','Planned'])}
    ${d.base!=='Soil'?`${choose('Base top','profile-baseShape',p.baseShape,['Follows ground','Level top','Sloped top','Stepped top'])}
    ${input('Base height at start (m)','profile-baseStart',p.baseStart,num+' min="0" max="2"')}
    ${['Sloped top','Stepped top'].includes(p.baseShape)?input('Base height at end (m)','profile-baseEnd',p.baseEnd,num+' min="0" max="2"'):''}
    ${p.baseShape==='Stepped top'?pos('Base step (% from start)','profile-baseStep',p.baseStep):''}
    <p class="info-note">Base heights are above local ground, not fence heights.</p>`:'<p class="info-note">Fence supported directly in soil. No raised base is recorded.</p>'}`;
  return `${input('Length (m)','saved-length',state[run],'readonly')}
    ${input(p.top==='Follow base'?'Fence height above base (m)':'Minimum fence height above base (m)','height',d.height,num+' min="0.2" max="3"')}
    ${choose('Sold model','model',d.model,['Slat panel','Routed vinyl'])}
    ${choose('Fence top intent','profile-top',p.top,['Follow base','Level top','Stepped top'])}
    ${p.top==='Stepped top'?pos('Fence step (% from start)','profile-fenceStep',p.fenceStep):''}`;
}
function siteFields(mode){
  const d=state.siteDraft;
  if(mode==='job')return `${choose('Site stage','site-stage',d.stage,['Existing site','Under construction','Planned'])}
    ${d.stage!=='Existing site'?choose('Work area','site-workArea',d.workArea,['House','Yard','Entire house / yard']):''}
    ${choose('Finished ground levels','site-finished',d.finished,['Confirmed','Unconfirmed'])}
    ${input('Next site action','site-action',d.action,'maxlength="160"')}
    <p class="draft-status" id="site-draft-status">${siteDirty()?'Site draft / not saved':'Site context recorded'}</p>
    <button class="secondary" id="save-site">${icon('check')} Save site context</button>`;
  return `${choose('Pool','site-pool',d.pool,['None','Existing','Planned'])}
    ${d.pool!=='None'?`${choose('Fence relationship','site-poolRole',d.poolRole,['Nearby only','Pool enclosure','Unconfirmed'])}
    <fieldset class="scope-checks"><legend>Affected components</legend>${['street','side','gate'].map(k=>`<label><input type="checkbox" data-pool-ref="${k}" ${d.poolRefs.includes(k)?'checked':''}>${scopeNames[k]}</label>`).join('')}</fieldset>
    <p class="info-note">Pool outline is a reference only. No pool-safety approval is implied.</p>`:''}
    <p class="draft-status" id="site-draft-status">${siteDirty()?'Site draft / not saved':'Site context recorded'}</p>
    <button class="primary" id="save-site">${icon('check')} Save site context</button>
    <button class="secondary" data-go="0">${icon('hard-hat')} Construction status</button>`;
}
function bindSite(){
  document.querySelectorAll('[data-detail-tab]').forEach(b=>b.onclick=()=>{state.detailTab=b.dataset.detailTab;state.source=state.detailTab==='Fence'?'contract':'construction';render();});
  document.querySelectorAll('[data-layout-tab]').forEach(b=>b.onclick=()=>{state.layoutTab=b.dataset.layoutTab;render();});
  document.querySelectorAll('[id^="profile-"]').forEach(el=>el.oninput=()=>{
    const key=el.id.slice(8);state.profileDraft[state.selected][key]=key.endsWith('Step')?Number(el.value)/state[state.selected]:el.value;
    if(el.tagName==='SELECT'){render();return;}
    $('#draft-status').textContent='Profile draft / not saved';$('#form-error').textContent=profileError(state.profileDraft[state.selected],state.detailsDraft[state.selected].base);draw();saveLabel();
  });
  document.querySelectorAll('[id^="site-"]').forEach(el=>{if(!['INPUT','SELECT'].includes(el.tagName))return;el.oninput=()=>{
    state.siteDraft[el.id.slice(5)]=el.value;
    if(el.tagName==='SELECT'){render();return;}
    $('#site-draft-status').textContent='Site draft / not saved';saveLabel();
  };});
  document.querySelectorAll('[data-pool-ref]').forEach(el=>el.onchange=()=>{
    state.siteDraft.poolRefs=[...document.querySelectorAll('[data-pool-ref]:checked')].map(x=>x.dataset.poolRef);
    $('#site-draft-status').textContent='Site draft / not saved';saveLabel();draw();
  });
  if($('#save-site'))$('#save-site').onclick=()=>{state.site=structuredClone(state.siteDraft);render();saveLabel('Site context saved in demo');};
}
function evidenceScope(){return state.step===0?'job':state.step===1&&state.layoutTab==='Site'?'pool':state.step===3?'range':state.step===4?'gate':state.step===5?'job':state.selected;}
function evidenceSources(){
  const selected=evidenceScope();
  const meta=evidenceMeta[state.source];
  $('#evidence-target').textContent=scopeNames[selected];
  $('#source-link').textContent=meta?scopeNames[meta.scope]:scopeNames[selected];
  $('#source-meta').innerHTML=meta?`<strong>${esc(meta.kind)}</strong><span>${esc(meta.status)}</span><span>${esc(meta.by)} / ${esc(meta.date)}</span>`:'';
  const notes=state.notes.filter(n=>selected==='job'||n.scope===selected);
  $('#linked-notes').innerHTML=notes.map(n=>`<article class="linked-note"><strong>${esc(n.kind)} / ${esc(n.target)}</strong><p>${esc(n.text)}</p><small>${esc(n.status)} / Taylor${n.source?' / '+esc(sourceNames[n.source]):''}</small></article>`).join('');
  document.querySelectorAll('[data-source]').forEach(b=>{
    const scope=evidenceMeta[b.dataset.source]?.scope;
    b.classList.toggle('linked-source',scope===selected);
    b.title=scope?'Attached to '+scopeNames[scope]:'';
  });
}
function openNote(){
  if(!state.noteDraft.text)state.noteDraft.scope=evidenceScope();
  const d=state.noteDraft;
  $('#note-content').innerHTML=`${choose('Attach to','note-scope',d.scope,Object.keys(scopeNames))}
    ${choose('Record type','note-kind',d.kind,['Salesperson note','Customer message','Photo observation'])}
    ${choose('Status','note-status',d.status,['Open question','Observed','Confirmed instruction'])}
    <label>Note<textarea id="note-text" rows="4" maxlength="1000">${esc(d.text)}</textarea></label>
    <label>Supporting source<select id="note-source"><option value="">None</option>${Object.entries(sourceNames).map(([id,name])=>`<option value="${id}" ${d.source===id?'selected':''}>${name}</option>`).join('')}</select></label>
    <p class="info-note">Local example only. A note does not change the signed specification.</p><p class="error" id="note-error" role="status"></p>
    <button class="primary" id="save-note">${icon('plus')} Attach note</button>`;
  $('#note-scope').querySelectorAll('option').forEach(o=>{const value=o.value;o.value=value;o.textContent=scopeNames[value];});
  for(const key of ['scope','kind','status','text','source'])$('#note-'+key).oninput=()=>{state.noteDraft[key]=$('#note-'+key).value;};
  $('#save-note').onclick=()=>{
    if(!state.noteDraft.text.trim()){$('#note-error').textContent='Enter a note before attaching it.';return;}
    if(state.noteDraft.scope==='range'&&!rangeValid(state.range)){$('#note-error').textContent='Select a valid range before attaching a note.';return;}
    const n=structuredClone(state.noteDraft);n.target=scopeNames[n.scope];
    if(n.scope==='range')n.target='Street A-B / '+fmt(state.range.start)+'-'+fmt(state.range.end)+' m';
    state.notes.push(n);state.noteDraft={scope:evidenceScope(),kind:'Salesperson note',status:'Open question',text:'',source:''};$('#note-dialog').close();sources();saveLabel('Note attached in demo');
  };
  lucide.createIcons();$('#note-dialog').showModal();
}
function sitePlan(){
  const s=state.step<=1?state.siteDraft:state.site,B=100+state.street*48;
  const work=s.stage!=='Existing site';
  let art='<defs><pattern id="work-hatch" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M0 10L10 0" stroke="#b4bbc0" stroke-width="0.7"/></pattern></defs>';
  if(work){const house=$('#house-reference'),houseOnly=s.workArea==='House';
    const x=houseOnly?Number(house.getAttribute('x')):78,y=houseOnly?112:34,w=houseOnly?Number(house.getAttribute('width')):B-38,h=houseOnly?110:203;
    art+=`<rect data-work-zone="true" x="${x}" y="${y}" width="${w}" height="${h}" fill="url(#work-hatch)" fill-opacity="0.35" stroke="#7c8389" stroke-dasharray="6 5" pointer-events="none"/><text x="85" y="24" font-size="12" fill="#535b62">${esc(s.workArea)} / ${esc(s.stage.toLowerCase())}</text>`;
  }
  if(s.pool!=='None'){
    const x=state.street>=8?B-140:B+82,y=state.street<4?242:112;
    art+=`<g data-landmark="pool" role="button" tabindex="0" aria-label="Edit pool context" class="fence-hit"><rect x="${x}" y="${y}" width="96" height="92" rx="5" fill="#dbedf1" stroke="#397d90" stroke-width="2" ${s.pool==='Planned'?'stroke-dasharray="6 4"':''}/><text x="${x+48}" y="${y+37}" font-size="14" fill="#26596a" text-anchor="middle">Pool</text><text x="${x+48}" y="${y+58}" font-size="12" fill="#26596a" text-anchor="middle">${s.pool}</text><text x="${x+48}" y="${y+78}" font-size="10" fill="#26596a" text-anchor="middle">Reference only</text></g>`;
  }
  $('#plan').insertAdjacentHTML('beforeend',art);
}
function profileElevation(){
  const rows=[];
  for(const [index,run] of ['street','side'].entries()){
    if(state.drawn<=index)continue;
    const {p,base,height}=activeProfile(run),r=run==='street'?shownRange():null,g=run==='street'&&state.step>=4?shownGate():null;
    const breaks=[0,1];
    if(p.ground==='Step')breaks.push(Number(p.groundStep));
    if(p.baseShape==='Stepped top'&&base!=='Soil')breaks.push(Number(p.baseStep));
    if(p.top==='Stepped top')breaks.push(Number(p.fenceStep));
    if(r)breaks.push(r.start/state[run],r.end/state[run]);
    if(g)breaks.push(g.offset/state[run],(g.offset+g.width)/state[run]);
    const pts=[...new Set(breaks)].filter(t=>t>=0&&t<=1).sort((a,b)=>a-b);
    rows.push({run,index,p,base,height,r,g,pts,origin:index?groundAt(activeProfile('street').p,1):0});
  }
  const samples=rows.flatMap(row=>row.pts.flatMap(t=>[row.origin+groundAt(row.p,t),row.origin+baseAt(row.p,row.base,t)+Math.max(row.height,row.r?.height||0)]));
  const min=Math.min(0,...samples)-0.2,max=Math.max(2.5,...samples)+0.2,Y=z=>177-(z-min)*130/(max-min),S=610/(state.street+state.side),X=(row,t)=>35+(row.index?state.street*S+30:0)+t*state[row.run]*S;
  let art='<defs><pattern id="profile-slats" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M4 0v8" stroke="#6e9482" stroke-width="0.6"/></pattern></defs>';
  for(const row of rows){const {run,p,base,height,r,g,pts}=row;
    for(let i=0;i<pts.length-1;i++){
      const a=pts[i],b=pts[i+1],mid=(a+b)/2,ga=groundAt(p,a+1e-7),gb=groundAt(p,b-1e-7),ba=baseAt(p,base,a+1e-7),bb=baseAt(p,base,b-1e-7),changed=r&&mid*state[run]>=r.start&&mid*state[run]<r.end;
      const h=changed?r.height:height,inGate=g&&mid*state[run]>g.offset&&mid*state[run]<g.offset+g.width;
      let ta=ba+h,tb=bb+h;
      if(p.top!=='Follow base'){
        const start=p.top==='Stepped top'&&mid>=p.fenceStep?Number(p.fenceStep):0,end=p.top==='Stepped top'&&mid<p.fenceStep?Number(p.fenceStep):1;
        const values=[...Array.from({length:101},(_,j)=>start+(end-start)*j/100),...pts.filter(t=>t>=start&&t<=end)];
        ta=tb=Math.max(...values.map(t=>baseAt(p,base,t)))+h;
      }
      const x1=X(row,a),x2=X(row,b),y=z=>Y(z+row.origin),poly=(bottomA,bottomB,topA,topB)=>`${x1},${y(bottomA)} ${x2},${y(bottomB)} ${x2},${y(topB)} ${x1},${y(topA)}`;
      art+=`<path data-ground="${run}" d="M${x1} ${y(ga)}L${x2} ${y(gb)}" stroke="#5b6357" stroke-width="3" ${p.ground==='Unmeasured'?'stroke-dasharray="5 4"':''}/>`;
      if(base!=='Soil')art+=`<polygon data-base="${run}" points="${poly(ga,gb,ba,bb)}" fill="#c9d0d5" stroke="#606d78" ${p.condition!=='Existing'?'stroke-dasharray="4 3"':''}/>`;
      if(!inGate)art+=`<polygon data-fence="${run}" points="${poly(ba,bb,ta,tb)}" fill="${changed?'#f1dfb6':'#d8e9df'}" stroke="${changed?'#99712c':'#427456'}"/><polygon points="${poly(ba,bb,ta,tb)}" fill="url(#profile-slats)"/>`;
      if(i<pts.length-2)art+=`<path d="M${x2} ${y(gb)}V${y(groundAt(p,b+1e-7))}" stroke="#5b6357" stroke-width="3"/>`;
    }
    const center=X(row,.5);
    art+=`<text x="${center}" y="18" font-size="13" text-anchor="middle" fill="#345d49">${run==='street'?'A-B':'B-C'} / ${fmt(state[run])} m / ${p.condition}</text><text x="${center}" y="36" font-size="11" text-anchor="middle" fill="#52665b">${p.ground==='Unmeasured'?'Ground unmeasured':fmt(groundAt(p,1))+' m ground rise'} / ${p.groundSource}</text><text x="${center}" y="205" font-size="12" text-anchor="middle" fill="#345d49">Fence: ${r?fmt(height)+' / '+fmt(r.height):fmt(height)} m ${p.top==='Follow base'?'above base':'min. above base'}</text>`;
  }
  if(!rows.length)art+='<text x="360" y="120" font-size="14" text-anchor="middle" fill="#52665b">No stretches recorded</text>';
  $('#side').setAttribute('viewBox','0 0 720 220');$('#side').innerHTML=art;
  $('#profile-caption').textContent=state.step===2&&(profileDirty(state.selected)||detailDirty(state.selected))?'Draft preview / not saved':'Recorded ground, base and fence';
  $('#profile-summary').textContent=rows.map(({run,p,base})=>`${run==='street'?'A-B':'B-C'}: ${base}${base!=='Soil'?' '+fmt(Number(p.baseStart))+' m at start':''}; ${p.top.toLowerCase()}`).join(' | ');
}
function siteReviewItems(){
  const out=[],add=(step,text)=>out.push({step,text}),s=state.site;
  if(siteDirty())add(0,'Site context has unsaved edits.');
  if(s.finished==='Unconfirmed')add(0,'Confirm finished ground levels before installation.');
  if(s.stage!=='Existing site')add(0,`${s.workArea}: ${s.stage.toLowerCase()}. Next: ${s.action||'site action not recorded'}.`);
  for(const run of ['street','side']){const p=state.profiles[run];
    if(profileDirty(run))add(2,`${scopeNames[run]} has an unsaved profile draft.`);
    if(p.condition!=='Existing')add(2,`${scopeNames[run]} base is ${p.condition.toLowerCase()}; verify it after completion.`);
    if(p.ground==='Unmeasured')add(2,`${scopeNames[run]} ground has not been measured.`);
    else if(p.groundSource!=='Measured')add(2,`${scopeNames[run]} ground is ${p.groundSource.toLowerCase()}; not a verified field measurement.`);
  }
  if(s.pool!=='None'&&s.poolRole!=='Nearby only')add(1,`Pool relationship: ${s.poolRole.toLowerCase()}. Office pool-safety review required; no approval recorded.`);
  if(s.pool!=='None'&&!s.poolRefs.length)add(1,'Identify the components affected by the pool.');
  for(const n of state.notes)if(n.status==='Open question')add(5,`${n.target}: ${n.text}`);
  return out;
}
function sitePackage(){
  const s=state.site;
  return `<section class="site-package"><h4>Sold facts / signed sources</h4><p>8 m street fence in soil; 5 m side fence on a planned masonry wall. Slat panel, 1.8 m above base; signed amendment lowers A-B from 3-8 m to 1.4 m. Gate: 1 m wide, 2 m from A.</p>
    <h4>Recorded site / measured versus planned</h4><p>${esc(s.stage)} / ${esc(s.workArea)}. Finished ground levels: ${esc(s.finished.toLowerCase())}.</p>
    <table class="package-facts"><thead><tr><th>Stretch</th><th>Ground</th><th>Supporting base</th><th>Fence top intent</th></tr></thead><tbody>${['street','side'].map(run=>{const p=state.profiles[run],base=state.bases[run];return `<tr><th>${scopeNames[run]}</th><td>${p.ground==='Unmeasured'?'Unmeasured':esc(p.ground)+' / '+fmt(groundAt(p,1))+' m rise'}<br>${esc(p.groundSource)}</td><td>${esc(base)} / ${esc(p.condition)}${base!=='Soil'?'<br>'+esc(p.baseShape)+'<br>Above ground: '+fmt(Number(p.baseStart))+' m start; '+fmt(baseAt(p,base,1)-groundAt(p,1))+' m end':''}</td><td>${esc(p.top)}</td></tr>`;}).join('')}</tbody></table>
    <h4>Pool and construction</h4><p>Pool: ${esc(s.pool)}${s.pool!=='None'?' / '+esc(s.poolRole)+' / '+esc(s.poolRefs.map(k=>scopeNames[k]).join(', ')||'components unconfirmed'):''}. No pool-safety approval is claimed.</p><p>Next site action: ${esc(s.action||'Not recorded')}.</p>
    ${state.notes.length?`<h4>Component notes</h4>${state.notes.map(n=>`<p><strong>${esc(n.target)} / ${esc(n.status)}</strong><br>${esc(n.text)}<br>${esc(n.kind)} / Taylor${n.source?' / '+esc(sourceNames[n.source]):''}</p>`).join('')}`:''}</section>`;
}
