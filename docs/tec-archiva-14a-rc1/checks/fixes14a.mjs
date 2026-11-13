import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const b=path.dirname(fileURLToPath(import.meta.url));
const state=JSON.parse(await fs.readFile(path.join(b,'campaign-full/phase14a-environment.json'),'utf8'));
assert.match(state.project,/^geology-auto11e-a11y14a-full-/);
const creds=JSON.parse(await fs.readFile(path.join(state.control,'ui-private.json'),'utf8'));
const base='http://127.0.0.1:'+state.port;
const browser=await chromium.launch({headless:true});
const out=path.join(b,'results'), tests=[], scans=[];
const axe=await fs.readFile(path.join(b,'tools/axe.min.js'),'utf8');
async function check(id,fn){
 try{tests.push({id,status:'PASS',detail:await fn()});}
 catch(e){tests.push({id,status:'FAIL',error:e.message.slice(0,1500)});}
}
async function login(width,role='administradora'){
 const p=await browser.newPage({viewport:{width,height:900}});
 await p.goto(base+'/app');
 await p.locator('#correo').fill(role+'14a@example.invalid');
 await p.locator('#clave').fill(creds.password);
 await p.locator('#btnIngresar').click();
 await p.locator('#pApp').waitFor();
 await p.locator('#menu button').first().waitFor({state:'attached'});
 return p;
}
async function isExpanded(p){return (await p.locator('#taMenuToggle').getAttribute('aria-expanded'))==='true';}
async function open(p,key){
 const toggle=p.locator('#taMenuToggle');
 if(await toggle.isVisible()&&!await isExpanded(p))await toggle.click();
 await p.locator('#menu [data-vista="'+key+'"]').click();
}
const mobile=await login(390);
const toggle=mobile.locator('#taMenuToggle');
for(const key of ['Enter','Space']){
 await check('menu-'+key+'-and-escape',async()=>{
  await toggle.focus();
  await mobile.keyboard.press(key);
  assert.equal(await isExpanded(mobile),true);
  assert.equal(await mobile.evaluate(()=>document.activeElement.dataset.vista),'inicio');
  await mobile.keyboard.press('Escape');
  assert.equal(await isExpanded(mobile),false);
  assert.equal(await mobile.evaluate(()=>document.activeElement.id),'taMenuToggle');
 });
}
await check('menu-tab-without-trap',async()=>{
 await toggle.focus();
 await mobile.keyboard.press('Space');
 const last=mobile.locator('#menu button').last();
 await last.focus();
 await mobile.keyboard.press('Tab');
 assert.equal(await mobile.evaluate(()=>document.getElementById('taSidebar').contains(document.activeElement)),false);
 await mobile.screenshot({path:path.join(out,'menu-teclado-movil.png'),fullPage:true});
 await toggle.click();
});
await check('menu-same-breakpoint-retains-state',async()=>{
 await toggle.focus();
 await mobile.keyboard.press('Enter');
 for(const width of [390,600,768,600,390]){
  await mobile.setViewportSize({width,height:900});
  assert.equal(await isExpanded(mobile),true);
  assert.equal(await mobile.evaluate(()=>document.activeElement.dataset.vista),'inicio');
 }
 await mobile.keyboard.press('Escape');
});
await check('menu-legitimate-crossings-reset-and-recover-focus',async()=>{
 for(let run=0;run<5;run++){
  await toggle.focus();
  await mobile.keyboard.press('Space');
  assert.equal(await isExpanded(mobile),true);
  await mobile.setViewportSize({width:1440,height:900});
  await mobile.waitForFunction(()=>document.getElementById('taMenuToggle').getAttribute('aria-expanded')==='false');
  assert.equal(await mobile.evaluate(()=>document.activeElement.dataset.vista),'inicio');
  await mobile.setViewportSize({width:390,height:900});
  await mobile.waitForFunction(()=>document.activeElement.id==='taMenuToggle');
  assert.equal(await isExpanded(mobile),false);
 }
});
await mobile.close();
const labels={fDesde:'Folio inicial del trámite',fHasta:'Folio final del trámite',fRad:'Número de radicado del trámite',fObs:'Observaciones del trámite'};
for(const [mode,width] of [['escritorio',1440],['tableta',768],['movil',390]]){
 const p=await login(width,'equipo');
 await open(p,'hojas');
 const sheet=p.locator('#vHojas');
 await check('control-sheet-names-'+mode,async()=>{
  await p.evaluate(()=>{agregarFila({desde:2,hasta:2,radicado:'SYN14A',obs:'Observación sintética'});});
  const row=p.locator('#cuerpoHc tr').last();
  for(const [cls,name] of Object.entries(labels)){
   assert.equal(await row.getByRole('textbox',{name,exact:true}).count(),1);
   assert.equal(await row.locator('.'+cls).evaluate(e=>e.labels.length),1);
  }
  assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),width);
  const scroll=await p.locator('#tablaHc').evaluate(e=>({viewport:e.parentElement.clientWidth,table:e.parentElement.scrollWidth}));
  if(mode!=='escritorio')assert.ok(scroll.table>scroll.viewport);
  await p.screenshot({path:path.join(out,'hoja-control-'+mode+'.png'),fullPage:true});
 });
 await check('control-sheet-validation-'+mode,async()=>{
  await p.evaluate(()=>marcarErrores([
    {no_item:1,campo:'folio_desde',mensaje:'El trámite debía empezar en el folio 2.'},
    {no_item:1,campo:'folio_desde',mensaje:'Revise el folio en el original.'},
    {no_item:1,campo:'folio_hasta',mensaje:'Compruebe el folio final.'}
  ]));
  const first=p.locator('#cuerpoHc tr').first();
  const start=first.getByRole('textbox',{name:labels.fDesde,exact:true});
  assert.equal(await start.getAttribute('aria-invalid'),'true');
  const described=await start.evaluate(e=>e.getAttribute('aria-describedby').split(' ').map(id=>document.getElementById(id)?.textContent));
  assert.deepEqual(described,['El trámite debía empezar en el folio 2.','Revise el folio en el original.']);
  assert.equal(await first.getByRole('button',{name:'Continuar desde el folio 2'}).count(),1);
  await p.screenshot({path:path.join(out,'hoja-validacion-'+mode+'.png'),fullPage:true});
  await p.evaluate(()=>marcarErrores([]));
  assert.equal(await start.getAttribute('aria-invalid'),null);
  assert.equal(await start.getAttribute('aria-describedby'),null);
  assert.equal(await first.locator('.errCelda,.continuarFoliosError').count(),0);
 });
 await check('control-sheet-axe-'+mode,async()=>{
  await p.evaluate(axe);
  const results=await p.evaluate(()=>window.axe.run('#vHojas',{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}));
  scans.push({mode,engine:results.testEngine,violations:results.violations,incomplete:results.incomplete});
  assert.deepEqual(results.violations.map(v=>[v.id,v.nodes.map(n=>n.target)]),[]);
 });
 await p.close();
}
await browser.close();
const result={tests,scans,passed:tests.filter(t=>t.status==='PASS').length,failed:tests.filter(t=>t.status==='FAIL').length};
await fs.writeFile(path.join(out,'fixes14a.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({passed:result.passed,failed:result.failed,failures:tests.filter(t=>t.status==='FAIL')}));
process.exitCode=result.failed?1:0;
