import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const root=path.dirname(fileURLToPath(import.meta.url));
const state=JSON.parse(await fs.readFile(path.join(root,'campaign-full/phase13e-environment.json'),'utf8'));
assert.match(state.project,/^geology-auto11e-a11y13e-full-/);
const creds=JSON.parse(await fs.readFile(path.join(state.control,'ui-private.json'),'utf8'));
const base='http://127.0.0.1:'+state.port;
const out=path.join(root,'results');
const browser=await chromium.launch({headless:true});
const tests=[],permissions=[],scans=[],errors=[];
const axe=await fs.readFile(path.join(root,'tools/axe.min.js'),'utf8');
async function check(id,fn){
  try {tests.push({id,status:'PASS',detail:await fn()});}
  catch(error){tests.push({id,status:'FAIL',error:error.message.slice(0,900)});}
}
async function login(role){
  const p=await browser.newPage({viewport:{width:1440,height:950}});
  p.on('pageerror',error=>errors.push(error.message));
  p.setDefaultTimeout(6000);
  await p.goto(base+'/app');
  await p.locator('#correo').fill(role+'13e@example.invalid');
  await p.locator('#clave').fill(creds.password);
  await p.locator('#btnIngresar').click();
  await p.locator('#pApp').waitFor({state:'visible'});
  return p;
}
const nav=(p,n)=>p.locator('#menu').getByRole('button',{name:n,exact:true});
const shot=(p,n)=>p.screenshot({path:path.join(out,n+'.png'),fullPage:true});
async function scan(p,name){
  await p.evaluate(axe);
  const r=await p.evaluate(()=>window.axe.run({runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}));
  scans.push({name,violations:r.violations,incomplete:r.incomplete,engine:r.testEngine});
  assert.deepEqual(r.violations.map(v=>[v.id,v.nodes.map(n=>n.target)]),[]);
}
async function responsive(p,name){
  await shot(p,name+'-escritorio');
  for(const width of [768,390,320]){
    await p.setViewportSize({width,height:900});
    assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),width);
    if(width===390)await shot(p,name+'-movil');
  }
  await p.setViewportSize({width:1440,height:950});
}
const team=await login('equipo');
await nav(team,'Cargue').click();
const input=team.locator('#selArchivos');
const send=team.locator('#cgConfirmar');
const synthetic=path.join(root,'AC-CP-99994.pdf');
let uploads=0;
team.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/cargue/cargar'))uploads++;});
await check('inventory-preview',async()=>{
  await team.getByLabel('Código de carpeta del inventario').fill('AC-CP-99994');
  await team.getByRole('button',{name:'Consultar inventario',exact:true}).click();
  await team.locator('#cgInventarioEstado').getByText(/AC-CP-99994.*CARGUE13E/).waitFor();
});
await check('validation-and-no-premature-upload',async()=>{
  await input.setInputFiles([{name:'sintetico.txt',mimeType:'text/plain',buffer:Buffer.from('synthetic')},{name:'vacio.pdf',mimeType:'application/pdf',buffer:Buffer.alloc(0)}]);
  assert.match(await team.locator('#cgError').innerText(),/Formato no admitido.*Archivo vacío/);
  assert.ok(await send.isDisabled());
  assert.equal(uploads,0);
  await team.locator('#cgLimpiar').click();
  assert.equal(await team.evaluate(()=>document.activeElement.id),'cgSeleccionar');
  assert.equal(await team.locator('#cgError').innerText(),'');
});
await check('real-upload-explicit-confirmation',async()=>{
  await input.setInputFiles(synthetic);
  assert.equal(uploads,0);
  assert.equal(await team.locator('#cgEtapas [aria-current=step]').innerText(),'Confirmar cargue');
  await send.focus();
  const response=team.waitForResponse(r=>r.url().endsWith('/cargue/cargar')&&r.request().method()==='POST');
  await team.keyboard.press('Enter');
  const r=await response;
  assert.equal(r.status(),200);
  const body=await r.json();
  assert.equal(body.carpeta,'AC-CP-99994');
  assert.equal(body.estado,'En cola');
  assert.equal(body.levantamiento_automatico,false);
  await team.locator('#lecturaNombres').getByText('En cola',{exact:true}).waitFor();
  await team.locator('#cgTransferencia').getByText(/Envío finalizado/).waitFor();
  assert.equal(uploads,1);
});
await check('upload-responsive',async()=>{
  await responsive(team,'cargue');
  await team.setViewportSize({width:390,height:900});
  const region=team.locator('#lecturaNombres [role=region]');
  await region.focus();
  assert.equal(await region.evaluate(e=>e===document.activeElement && e.scrollWidth>e.clientWidth),true);
  await team.setViewportSize({width:1440,height:950});
});
await check('upload-axe',()=>scan(team,'Cargue'));
await check('duplicate-server-message',async()=>{
  await input.setInputFiles(synthetic);
  const response=team.waitForResponse(r=>r.url().endsWith('/cargue/cargar')&&r.request().method()==='POST');
  await send.click();
  const r=await response;
  assert.equal(r.status(),409);
  const body=await r.json();
  await team.locator('#lecturaNombres').getByText(body.detail,{exact:true}).waitFor();
  assert.equal(uploads,2);
  await team.locator('#cgHistorial > summary').click();
  await team.locator('#cgHistorialLotes summary').click();
  await team.locator('#cgHistorialLotes').getByText('En cola',{exact:true}).waitFor();
});
await check('process-navigation-real-state',async()=>{
  await team.locator('#cgIrProceso').click();
  await team.locator('#buscarProceso').fill('99994');
  const row=team.locator('tr.carpeta').filter({hasText:'AC-CP-99994'});
  await row.getByText('En cola',{exact:true}).waitFor();
  assert.match(await row.innerText(),/1 archivo/);
});
await check('process-technical-detail',async()=>{
  const trigger=team.locator('tr.carpeta').filter({hasText:'AC-CP-99994'}).getByRole('button',{name:'Detalle técnico'});
  await trigger.click();
  await team.locator('#taProcessParts').getByText(/Archivo registrado disponible.*Copia de consulta/).waitFor();
  assert.equal(await team.locator('#taProcessDetail').getByRole('button',{name:'Ver documento'}).count(),1);
  assert.equal(await team.evaluate(()=>document.activeElement.id),'taProcessDetail');
  await shot(team,'digitalizacion-detalle-escritorio');
  await team.locator('#taProcessClose').click();
  assert.ok(await trigger.evaluate(e=>document.activeElement===e));
});
await check('process-responsive',()=>responsive(team,'digitalizacion'));
await check('process-axe',()=>scan(team,'Digitalización'));
const lead=await login('lider');
await nav(lead,'Revisión').click();
const open=lead.getByRole('button',{name:'Abrir revisión de AC-CP-99995',exact:true});
await check('review-filter-focus-and-return',async()=>{
  await lead.locator('#taReviewState').selectOption('Descripción por validar');
  await lead.locator('#taReviewQuery').fill('99995');
  await open.waitFor();
  await open.focus();
  await lead.keyboard.press('Enter');
  await lead.locator('#fichaRevision').getByRole('heading',{name:/AC-CP-99995/}).waitFor();
  assert.equal(await lead.evaluate(()=>document.activeElement.id),'fichaRevision');
  await shot(lead,'revision-ficha-escritorio');
  await lead.locator('#fichaRevision').getByRole('button',{name:'Cerrar',exact:true}).click();
  assert.equal(await lead.evaluate(()=>document.activeElement.getAttribute('aria-label')),'Abrir revisión de AC-CP-99995');
  assert.equal(await lead.locator('#taReviewQuery').inputValue(),'99995');
});
await check('review-responsive',()=>responsive(lead,'revision'));
await check('review-axe',()=>scan(lead,'Revisión'));
for(const role of ['administradora','equipo','lider','consulta','entidad']){
  await check('permissions-'+role,async()=>{
    const p=await login(role);
    const menu=await p.locator('#menu button').allTextContents();
    const result=await p.evaluate(async()=>{
      const data=new FormData();
      data.append('archivo',new File(['invalido'],'invalido.pdf',{type:'application/pdf'}));
      const headers={Authorization:'Bearer '+PASE};
      const [upload,review]=await Promise.all([
        fetch(API+'/cargue/cargar',{method:'POST',headers,body:data}),
        fetch(API+'/unidades/AC-CP-99995',{headers})
      ]);
      return {upload:upload.status,review:review.status};
    });
    assert.equal(result.upload,['consulta','entidad'].includes(role)?403:422);
    assert.equal(result.review,role==='entidad'?403:200);
    assert.equal(menu.includes('Cargue'),result.upload!==403);
    if(role==='entidad')assert.ok(!menu.includes('Proceso')&&!menu.includes('Revisión'));
    permissions.push({role,menu,...result});
    await p.close();
  });
}
await check('no-browser-errors',()=>assert.deepEqual(errors,[]));
await browser.close();
const result={tests,permissions,passed:tests.filter(x=>x.status==='PASS').length,failed:tests.filter(x=>x.status==='FAIL').length};
await fs.writeFile(path.join(out,'workflow-tests.json'),JSON.stringify(result,null,2));
await fs.writeFile(path.join(out,'axe-workflow.json'),JSON.stringify(scans,null,2));
console.log(JSON.stringify({passed:result.passed,failed:result.failed,failures:tests.filter(x=>x.status==='FAIL')}));
process.exitCode=result.failed?1:0;

