const $ = s => document.querySelector(s);
const icon = name => `<i data-lucide="${name}"></i>`;
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt = n => Number(n).toLocaleString('en', {maximumFractionDigits:2});
const steps = [
  {name:'Job & sources',icon:'files',title:'Start with the signed job and site status.',copy:'This yard is under construction. Original sources and outstanding site checks stay together.',take:'The right address and original agreement are always within reach.'},
  {name:'Draw the layout',icon:'pencil-ruler',title:'Place the fence in its site context.',copy:'8 m along the street, 5 m toward the house. A planned pool and works area stay visible.',take:'Written measurements define the fence. The rough sketch only shows the arrangement.'},
  {name:'Set the details',icon:'sliders-horizontal',title:'Ground, supporting base, then fence.',copy:'Keep the measured ground separate from the planned wall and the fence above it.',take:'Fence height is above its base. Planned levels are not measured site conditions.'},
  {name:'Edit a section',icon:'split',title:'Change only the part you mean.',copy:'This example amendment lowers the final 5 m. The first 3 m stays at 1.8 m.',take:'The highlighted section changes. The rest of the fence stays untouched.'},
  {name:'Place the gate',icon:'door-open',title:'Place the gate with numbers, not guesswork.',copy:'A 1 m opening, starting exactly 2 m from corner A. See the position before saving.',take:'Gate width and distance use the same named reference as the signed sketch.'},
  {name:'Review',icon:'clipboard-check',title:'Check the layout, then prepare the office package.',copy:'Review the recorded facts and the original sources. Keep the unanswered hinge question visible.',take:'The office gets the layout, sources and open question together. This demo sends nothing.'}
];
const initial = () => ({step:0,source:'sketch',selected:'street',drawn:0,street:8,side:5,heights:{street:1.8,side:1.8},models:{street:'Slat panel',side:'Slat panel'},bases:{street:'Soil',side:'Soil'},range:{start:3,end:8,height:1.4},rangeApplied:null,rangeTouched:false,gate:{offset:2,width:1,swing:'Inward'},gateSaved:null,gateTouched:false,zoom:1,sideFocus:false});
let state = initial();
function initializeDrafts() {
  initializeSite();
  state.drawTouched=false;
  state.drawDraft={street:String(state.street),side:String(state.side)};
  state.detailsDraft=Object.fromEntries(['street','side'].map(run=>[run,{height:String(state.heights[run]),model:state.models[run],base:state.bases[run]}]));
  state.rangeActive=true;
}
initializeDrafts();
const sourceNames={contract:'Signed contract',sketch:'Site sketch',amendment:'Signed amendment',message:'WhatsApp message',photo:'Site photo',construction:'Construction drawing'};
const same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
function detailDirty(run) {
  const d=state.detailsDraft[run];
  return d.height===''||Number(d.height)!==state.heights[run]||d.model!==state.models[run]||d.base!==state.bases[run];
}
function lengthDirty(run) {return state.drawDraft[run]===''||Number(state.drawDraft[run])!==state[run];}
function pendingCount() {
  return Number(siteDirty())+['street','side'].filter(profileDirty).length+['street','side'].filter(lengthDirty).length+['street','side'].filter(detailDirty).length+
    Number(state.rangeTouched&&state.rangeActive&&!same(state.range,state.rangeApplied))+
    Number(state.gateTouched&&!same(state.gate,state.gateSaved));
}
function focusKey() {
  const el=document.activeElement;
  if(!el||el===document.body)return null;
  if(el.id)return '#'+el.id;
  for(const key of ['data-step','data-select','data-run','data-gate','data-detail-tab','data-layout-tab','data-landmark'])if(el.hasAttribute(key))return '['+key+'="'+el.getAttribute(key)+'"]';
  return el.hasAttribute('data-go')?'#inspector h3':null;
}
function restoreFocus(key) {
  const el=key&&$(key);
  if(el&&!el.disabled){if(el.tagName==='H3')el.tabIndex=-1;el.focus({preventScroll:true});}
}
function invalidateGeometry() {
  if(state.rangeApplied&&!rangeValid(state.rangeApplied)){state.rangeApplied=null;state.rangeTouched=true;}
  if(state.gateSaved&&!gateValid(state.gateSaved)){state.gateSaved=null;state.gateTouched=true;}
}
const sourceHTML = (source=state.source) => {
  if(source==='construction')return `<div class="paper"><div class="paper-kicker">Fictional drawing / rev 3</div><h4>Side B-C / planned works</h4><p>Ground rises <strong>0.3 m</strong> from B to C.<br>Masonry wall: <strong>0.6 m above ground</strong>, following the slope.</p><p>Pool planned near B-C. Outline is indicative only.</p><div class="stamp">Not a field measurement.<br>Finished levels unconfirmed.<br>Remeasure after wall completion.</div></div>`;
  if(source==='contract') return `<div class="paper"><div class="paper-kicker">Fictional signed record</div><h4>Fence supply agreement</h4><p><strong>Sam Example</strong><br>18 Garden Lane</p><p>Street A-B: 8 m<br>Side B-C: 5 m</p><p>Slat panel / 1.8 m above base<br>A-B: soil. B-C: planned masonry wall.<br>Gate: 1 m wide, starting 2 m from A.</p><div class="stamp">Signed in this example / 06 Sep 2026<br>Layout: attached site sketch.<br>Later height change: signed amendment.</div></div>`;
  if(source==='photo') return `<div class="paper"><div class="paper-kicker">Illustrative site photo</div><h4>Street gate location</h4><img class="site-photo" src="sales-journey/example-site.png" alt="Generated example: soil boundary and a pedestrian path toward a white house"><p>Linked to gate on A-B.<br>Soil and path edge at the proposed opening.</p><div class="stamp">AI-generated example, not site evidence. No dimensions inferred from this image.</div></div>`;
  if(source==='amendment') return `<div class="paper"><div class="paper-kicker">Example document / 02</div><h4>Signed amendment</h4><p>Street fence A-B</p><span class="source-measure">3 m &rarr; 8 m</span><p>Lower this section to <strong>1.4 m</strong>.</p><p>The first 3 m stays at 1.8 m. Side fence and gate unchanged.</p><div class="stamp">Confirmed in this example</div></div>`;
  if(source==='message') return `<div class="paper"><div class="paper-kicker">Copied message / example</div><h4>Customer question</h4><p>"The gate opens into the garden. Which side will the hinges be on?"</p><p class="request">Hinge side not confirmed.</p><div class="stamp">Linked to the street gate.<br>Source: WhatsApp. No live connection.</div></div>`;
  return `<div class="paper"><div class="paper-kicker">Example document / 01</div><h4>Signed site sketch</h4><svg viewBox="0 0 210 177" role="img" aria-label="Original sketch: eight metre street fence, five metre side fence and a gate two metres from A"><path d="M22 120 L168 119 170 22" fill="none" stroke="#4b6253" stroke-width="3"/><path d="M59 120 L78 119" stroke="#b17f36" stroke-width="5"/><rect x="53" y="42" width="79" height="44" fill="#edf1ed" stroke="#a2afa4"/><text x="75" y="68" fill="#768479" font-size="12">House</text><text x="91" y="110" fill="#46604d" font-size="15">8 m</text><text x="177" y="73" fill="#46604d" font-size="14">5 m</text><text x="13" y="139" font-size="12">A</text><text x="168" y="139" font-size="12">B</text><text x="173" y="18" font-size="12">C</text><path d="M20 151 H187" stroke="#acb7bc" stroke-width="2"/><text x="85" y="168" font-size="11" fill="#7c8a8e">Street</text></svg><p>Slat panel / 1.8 m above base<br>A-B: soil / B-C: planned wall<br>Gate: 1 m wide, 2 m from A</p><div class="stamp">Signed sale / 06 Sep 2026</div></div>`;
};
function sources(){
  $('#source-view').innerHTML=sourceHTML();
  document.querySelectorAll('[data-source]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.source===state.source)));
  evidenceSources();
}
function saveLabel(text='Saved example values') {
  const count=pendingCount();
  $('#save-state').innerHTML=icon(count?'pencil':'check')+esc(count?count+' unsaved '+(count===1?'edit':'edits'):text);
  $('#save-state').classList.toggle('pending',count>0);
  lucide.createIcons();
}
function go(index){
  state.step=Math.max(0,Math.min(5,index));
  // Each chapter can be opened directly as a prepared example. User edits are retained.
  if(state.step>=2&&!state.drawTouched)state.drawn=2;
  if(state.step>=4&&!state.rangeTouched)state.rangeApplied=rangeValid(state.range)?{...state.range}:null;
  if(state.step>=5&&!state.gateTouched)state.gateSaved=gateValid(state.gate)?{...state.gate}:null;
  state.source=state.step===3?'amendment':state.step===4?'message':state.step===2&&state.selected==='side'?'construction':'sketch';
  state.sideFocus=state.step===3;
  render();
}
function render(){
  const focused=focusKey();
  const s=steps[state.step];
  if(!$('#steps').children.length)$('#steps').innerHTML=steps.map((v,i)=>`<button data-step="${i}" ${i===state.step?'aria-current="step"':''}>${icon(v.icon)}<span>${v.name}</span><span class="step-index">${String(i+1).padStart(2,'0')}</span></button>`).join('');
  $('#steps').querySelectorAll('[data-step]').forEach(b=>{if(+b.dataset.step===state.step)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
  $('#story-number').textContent=String(state.step+1).padStart(2,'0');$('#story-title').textContent=s.title;$('#story-copy').textContent=s.copy;$('#takeaway').textContent=s.take;
  $('#previous').disabled=state.step===0;$('#next').innerHTML=state.step===5?'Restart '+icon('rotate-ccw'):'Next: '+steps[state.step+1].name+' '+icon('arrow-right');
  $('#sources').classList.toggle('active-source',state.step===0);$('#inspector').classList.toggle('step-accent',state.step>0);
  $('#screen-status').textContent=state.step===0?'Sam Example / 18 Garden Lane':`${state.drawn} stretches / ${fmt(state.street+state.side)} m total / ${state.step===3?'Selected range on street fence':'Recorded layout / see source status'}`;
  sources();inspector();draw();saveLabel();restoreFocus(focused);
}
function rangeValid(r){return Number.isFinite(r.start)&&Number.isFinite(r.end)&&Number.isFinite(r.height)&&r.start>=0&&r.end<=state.street&&r.start<r.end&&r.height>=0.2&&r.height<=3;}
function gateValid(g){return Number.isFinite(g.offset)&&Number.isFinite(g.width)&&g.offset>=0&&g.width>=0.5&&g.width<=3&&g.offset+g.width<=state.street;}
function shownRange(){return state.step===3&&state.rangeActive&&rangeValid(state.range)?state.range:state.rangeApplied;}
function shownGate(){return state.step===4&&gateValid(state.gate)?state.gate:state.gateSaved;}
function draw(){
  const focused=$('#plan').contains(document.activeElement)?focusKey():null;
  const A=100,B=A+state.street*48,Y=305,C=Y-state.side*48,r=shownRange(),g=shownGate();
  const line=(key,x1,y1,x2,y2,recorded)=>`<g class="fence-hit" data-run="${key}" role="button" tabindex="0" aria-label="Select ${key} stretch"><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="transparent" stroke-width="28"/><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="${recorded?'#27684d':'#b8c5bb'}" stroke-width="${recorded?6:3}" ${recorded?'':'stroke-dasharray="8 7"'}/>${state.step>=2&&state.selected===key?`<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#72ad8c" opacity=".2" stroke-width="18"/>`:''}</g>`;
  const houseX=state.street<4?B+95:A+25,houseWidth=state.street<4?150:Math.min(180,B-houseX-30);
  let art=`<defs><pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse"><path d="M48 0H0V48" fill="none" stroke="#e9efea" stroke-width="1"/></pattern></defs><rect width="720" height="400" fill="url(#grid)"/><g><path d="M55 358 H660" stroke="#c8d4db" stroke-width="15"/><path d="M55 358 H660" stroke="white" stroke-width="1.5" stroke-dasharray="10 10"/><text x="352" y="384" text-anchor="middle" font-size="13" fill="#52665b">STREET</text><rect id="house-reference" x="${houseX}" y="112" width="${houseWidth}" height="110" fill="#e8eeea" stroke="#bfcec4" stroke-width="1.5"/><text x="${houseX+houseWidth/2}" y="163" text-anchor="middle" font-size="15" fill="#506758">House</text><text x="${houseX+houseWidth/2}" y="184" text-anchor="middle" font-size="11" fill="#52665b">Reference only</text>`;
  art+=line('street',A,Y,B,Y,state.drawn>=1)+line('side',B,Y,B,C,state.drawn>=2);
  if(r&&state.drawn>=1&&state.step>=3)art+=`<g data-run="street" class="range-overlay fence-hit"><line x1="${A+r.start*48}" y1="${Y}" x2="${A+r.end*48}" y2="${Y}" stroke="#c38b3a" stroke-width="7"/><text x="${A+(r.start+r.end)*24}" y="${Y-24}" text-anchor="middle" font-size="13" fill="#98702e">${fmt(r.height)} m high</text></g>`;
  if(g&&state.step>=4){const start=A+g.offset*48,end=start+g.width*48,mid=(start+end)/2,direction=g.swing==='Inward'?-1:1,tip=Y+direction*27;art+=`<g data-gate="true" class="fence-hit" role="button" tabindex="0" aria-label="Edit street gate"><line x1="${start}" y1="${Y}" x2="${end}" y2="${Y}" stroke="#fbfdfb" stroke-width="12"/><path d="M${start} ${Y-7}v14M${end} ${Y-7}v14" stroke="#ba862e" stroke-width="4"/><path data-swing="${g.swing}" d="M${mid} ${Y-direction*7}V${tip}m-6 ${-direction*7} 6 ${direction*7} 6 ${-direction*7}" stroke="#ba862e" stroke-width="2.5" fill="none"/><text x="${mid}" y="${Y-48}" font-size="13" fill="#9a6b21" text-anchor="middle">${fmt(g.width)} m gate</text><path d="M${A} ${Y+18}v7m0-3H${start}m0-4v8" stroke="#ae893c" fill="none"/><text x="${(A+start)/2}" y="${Y+41}" font-size="12" fill="#96702a" text-anchor="middle">${fmt(g.offset)} m from A</text></g>`;}
  art+=`<text x="${(A+B)/2}" y="${Y+22}" text-anchor="middle" font-size="16" font-weight="650" fill="#2d6247">${fmt(state.street)} m</text><text x="${B+24}" y="${(Y+C)/2}" font-size="16" font-weight="650" fill="#2d6247">${fmt(state.side)} m</text>`;
  for(const [x,y,label] of [[A,Y,'A'],[B,Y,'B'],[B,C,'C']])art+=`<circle cx="${x}" cy="${y}" r="7" fill="white" stroke="#366e50" stroke-width="2"/><text x="${x-20}" y="${y-12}" font-size="14" font-weight="700" fill="#355d46">${label}</text>`;
  art+='</g>';$('#plan').innerHTML=art;
  $('#plan').style.width=(state.zoom*100)+'%';
  $('#plan').style.height=(330*state.zoom)+'px';
  sitePlan();profileElevation();$('#zoom-label').textContent=Math.round(state.zoom*100)+'%';$('#zoom-out').disabled=state.zoom<=0.8;$('#zoom-in').disabled=state.zoom>=1.4;$('#elevation').classList.toggle('focus',state.sideFocus);$('#side-focus').setAttribute('aria-pressed',String(state.sideFocus));$('#plan-focus').setAttribute('aria-pressed',String(!state.sideFocus));restoreFocus(focused);
}
const input=(label,id,value,extra='')=>`<label>${label}<input id="${id}" value="${esc(value)}" ${extra}></label>`;
const fact=(a,b)=>`<div><dt>${a}</dt><dd>${b}</dd></div>`;
const choose=(label,id,value,options)=>`<label>${label}<select id="${id}">${options.map(v=>`<option ${v===value?'selected':''}>${v}</option>`).join('')}</select></label>`;
function inspector(){
  let html='';
  if(state.step===0)html=`<div class="eyebrow">This customer</div><h3>Sam's signed job</h3>${input('Customer','customer','Sam Example','readonly')}${input('Site address','address','18 Garden Lane','readonly')}<dl class="facts-list">${fact('Sold by','Taylor')}${fact('Sale date','06 Sep 2026')}${fact('Sources','6 example records')}</dl>${siteFields('job')}<button class="primary" data-go="1">Start the layout ${icon('arrow-right')}</button>`;
  if(state.step===1){
    const done=state.drawn===2,run=done?state.selected:state.drawn===0?'street':'side',first=run==='street';
    html=`<div class="eyebrow">${done?'Recorded layout':first?'First stretch / A-B':'Next stretch / B-C'}</div><h3>${first?'Along the street':'Toward the house'}</h3>
      ${done?'<div class="run-select"><button data-select="street" aria-pressed="'+first+'">Street A-B</button><button data-select="side" aria-pressed="'+!first+'">Side B-C</button></div>':''}
      ${input('Measured length (m)','draw-length',state.drawDraft[run],`type="number" min="1" max="${first?10:5.5}" step="0.1" data-length-run="${run}"`)}
      <dl class="facts-list">${fact('Start',first?'Corner A':'Corner B')}${fact('Direction',first?'Along street':'90 degree left turn')}</dl>
      <p class="draft-status" id="draft-status">${lengthDirty(run)?'Draft / not recorded':done?'Recorded in this example':'Awaiting placement'}</p>
      <p class="error" id="form-error" role="status"></p>
      <button class="primary" id="place">${icon(done?'check':'plus')} ${done?'Save length':first?'Place street stretch':'Place side stretch'}</button>
      <button class="secondary" data-go="2">See the fence details ${icon('arrow-right')}</button>`;
  }
  if(state.step===1){
    const tabs=`<div class="detail-tabs" role="group" aria-label="Layout content"><button data-layout-tab="Fence" aria-pressed="${state.layoutTab==='Fence'}">${icon('fence')}Fence</button><button data-layout-tab="Site" aria-pressed="${state.layoutTab==='Site'}">${icon('map')}Pool & site</button></div>`;
    html=state.layoutTab==='Site'?'<div class="eyebrow">Site context</div><h3>Pool & surroundings</h3>'+tabs+siteFields('pool'):tabs+html;
  }
  if(state.step===2){
    const run=state.selected;
    html=`<div class="eyebrow">Selected stretch / layers</div><h3>${run==='street'?'Street fence A-B':'Side fence B-C'}</h3><div class="run-select"><button data-select="street" aria-pressed="${run==='street'}">Street A-B</button><button data-select="side" aria-pressed="${run==='side'}">Side B-C</button></div>
      ${detailTabs()}${profileFields()}<p class="error" id="form-error" role="status"></p><p class="draft-status" id="draft-status">${detailDirty(run)||profileDirty(run)?'Draft / not saved':'Saved values'}</p>
      <button class="primary" id="save-details">${icon('check')} Save stretch</button><p class="info-note">Source: ${run==='side'?'contract + planned drawing rev 3':'signed site sketch'}</p>`;
  }
  if(state.step===3)html=`<div class="eyebrow">Selected range / street A-B</div><h3>Lower the last section</h3><div class="field-row">${input('From A (m)','range-start',state.range.start,'type="number" min="0" max="10" step="0.1"')}${input('To A (m)','range-end',state.range.end,'type="number" min="0" max="10" step="0.1"')}</div>${input('New height (m)','range-height',state.range.height,'type="number" min="0.2" max="3" step="0.1"')}<div id="range-summary" class="change-summary"></div><p class="error" id="form-error" role="status"></p><button class="primary" id="apply-range">${icon('check')} Apply this change</button><button class="secondary" id="undo-range">${icon('undo-2')} Restore full height</button><p class="info-note">Source: signed amendment<br>Gate and side fence stay unchanged.</p>`;
  if(state.step===4)html=`<div class="eyebrow">Street gate / A-B</div><h3>A measured opening</h3>${input('Distance from A to opening (m)','gate-offset',state.gate.offset,'type="number" min="0" max="10" step="0.1"')}${input('Opening width (m)','gate-width',state.gate.width,'type="number" min="0.5" max="3" step="0.1"')}${choose('Opens toward','gate-swing',state.gate.swing,['Inward','Outward'])}<div id="gate-summary" class="change-summary"></div><p class="error" id="form-error" role="status"></p><button class="primary" id="save-gate">${icon('check')} Save gate</button><p class="info-note">Hinge side: not yet confirmed.</p>`;
  if(state.step===5){
    const issues=reviewItems(),has=step=>issues.some(x=>x.step===step);
    html=`<div class="eyebrow">Review the recorded sale</div><h3>Ready for a human check</h3>
      <div class="review-top">${icon('clipboard-check')}<div><strong>${issues.length} open ${issues.length===1?'question':'items'}</strong><span>No engineering approval implied</span></div></div>
      ${reviewRow('Site readiness',state.site.stage+' / levels '+state.site.finished.toLowerCase(),0,has(0))}
      ${reviewRow('Measured layout',state.drawn===2?fmt(state.street)+' m + '+fmt(state.side)+' m':state.drawn+' of 2 stretches recorded',1,has(1))}
      ${reviewRow('Fence details','Saved models, bases and heights',2,has(2))}
      ${reviewRow('Height amendment',state.rangeApplied?'Selected range recorded':'Not applied yet',3,has(3))}
      ${reviewRow('Gate position',state.gateSaved?fmt(state.gateSaved.width)+' m wide / '+fmt(state.gateSaved.offset)+' m from A':'Not saved yet',4,has(4))}
      <button class="review-row warn" id="review-question">${icon('message-square-warning')}<span class="review-text">Hinge side<small>Customer question still open</small></span>${icon('chevron-right')}</button>
      <button class="primary" id="preview-package">Preview office package ${icon('arrow-right')}</button>`;
  }
  $('#inspector').innerHTML=html;bindInspector();bindSite();updateRangeSummary();updateGateSummary();
}
function reviewRow(title,sub,step,warn=false){return `<button class="review-row ${warn?'warn':''}" data-go="${step}">${icon(warn?'circle-alert':'check-circle-2')}<span class="review-text">${esc(title)}<small>${esc(sub)}</small></span>${icon('chevron-right')}</button>`;}
function updateRangeSummary(){if(!$('#range-summary'))return;const r=state.range,valid=rangeValid(r);$('#range-summary').textContent=!state.rangeActive?'Full stretch: '+fmt(state.heights.street)+' m. No partial change.':valid?`${fmt(r.end-r.start)} m changes to ${fmt(r.height)} m high. ${fmt(state.street-(r.end-r.start))} m stays unchanged.`:'Select a range inside the street fence.';$('#apply-range').disabled=!valid;$('#form-error').textContent=valid?'':'Start must be before end, within the street length. Height: 0.2-3 m.';}
function updateGateSummary(){if(!$('#gate-summary'))return;const g=state.gate,valid=gateValid(g);$('#gate-summary').textContent=valid?`Opening: ${fmt(g.offset)} m to ${fmt(g.offset+g.width)} m from A.`:'The gate must fit entirely within this stretch.';$('#save-gate').disabled=!valid;$('#form-error').textContent=valid?'':'Use a positive width of 0.5-3 m and an offset that fits the street fence.';}
function number(id){const el=$('#'+id);return el.value===''?NaN:Number(el.value);}
function bindInspector(){
  $('#inspector').querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>go(+b.dataset.go));
  $('#inspector').querySelectorAll('[data-select]').forEach(b=>b.onclick=()=>{state.selected=b.dataset.select;render();});
  if($('#draw-length'))$('#draw-length').oninput=()=>{
    state.drawTouched=true;const el=$('#draw-length');state.drawDraft[el.dataset.lengthRun]=el.value;
    $('#draft-status').textContent='Draft / not recorded';saveLabel();
  };
  if($('#place'))$('#place').onclick=()=>{
    const el=$('#draw-length'),run=el.dataset.lengthRun;
    if(!el.checkValidity()||!el.value){$('#form-error').textContent='Enter a valid measured length.';return;}
    state.drawTouched=true;state[run]=Number(el.value);state.drawDraft[run]=el.value;
    if(state.drawn<2)state.drawn++;invalidateGeometry();render();
    saveLabel('Length recorded in demo');
    if(state.drawn===1)$('#draw-length').focus();
  };
  for(const id of ['height','model','base'])if($('#'+id))$('#'+id).oninput=()=>{
    const d=state.detailsDraft[state.selected];d[id]=$('#'+id).value;
    $('#draft-status').textContent=detailDirty(state.selected)?'Draft / not saved':'Saved values';saveLabel();if(id==='base')render();else draw();
  };
  if($('#save-details'))$('#save-details').onclick=()=>{
    const run=state.selected,d=state.detailsDraft[run],p=state.profileDraft[run],height=Number(d.height),error=profileError(p,d.base);
    if(d.height===''||!Number.isFinite(height)||height<0.2||height>3){$('#form-error').textContent='Enter a height from 0.2 to 3 m.';return;}
    if(error){$('#form-error').textContent=error;return;}
    state.heights[run]=height;state.models[run]=d.model;state.bases[run]=d.base;state.profiles[run]=structuredClone(p);
    $('#form-error').textContent='';$('#draft-status').textContent='Saved values';
    if(!state.rangeActive&&!state.rangeApplied)state.range.height=state.heights.street;
    saveLabel('Stretch saved in demo');draw();
  };
  for(const k of ['start','end','height'])if($('#range-'+k))$('#range-'+k).oninput=()=>{state.rangeTouched=true;state.rangeActive=true;state.range[k]=number('range-'+k);updateRangeSummary();draw();saveLabel('Range preview / not applied');};
  if($('#apply-range'))$('#apply-range').onclick=()=>{state.rangeTouched=true;state.rangeActive=true;state.rangeApplied={...state.range};saveLabel('Range applied in demo');$('#range-summary').innerHTML=`<strong>Change applied</strong>${fmt(state.range.start)}-${fmt(state.range.end)} m is now ${fmt(state.range.height)} m high.`;draw();};
  if($('#undo-range'))$('#undo-range').onclick=()=>{state.rangeTouched=true;state.rangeActive=false;state.rangeApplied=null;state.range={start:Math.min(3,state.street/2),end:state.street,height:state.heights.street};render();saveLabel('Full height restored in demo');};
  for(const k of ['offset','width'])if($('#gate-'+k))$('#gate-'+k).oninput=()=>{state.gateTouched=true;state.gate[k]=number('gate-'+k);updateGateSummary();draw();saveLabel('Gate preview / not saved');};
  if($('#gate-swing'))$('#gate-swing').onchange=()=>{state.gateTouched=true;state.gate.swing=$('#gate-swing').value;draw();saveLabel('Gate preview / not saved');};
  if($('#save-gate'))$('#save-gate').onclick=()=>{state.gateTouched=true;state.gateSaved={...state.gate};saveLabel('Gate saved in demo');$('#gate-summary').innerHTML=`<strong>Gate saved</strong>${fmt(state.gate.width)} m wide, ${fmt(state.gate.offset)} m from A.`;};
  if($('#review-question'))$('#review-question').onclick=()=>openSource('message');
  if($('#preview-package'))$('#preview-package').onclick=showPackage;
}
function reviewItems(){
  const out=[{step:4,text:'Confirm which side the gate hinges are on.'}];
  const add=(step,text)=>out.push({step,text});
  if(state.drawn<2)add(1,'The layout is incomplete: '+state.drawn+' of 2 stretches recorded.');
  if(['street','side'].some(lengthDirty))add(1,'A measured length draft has not been recorded.');
  if(state.street!==8||state.side!==5)add(1,'Layout lengths differ from the signed sketch.');
  if(['street','side'].some(detailDirty))add(2,'Stretch detail drafts have not been saved.');
  if(!state.rangeApplied)add(3,'The signed height amendment has not been applied.');
  else if(state.rangeApplied.start!==3||state.rangeApplied.end!==8||state.rangeApplied.height!==1.4)add(3,'Recorded height range differs from the signed amendment.');
  if(state.heights.street!==1.8||state.heights.side!==1.8||Object.values(state.models).some(x=>x!=='Slat panel')||state.bases.street!=='Soil'||state.bases.side!=='Masonry wall')add(2,'Stretch details differ from the original signed specification.');
  if(!state.gateSaved)add(4,'The gate is not saved.');
  else if(state.gateSaved.offset!==2||state.gateSaved.width!==1||state.gateSaved.swing!=='Inward')add(4,'Gate dimensions or swing differ from the original sources.');
  if(state.rangeTouched&&state.rangeActive&&!same(state.range,state.rangeApplied))add(3,'A range preview has not been applied.');
  if(state.gateTouched&&!same(state.gate,state.gateSaved))add(4,'A gate preview has not been saved.');
  return out.concat(siteReviewItems());
}
function reviewIssues(){return reviewItems().map(x=>x.text);}
function openSource(source=state.source){
  $('#source-title').textContent=sourceNames[source]+' / example';
  $('#source-expanded').innerHTML=sourceHTML(source);
  $('#source-dialog').showModal();
}
function savedHeights(run){
  const r=state.rangeApplied,normal=fmt(state.heights[run])+' m';
  if(run==='side'||!r)return normal+' throughout';
  const parts=[];
  if(r.start>0)parts.push('0-'+fmt(r.start)+' m: '+normal);
  parts.push(fmt(r.start)+'-'+fmt(r.end)+' m: '+fmt(r.height)+' m');
  if(r.end<state.street)parts.push(fmt(r.end)+'-'+fmt(state.street)+' m: '+normal);
  return parts.join('; ');
}
function diagramSnapshot(id){
  const clone=$('#'+id).cloneNode(true);
  clone.removeAttribute('id');clone.removeAttribute('style');
  clone.querySelectorAll('*').forEach(el=>{
    for(const attr of [...el.attributes])if(attr.name.startsWith('data-'))el.removeAttribute(attr.name);
    el.classList.remove('fence-hit','range-overlay');
  });
  clone.querySelectorAll('[tabindex], [role="button"], [data-run], [data-gate]').forEach(el=>{
    for(const attr of ['tabindex','role','data-run','data-gate'])el.removeAttribute(attr);
  });
  clone.querySelectorAll('[id]').forEach(el=>{
    const before=el.id,after='package-'+before;el.id=after;
    clone.querySelectorAll('*').forEach(node=>{
      for(const attr of ['fill','stroke'])if(node.getAttribute(attr)==='url(#'+before+')')node.setAttribute(attr,'url(#'+after+')');
    });
  });
  return clone.outerHTML;
}
function showPackage(){
  const issues=reviewIssues(),g=state.gateSaved;
  $('#package-content').innerHTML=`
    <div class="package-banner"><strong>Prepared for office review</strong><p>Example only. Nothing has been sent. Saved values below; drafts are excluded.</p></div>
    <h3>Sam Example / 18 Garden Lane</h3>
    <p>Signed sale / 06 Sep 2026 / Taylor</p>
    <div class="package-layout"><figure><figcaption>Recorded plan</figcaption>${diagramSnapshot('plan')}</figure><figure><figcaption>Unfolded elevations / corner B</figcaption>${diagramSnapshot('side')}</figure></div>
    <table class="package-facts"><caption>Saved specification</caption><thead><tr><th scope="col">Stretch</th><th scope="col">Recorded length</th><th scope="col">Model / base</th><th scope="col">Height above base</th></tr></thead><tbody>
      ${['street','side'].map((run,i)=>`<tr><th scope="row">${i?'Side B-C':'Street A-B'}</th><td>${state.drawn>i?fmt(state[run])+' m':'Not recorded'}</td><td>${esc(state.models[run])}<br>${esc(state.bases[run])}</td><td>${esc(savedHeights(run))}</td></tr>`).join('')}
    </tbody></table>
    <h4>Street gate</h4><p>${g?fmt(g.width)+' m opening, '+fmt(g.offset)+'-'+fmt(g.offset+g.width)+' m from A. Opens '+g.swing.toLowerCase()+'.':'No gate saved.'} Hinge side unconfirmed.</p>
    <p>Height change: ${state.rangeApplied?'signed amendment linked to A-B, '+fmt(state.rangeApplied.start)+'-'+fmt(state.rangeApplied.end)+' m.':'signed amendment not applied.'}</p>
    ${sitePackage()}<h4>Original sources / 6 example records</h4><div class="package-sources">${Object.entries(sourceNames).map(([key,name])=>`<button data-package-source="${key}">${icon(key==='photo'?'image':'file-text')}${name}${icon('arrow-up-right')}</button>`).join('')}</div>
    <div class="change-summary warning"><strong>Still needs confirmation / ${issues.length} open ${issues.length===1?'question':'items'}</strong>${issues.map(x=>`<p>${esc(x)}</p>`).join('')}</div>
    <p>No buildability check or office acceptance is claimed.</p>`;
  $('#package-content').querySelectorAll('[data-package-source]').forEach(b=>b.onclick=()=>openSource(b.dataset.packageSource));
  lucide.createIcons();$('#handover-dialog').showModal();
}
$('#steps').onclick=e=>{const b=e.target.closest('[data-step]');if(b)go(+b.dataset.step);};
$('#next').onclick=()=>state.step===5?restart():go(state.step+1);$('#previous').onclick=()=>go(state.step-1);
function restart(){state=initial();initializeDrafts();render();saveLabel('Example loaded');$('#plan-wrap').scrollTo(0,0);}$('#restart').onclick=restart;
document.querySelectorAll('[data-source]').forEach(b=>b.onclick=()=>{state.source=b.dataset.source;sources();});
$('#source-open').onclick=()=>openSource();
$('#add-note').onclick=openNote;
document.querySelectorAll('[data-close]').forEach(b=>b.onclick=()=>b.closest('dialog').close());
$('#zoom-in').onclick=()=>{state.zoom=Math.min(1.4,Math.round((state.zoom+0.1)*10)/10);draw();};$('#zoom-out').onclick=()=>{state.zoom=Math.max(0.8,Math.round((state.zoom-0.1)*10)/10);draw();};$('#zoom-reset').onclick=()=>{state.zoom=1;draw();$('#plan-wrap').scrollTo(0,0);};
$('#side-focus').onclick=()=>{state.sideFocus=true;draw();};$('#plan-focus').onclick=()=>{state.sideFocus=false;draw();};
function selectDrawing(e){const pool=e.target.closest('[data-landmark]'),gate=e.target.closest('[data-gate]'),run=e.target.closest('[data-run]');if(pool){state.layoutTab='Site';go(1);}else if(gate)go(4);else if(run&&state.drawn>0){state.selected=run.dataset.run;go(2);}}
$('#plan').onclick=selectDrawing;$('#plan').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();selectDrawing(e);}};
render();
