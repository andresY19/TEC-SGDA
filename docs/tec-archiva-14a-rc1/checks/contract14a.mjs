import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const b=path.dirname(fileURLToPath(import.meta.url));
const state=JSON.parse(await fs.readFile(path.join(b,'campaign-full/phase14a-environment.json'),'utf8'));
assert.match(state.project,/^geology-auto11e-a11y14a-full-/);
const creds=JSON.parse(await fs.readFile(path.join(state.control,'ui-private.json'),'utf8'));
const data=JSON.parse(await fs.readFile(path.join(b,'results/cross14a.json'),'utf8'));
const browser=await chromium.launch({headless:true});
const axe=await fs.readFile(path.join(b,'tools/axe.min.js'),'utf8');
const observed=[];
for(const [mode,width,height] of [['escritorio',1440,1000],['tableta',768,1024],['movil',390,844]]){
 const p=await browser.newPage({viewport:{width,height}});
 p.setDefaultTimeout(7500);
 const id='contract-settled-'+mode;
 try {
  await p.goto('http://127.0.0.1:'+state.port+'/app');
  await p.locator('#correo').fill('administradora14a@example.invalid');
  await p.locator('#clave').fill(creds.password);
  await p.locator('#btnIngresar').click();
  await p.locator('#pApp').waitFor();
  const toggle=p.locator('#taMenuToggle');
  if(await toggle.isVisible())await toggle.click();
  await p.locator('#menu [data-vista=contrato]').click();
  await p.locator('#ctCuerpo .metro').first().waitFor();
  const detail=await p.locator('#ctCuerpo').evaluate(e=>({cards:e.querySelectorAll('.metro').length,table:!!e.querySelector('table'),width:document.documentElement.scrollWidth}));
  observed.push({mode,...detail});
  await p.screenshot({path:path.join(b,'results','contrato-cargado-'+mode+'.png'),fullPage:true});
  if(mode==='escritorio'){
   await p.evaluate(axe);
   const a=await p.evaluate(()=>window.axe.run('#vContrato',{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}));
   data.scans.push({key:'contrato-cargado',viewport:mode,engine:a.testEngine,incomplete:a.incomplete.map(x=>x.id),violations:a.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,targets:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}))});
  }
  assert.equal(detail.cards,6);
  assert.equal(detail.table,true);
  assert.equal(detail.width,width,'Desbordamiento del contrato tras cargar');
  data.tests.push({id,status:'PASS',detail});
  data.passed++;
 }catch(e){data.tests.push({id,status:'FAIL',error:e.message.slice(0,1000)});data.failed++;}
 finally{await p.close();}
}
await browser.close();
data.contractSettled=observed;
await fs.writeFile(path.join(b,'results/cross14a.json'),JSON.stringify(data,null,2));
console.log(JSON.stringify({observed,passed:data.passed,failed:data.failed}));
