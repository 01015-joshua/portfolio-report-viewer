// All returns are fractions; effects are linked to arithmetic cumulative active return.
const obs=ANALYTICS.daily;
const avg=a=>a.reduce((s,x)=>s+x,0)/a.length;
const deviation=a=>a.length<2?null:Math.sqrt(a.reduce((s,x)=>s+(x-avg(a))**2,0)/(a.length-1));
const compound=a=>Math.expm1(a.reduce((s,x)=>s+Math.log1p(x),0));
function riskStats(ds){const p=ds.map(d=>d.p),b=ds.map(d=>d.b),a=ds.map(d=>d.p-d.b),n=ds.length;const sd=deviation(a),ready=n>=20,bm=avg(b),pm=avg(p),bv=b.reduce((v,x)=>v+(x-bm)**2,0),beta=ready&&bv>1e-24?p.reduce((v,x,i)=>v+(x-pm)*(b[i]-bm),0)/bv:null;return {annualActive:ready?avg(a)*252:null,beta,n,p:compound(p),b:compound(b),active:compound(p)-compound(b),te:ready?sd*Math.sqrt(252):null,ir:ready&&sd>1e-12?avg(a)/sd*Math.sqrt(252):null,sp:ready?deviation(p)*Math.sqrt(252):null,sb:ready?deviation(b)*Math.sqrt(252):null}}
function linkK(p,b){return Math.abs(p-b)<1e-10?1/(1+(p+b)/2):(Math.log1p(p)-Math.log1p(b))/(p-b)}
function selfAttribution(ds,level='sector'){
 const P=compound(ds.map(d=>d.p)),B=compound(ds.map(d=>d.b)),K=linkK(P,B),names=ds[0][level].map(x=>x.name);let missing=0,residual=0;
 const rows=names.map(name=>({name,allocation:0,selection:0,interaction:0,wp:0,wb:0,unresolved:0}));
 ds.forEach(d=>{const f=linkK(d.p,d.b)/K;let explained=0;for(const x of d[level]){const o=rows.find(o=>o.name===x.name);if(valid(x.wp))o.wp+=x.wp/ds.length;if(valid(x.wb))o.wb+=x.wb/ds.length;
 // Missing reference returns are left unresolved, never treated as zero returns.
 if(!valid(x.wp)||!valid(x.wb)||!valid(x.rb)||(x.wp!==0&&!valid(x.rp))){if(x.wp!==0||x.wb!==0){missing++;o.unresolved++}continue}
 const rp=valid(x.rp)?x.rp:x.rb,A=(x.wp-x.wb)*(x.rb-d.b),S=x.wb*(rp-x.rb),I=(x.wp-x.wb)*(rp-x.rb);o.allocation+=A*f;o.selection+=S*f;o.interaction+=I*f;explained+=A+S+I}
 residual+=(d.p-d.b-explained)*f});
 rows.forEach(o=>o.total=o.allocation+o.selection+o.interaction);return {P,B,active:P-B,rows,residual,missing,n:ds.length}}
// Explicit approximation: all USD returns are treated as local returns.
function usdProxyAttribution(ds,level='sector'){
 const P=compound(ds.map(d=>d.p)),B=compound(ds.map(d=>d.b)),K=linkK(P,B);let residual=0,missing=0;
 const rows=ds[0].group.map(x=>({name:x.name,allocation:0,selection:0,interaction:0,currency:0,wp:0,wb:0,unresolved:0}));
 for(const d of ds){const f=linkK(d.p,d.b)/K,g=d.fx_factor-1;let explained=0;
 for(const x of d.group){const o=rows.find(r=>r.name===x.name);if(valid(x.wp))o.wp+=x.wp/ds.length;if(valid(x.wb))o.wb+=x.wb/ds.length;
 const rp=x.rp_usd,rb=x.rb_usd;const pOK=valid(x.wp)&&(x.wp===0||valid(rp)),bOK=valid(x.wb)&&(x.wb===0||valid(rb));
 if(pOK&&bOK){const C=((x.wp===0?0:x.wp*(1+rp))-(x.wb===0?0:x.wb*(1+rb)))*g;o.currency+=C*f;explained+=C}
 if(!pOK||!bOK||!valid(rb)){o.unresolved++;missing++;continue}
 const pr=valid(rp)?rp:rb,A=(x.wp-x.wb)*(rb-d.b_usd),S=x.wb*(pr-rb),I=(x.wp-x.wb)*(pr-rb);o.allocation+=A*f;o.selection+=S*f;o.interaction+=I*f;explained+=A+S+I;
 }residual+=(d.p-d.b-explained)*f}
 rows.forEach(r=>r.total=r.allocation+r.selection+r.interaction+r.currency);
 if(level==='group')return {P,B,active:P-B,rows,residual,missing,n:ds.length};
 const sectors=ds[0].sector.map(x=>({name:x.name,allocation:0,selection:0,interaction:0,currency:0,total:0,wp:0,wb:0,unresolved:0}));
 for(const r of rows){const o=sectors.find(s=>s.name===r.name.split(' / ')[0]);if(!o)throw Error('Missing parent sector');for(const k of ['allocation','selection','interaction','currency','total','wp','wb'])o[k]+=r[k];o.unresolved=Math.max(o.unresolved,r.unresolved)}
 return {P,B,active:P-B,rows:sectors,residual,missing,n:ds.length};
}
const useUsdProxy=()=>$('customMethod').value==='usd_proxy';
function selectedAttribution(ds,level='sector'){
 if(useUsdProxy())return usdProxyAttribution(ds,level);
 if($('customMethod').value==='legacy')return selfAttribution(ds,level);
 const a=selfAttribution(ds,'group');if(level==='group')return a;
 const rows=ds[0].sector.map(x=>({name:x.name,allocation:0,selection:0,interaction:0,total:0,wp:0,wb:0,unresolved:0}));
 for(const r of a.rows){const parent=rows.find(x=>x.name===r.name.split(' / ')[0]);if(!parent)throw Error('Missing parent sector');for(const k of ['allocation','selection','interaction','total','wp','wb'])parent[k]+=r[k];parent.unresolved=Math.max(parent.unresolved,r.unresolved)}
 return {...a,rows};
}
function enterExtra(which){$('historyView').hidden=true;$('reportView').hidden=which!=='custom';$('customView').hidden=which!=='custom';$('riskView').hidden=which!=='risk';$('portBody').hidden=true;$('historyMode').className='';$('reportMode').className=which==='custom'?'active':'';$('riskMode').className=which==='risk'?'active':'';$('subtitle').textContent=(which==='risk'?'日次リターン USD・JPYから算出（換算統一） ｜ JPY ｜ ':'JIKA・日次リターン USD・JPYから算出（換算統一） ｜ JPY ｜ ')+ANALYTICS.start+' → '+ANALYTICS.end;if(which==='custom'){drawCustomTabs();calculateCustom()}else drawRisk()}
function drawCustomTabs(){ $('periods').innerHTML=REPORTS.map((r,i)=>`<button data-period="${i}">${esc(periodLabel(r))}</button>`).join('')+'<button class="active" onclick="enterExtra(\'custom\')">指定日から（自算）</button>'}
let customState=null,customSector=0;
function customMatrix(rows,ds,level,clickable=false){
 const keys=['allocation','selectionCombined','localTotal','currency','other','total'];rows=rows.map(r=>({...r,selectionCombined:r.selection+r.interaction,localTotal:r.allocation+r.selection+r.interaction,currency:valid(r.currency)?r.currency:null,other:null}));const scale=Math.max(1,...rows.flatMap(r=>keys.map(k=>Math.abs((r[k]||0)*10000))));
 let h='<table class="matrix custommatrix"><thead><tr><th rowspan="2">'+(level==='sector'?'セクター':'業種グループ')+'</th><th colspan="6">超過収益への寄与（bp）</th><th colspan="3">平均構成比（%）</th><th colspan="3">円ベース収益率（%）</th></tr><tr><th>配分効果</th><th>銘柄選択効果</th><th>配分・選択計</th><th>為替効果</th><th>その他効果</th><th>総合効果</th><th>ポートフォリオ</th><th>ベンチマーク</th><th>差（pt）</th><th>ポートフォリオ</th><th>ベンチマーク</th><th>差（pt）</th></tr></thead><tbody>';
 rows.forEach((r,i)=>{const series=ds.map(d=>d[level].find(x=>x.name===r.name));const ret=k=>series.every(x=>x&&valid(x[k]))?compound(series.map(x=>x[k]))*100:null;const rp=ret('rp'),rb=ret('rb');
 h+=`<tr class="${clickable&&i===customSector?'selected':''}"><th>${clickable?`<button class="rowbutton" onclick="selectCustomSector(${i})">${esc(label(r.name))}</button>`:esc(label(r.name.split(' / ').at(-1)))}${r.unresolved?' <small>未分解あり</small>':''}</th>`+keys.map(k=>r.unresolved===ds.length&&k!=='currency'?'<td>—</td>':bar(valid(r[k])?r[k]*10000:null,scale)).join('')+num(r.wp*100)+num(r.wb*100)+bar((r.wp-r.wb)*100,10)+num(rp)+num(rb)+bar(valid(rp)&&valid(rb)?rp-rb:null,10)+'</tr>'});
 h+='<tr class="sum"><th>分解済み効果 合計</th>'+keys.map(k=>bar((k==='other'||k==='currency'&&!useUsdProxy())?null:rows.reduce((v,r)=>v+r[k],0)*10000,scale)).join('')+'<td colspan="6"></td></tr>';
 return h+'</tbody></table>';
}
function selectCustomSector(i){customSector=i;drawCustomDetail();$('customSectorTable').innerHTML=customMatrix(customState.a.rows,customState.ds,'sector',true)}
function drawCustomDetail(){const {ds,a}=customState;const name=a.rows[customSector].name;const groups=selectedAttribution(ds,'group').rows.filter(r=>r.name.startsWith(name+' / ')||r.name===name);
 $('customGroupTitle').textContent=label(name)+'｜業種グループ別要因分析';$('customGroupTable').innerHTML=customMatrix(groups,ds,'group');
 $('customSectorTabs').innerHTML=a.rows.map((r,i)=>`<button class="${i===customSector?'active':''}" onclick="selectCustomSector(${i})">${esc(label(r.name))}</button>`).join('');
}
function calculateCustom(){const start=$('customStart').value,end=$('customEnd').value;if(start>=end){$('customResult').innerHTML='<p class="empty">終了日は開始日より後を選択してください。</p>';return}const ds=obs.filter(d=>d.start>=start&&d.end<=end);if(!ds.length||ds[0].start!==start||ds.at(-1).end!==end){$('customResult').innerHTML='<p class="empty">対応する日付の組み合わせを選択してください。</p>';return}
 const a=selectedAttribution(ds,'sector');$('subtitle').textContent=useUsdProxy()?'業種グループで計算 → セクターに合算 ｜ FXは全資産USD仮定の概算':($('customMethod').value==='group'?'業種グループで計算 → セクターに合算 ｜ FX未分離':'従来のセクター直接計算 ｜ FX未分離');customState={a,ds};customSector=Math.min(customSector,a.rows.length-1);
 let h=`<div class="cards">${[['ポートフォリオ',a.P*100,'%'],['ベンチマーク',a.B*100,'%'],['超過収益',a.active*10000,'bp']].map(([n,v,u])=>`<div class="card"><label>${n}</label><div class="big ${v>=0?'pos':'neg'}">${fmt(v)}<small>${u}</small></div></div>`).join('')}<div class="card"><label>対象期間</label><div>${start} → ${end}</div><span class="scope">${a.n}収益区間</span></div></div>`;
 const rawB=compound(ds.map(d=>d.b_raw));h+=`<p class="note">基準収益：元のJPY出力 ${fmt(rawB*100)}% → 換算統一後 ${fmt(a.B*100)}%（差 ${fmt((a.B-rawB)*10000)} bp）。組合せる日付区間を一致させ、基準のUSD収益を日次換算しています。</p>`;const saved=(ANALYTICS.comparison_reports||REPORTS).find(r=>r.start===start&&r.end===end);
 if(saved){const dp=(a.P-saved.total.rp/100)*10000,db=(a.B-saved.total.rb/100)*10000;
 h+=`<section class="panel"><div class="sectionhead"><h2>同期間のPORTとの比較</h2><small>収益系列の差を確認</small></div><div class="wrap"><table><thead><tr><th>収益系列</th><th>換算統一後 累積（%）</th><th>PORT 出力（%）</th><th>差（bp）</th></tr></thead><tbody><tr><th>ポートフォリオ</th><td>${(a.P*100).toFixed(5)}</td><td>${saved.total.rp.toFixed(5)}</td><td>${fmt(dp)}</td></tr><tr><th>ベンチマーク</th><td>${(a.B*100).toFixed(5)}</td><td>${saved.total.rb.toFixed(5)}</td><td>${fmt(db)}</td></tr><tr class="sum"><th>超過収益</th><td>${fmt(a.active*10000)} bp</td><td>${fmt(saved.total.rd*100)} bp</td><td>${fmt(dp-db)}</td></tr></tbody></table></div><p class="help">自算とPORTの超過収益差 ${fmt(dp-db)} bp ＝ ポートフォリオ収益差 ${fmt(dp)} bp − ベンチマーク収益差 ${fmt(db)} bp。基準はUSD収益をポートフォリオと同じ日次換算因子で円換算しています。元の基準JPY系列との差額を日々に配賦したものではありません。残る差は表中の系列別に表示しています。</p></section>`}
 const A=a.rows.reduce((v,r)=>v+r.allocation,0),S=a.rows.reduce((v,r)=>v+r.selection+r.interaction,0);
 const compare=[['配分効果',A,saved?.total.allocation],['銘柄選択効果',S,saved?.total.selection],['配分・選択計（小計）',A+S,saved?.total.attribution],['為替効果（自算はUSD仮定）',useUsdProxy()?a.rows.reduce((v,r)=>v+r.currency,0):null,saved?.total.currency],['その他効果',null,saved?['leverage','transaction','pricing'].reduce((v,k)=>v+(saved.total[k]||0),0):null],['未分解・照合差額',a.residual,null],['超過収益',a.active,saved?.total.rd]];
 h+=`<section class="panel"><div class="sectionhead"><h2>収益・要因内訳</h2><small>単位：bp ／ 同期間を横並び比較</small></div><div class="wrap"><table class="summary"><thead><tr><th>項目</th><th>PORT</th><th>自算</th><th>差（自算−PORT）</th></tr></thead><tbody>${compare.map(([n,v,p])=>`<tr class="${n==='超過収益'?'sum':''}"><th>${n}</th>${num(valid(p)?p*100:null)}${n.startsWith('為替')&&valid(v)?'<td>'+ (v*10000).toFixed(4)+'</td>':num(valid(v)?v*10000:null)}${num(valid(p)&&valid(v)?v*10000-p*100:null)}</tr>`).join('')}</tbody></table></div><p class="help">自算の銘柄選択効果は選択＋交互作用。PORTの交互作用処理とは同一と未確認。${useUsdProxy()?'為替は全資産USD仮定の概算。USD以外の現地通貨効果はUSD収益に含まれます。FXは対ベンチマーク効果であり、両者の共通ドル円影響は大部分が相殺されます。':'為替は未分離。'}その他効果は未分離のため「—」。配分・選択計は小計であり再加算しません。総合効果は分解済みの円ベース効果、未分解差額は別掲。PORTの代替値ではありません。</p></section>`;
 h+=`<section class="panel"><div class="sectionhead"><h2>セクター別パフォーマンス要因分析</h2><small>セクター名をクリックして内訳を表示</small></div><div class="wrap" id="customSectorTable">${customMatrix(a.rows,ds,'sector',true)}</div><p class="help">分解済み効果 ${fmt((a.active-a.residual)*10000)} bp ＋ 未分解・照合差額 ${fmt(a.residual*10000)} bp ＝ 超過収益 ${fmt(a.active*10000)} bp。参照値等の不足：${a.missing}分類・日。</p></section><section class="panel"><div class="sectionhead"><h2 id="customGroupTitle"></h2></div><div class="pickers"><div class="tabs" id="customSectorTabs"></div></div><div class="wrap" id="customGroupTable"></div><p class="help">${$('customMethod').value!=='legacy'?'業種グループの各効果をセクターに合算。父行と子行を重複加算しません。':'業種グループは全体基準に対する独立分解で、セクター効果に加算しません。'}個別銘柄データはJIKA・日次リターンに含まれていません。</p></section>`;
 $('customResult').innerHTML=h;drawCustomDetail();
}
let riskSeries=[];
function drawRisk(){const mode=$('riskWindow').value;const windowSize=mode==='fytd'?null:+mode;riskSeries=obs.map((d,i)=>{const ds=obs.slice(windowSize?Math.max(0,i-windowSize+1):0,i+1),s=riskStats(ds);if(windowSize&&ds.length<windowSize)for(const k of ['active','annualActive','ir','te','sp','sb','beta'])s[k]=null;return {...s,date:d.end,start:ds[0].start}});const last=riskSeries.at(-1);$('riskAsOf').max=obs.length-1;$('riskAsOf').value=obs.length-1;drawRiskPoint(obs.length-1);
 const plots=[['Information Ratio','ir',1,''],['年率換算平均超過リターン（IR計算用）','annualActive',100,'%'],['Tracking Error（年率）','te',100,'%'],['Standard Deviation（年率）','sp',100,'%'],['Beta（対ベンチマーク）','beta',1,'']];$('riskCharts').innerHTML=plots.map(([name,key,m,u])=>`<section class="panel"><div class="sectionhead"><h2>${name}</h2><small>${key==='sp'?'青：ポートフォリオ ／ 金：基準':u}</small></div>${riskPlot(key,m,u)}</section>`).join('');
 const ends=riskSeries.filter((d,i)=>i===riskSeries.length-1||d.date.slice(0,7)!==riskSeries[i+1].date.slice(0,7));$('riskMonthly').innerHTML='<table><thead><tr><th>月末／最新日</th><th>観測数</th><th>IR</th><th>年率換算平均超過リターン %</th><th>累積超過リターン（非年率）%</th><th>TE（年率）%</th><th>ポートフォリオ Std Dev %</th><th>基準 Std Dev %</th><th>Beta</th></tr></thead><tbody>'+ends.map(d=>`<tr><th>${d.date}</th>${num(d.n)}${num(d.ir)}${num(valid(d.annualActive)?d.annualActive*100:null)}${num(valid(d.active)?d.active*100:null)}${['te','sp','sb'].map(k=>num(valid(d[k])?d[k]*100:null)).join('')}${num(d.beta)}</tr>`).join('')+'</tbody></table>';
}
function riskPlot(key,m,u){const series=[{key,color:'#176b98'},...(key==='sp'?[{key:'sb',color:'#ad7614'}]:[])],vals=riskSeries.flatMap(d=>series.map(s=>d[s.key]).filter(valid).map(x=>x*m));if(!vals.length)return '<p class="empty">観測数が不足しています。</p>';let low=Math.min(0,...vals),high=Math.max(key==='beta'?1:0,...vals);if(high===low)high=low+1;
 const raw=(high-low)/5,power=10**Math.floor(Math.log10(raw)),unit=raw/power;
 let step=(unit<=1?1:unit<=2?2:unit<=5?5:10)*power;if(u==='%')step=Math.max(1,step);
 const lo=Math.floor(low/step)*step,hi=Math.ceil(high/step)*step;
 const X=i=>60+i/Math.max(1,riskSeries.length-1)*590,Y=v=>180-(v-lo)/(hi-lo)*150;
 const decimals=step>=1?0:Math.max(0,-Math.floor(Math.log10(step)));
 let h='<div class="riskplot"><svg viewBox="0 0 680 230" role="img" aria-label="'+key+'の推移" style="width:100%;display:block">';
 for(let i=0;i<=Math.round((hi-lo)/step);i++){const v=lo+i*step,zero=Math.abs(v)<step*1e-8;h+=`<line class="${zero?'risk-zero':'risk-grid'}" x1="60" x2="650" y1="${Y(v)}" y2="${Y(v)}" stroke="${zero?'#123553':'#cbd8e2'}" stroke-width="${zero?2:1}"/><text class="risk-y-label" x="51" y="${Y(v)+4}" text-anchor="end" font-size="12" font-weight="${zero?700:400}" fill="#193344">${zero?'0':v.toFixed(decimals)}</text>`}
 h+=`<text x="51" y="17" text-anchor="end" font-size="11" fill="#405c70">${u}</text>`;
 riskSeries.forEach((d,i)=>{if(i===0||d.date.slice(0,7)!==riskSeries[i-1].date.slice(0,7)){const x=X(i);h+=`<line x1="${x}" x2="${x}" y1="30" y2="185" stroke="#d5e0e9" stroke-dasharray="2 4"/><text class="risk-month-label" x="${x}" y="207" text-anchor="${i===0?'start':'middle'}" font-size="12" fill="#193344">${d.date.slice(0,7).replace('-','/')}</text>`}});
 if(key==='beta')h+=`<line x1="60" x2="650" y1="${Y(1)}" y2="${Y(1)}" stroke="#ad7614" stroke-dasharray="5 4"/><text x="645" y="${Y(1)-5}" text-anchor="end" font-size="11">β = 1</text>`;for(const s of series){let path='';let started=false;riskSeries.forEach((d,i)=>{const v=d[s.key];if(!valid(v)){started=false;return}path+=(started?'L':'M')+X(i)+','+Y(v*m);started=true});h+=`<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.5"/>`;riskSeries.forEach((d,i)=>{if(valid(d[s.key]))h+=`<circle cx="${X(i)}" cy="${Y(d[s.key]*m)}" r="3" fill="${s.color}" tabindex="0"><title>${d.date}：${fmt(d[s.key]*m)}${u}</title></circle>`})}h+=riskSeries.map((d,i)=>`<rect class="riskhit" x="${X(i)-Math.max(2,590/(riskSeries.length-1)/2)}" y="20" width="${Math.max(4,590/(riskSeries.length-1))}" height="165" fill="transparent" tabindex="0" aria-label="${d.date}" onpointerenter="riskHover(this,${i},'${key}',${m},'${u}')" onfocus="riskHover(this,${i},'${key}',${m},'${u}')" onclick="riskHover(this,${i},'${key}',${m},'${u}')"/>`).join(''); return h+`<g class="riskfocus" pointer-events="none"></g></svg><div class="risktooltip" role="status">グラフにカーソルを合わせると日付と値を表示</div></div>`}
function riskHover(target,i,key,m,u){const box=target.closest('.riskplot'),svg=box.querySelector('svg'),d=riskSeries[i];const keys=key==='sp'?['sp','sb']:[key];const names={ir:'Information Ratio',annualActive:'年率換算平均超過リターン（IR計算用）',active:'累積超過リターン（非年率）',te:'Tracking Error',sp:'ポートフォリオ',sb:'ベンチマーク',beta:'Beta'};
 box.querySelector('.risktooltip').textContent=d.date+' ｜ '+keys.map(k=>names[k]+' '+fmt(valid(d[k])?d[k]*m:null)+u).join(' ／ ');
 const x=60+i/(riskSeries.length-1)*590;const pts=[...svg.querySelectorAll('circle')].filter(c=>!c.closest('.riskfocus')&&Math.abs(+c.getAttribute('cx')-x)<.01);
 svg.querySelector('.riskfocus').innerHTML=`<line x1="${x}" x2="${x}" y1="20" y2="185" stroke="#123553" stroke-dasharray="4 3"/>`+pts.map(c=>`<circle cx="${x}" cy="${c.getAttribute('cy')}" r="6" fill="${c.getAttribute('fill')}" stroke="white" stroke-width="2"/>`).join('');
 $('riskAsOf').value=i;drawRiskPoint(i);
}
function drawRiskPoint(i){const d=riskSeries[i];if(!d)return;$('riskDate').textContent=`${d.start} → ${d.date} ／ ${d.n}収益区間`;$('riskCards').innerHTML=[['Information Ratio',d.ir,1,''],['年率換算平均超過リターン（IR計算用）',d.annualActive,100,'%'],['Tracking Error（年率）',d.te,100,'%'],['ポートフォリオ Std Dev',d.sp,100,'%'],['基準 Std Dev',d.sb,100,'%'],['Beta（対ベンチマーク）',d.beta,1,'']].map(([name,v,m,u])=>`<div class="card"><label>${name}</label><div class="big">${fmt(valid(v)?v*m:null)}<small>${u}</small></div></div>`).join('');$('riskReconcile').textContent=valid(d.ir)?`IR = 年率換算平均超過リターン ÷ 年率TE：${(d.annualActive*100).toFixed(4)}% ÷ ${(d.te*100).toFixed(4)}% = ${d.ir.toFixed(4)}（表示値は丸めています）`:'IR：観測数不足またはTEがゼロのため算出できません。';$('riskCumulative').textContent=`期間の実績 ｜ 累積超過リターン（非年率）：${fmt(valid(d.active)?d.active*100:null)}%　※ポートフォリオとベンチマークの累積収益率の差。IRの分子ではありません。`}
function initAnalytics(){$('customMethod').value='group';const starts=obs.map(d=>d.start),ends=obs.map(d=>d.end);$('customStart').innerHTML=starts.map(d=>`<option>${d}</option>`).join('');$('customEnd').innerHTML=ends.map(d=>`<option>${d}</option>`).join('');$('customStart').value=ANALYTICS.start;$('customEnd').value=ANALYTICS.end;$('calcCustom').onclick=calculateCustom;$('customMethod').onchange=calculateCustom;$('riskWindow').onchange=drawRisk;$('riskAsOf').oninput=e=>drawRiskPoint(+e.target.value)}
initAnalytics();enterExtra('custom');
