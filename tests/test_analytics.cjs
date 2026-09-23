// Run with a privately generated report path. Does not embed portfolio fixtures.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(process.argv[2],'utf8');
const data=html.match(/type="application\/json">([\s\S]*?)<\/script>/)[1];
const script=html.split('</script><script>')[1].split('</script>')[0];
const nodes={};
const document={getElementById(id){return nodes[id]??={textContent:id==='reportData'?data:'',value:id==='rankBy'?'selection':id==='riskWindow'?'fytd':'',style:{},scrollIntoView(){},lastElementChild:{querySelector(){return {}}}}},addEventListener(){}};
const ctx=vm.createContext({document,console,assert,location:{protocol:'file:'}});vm.runInContext(script,ctx);
vm.runInContext(`
assert($('returnToImports').hidden);assert($('downloadHtml').hidden);assert(REPORTS.length===6);assert(REPORTS.every(r=>r.kind!=='FYTD'));assert(obs.length>=20);
assert($('customStart').value==='2026-03-31');assert($('customEnd').value===ANALYTICS.end);
assert(!$('customView').hidden);assert(customState.ds.length===obs.length);
draw();assert(!$('periods').innerHTML.includes('通期'));
enterExtra('custom');$('customStart').value=obs[obs.length-20].start;calculateCustom();assert(customState.ds.length===20);
$('customStart').value=ANALYTICS.start;calculateCustom();assert(customState.ds.length===obs.length);
for(const level of ['sector','group'])for(const n of [1,20,obs.length]){const a=selfAttribution(obs.slice(0,n),level);assert(Math.abs(a.rows.reduce((s,r)=>s+r.total,0)+a.residual-a.active)<1e-10)}
const fixture=[{start:'a',end:'b',p:.05,b:.02,sector:[{name:'x',wp:1,wb:1,rp:.05,rb:.02}]}];const a=selfAttribution(fixture);assert(Math.abs(a.rows[0].selection-.03)<1e-12);assert(Math.abs(a.residual)<1e-12);
const z=Array.from({length:20},()=>({p:.001,b:.001}));assert(riskStats(z).ir===null);assert(riskStats(z).te===0);assert(riskStats(obs.slice(0,19)).sp===null);
const bx=Array.from({length:30},(_,i)=>({b:(i-15)/1000,p:2*(i-15)/1000+.001}));assert(Math.abs(riskStats(bx).beta-2)<1e-12);
for(const n of [20,obs.length]){const q=riskStats(obs.slice(0,n));assert(Math.abs(q.annualActive/q.te-q.ir)<1e-12)}
enterExtra('custom');assert($('customResult').innerHTML.includes('照合差額'));drawHistory();assert(!$('historyTable').innerHTML.includes('NaN'));
for(const mode of ['fytd','20','60']){$('riskWindow').value=mode;enterExtra('risk');assert($('riskCharts').innerHTML.includes('<svg'));assert(!$('riskCharts').innerHTML.includes('NaN'));if(mode!=='fytd'&&obs.length>=+mode)assert(riskSeries[+mode-2].active===null)}
console.log('PASS: calculations, reconciliation, risk windows and page rendering');
`,ctx);
