import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const root=path.dirname(fileURLToPath(import.meta.url));
const state=JSON.parse(await fs.readFile(path.join(root,'campaign-full/phase13f-environment.json'),'utf8'));
assert.match(state.project,/^geology-auto11e-a11y13f-full-/);
const creds=JSON.parse(await fs.readFile(path.join(state.control,'ui-private.json'),'utf8'));
const base='http://127.0.0.1:'+state.port;
const out=path.join(root,'results');
const browser=await chromium.launch({headless:true});
const tests=[],permissions=[],scans=[],errors=[];
const axe=await fs.readFile(path.join(root,'tools/axe.min.js'),'utf8');
async function check(id,fn){
  try{tests.push({id,status:'PASS',detail:await fn()});}
  catch(e){tests.push({id,status:'FAIL',error:e.message.slice(0,900)});}
}
async function login(role){
  const p=await browser.newPage({viewport:{width:1440,height:960},acceptDownloads:true});
  p.on('pageerror',e=>errors.push(e.message));
  p.setDefaultTimeout(7000);
  await p.goto(base+'/app');
  await p.locator('#correo').fill(role+'13f@example.invalid');
  await p.locator('#clave').fill(creds.password);
  await p.locator('#btnIngresar').click();
  await p.locator('#pApp').waitFor({state:'visible'});
  return p;
}
const nav=(p,n)=>p.locator('#menu').getByRole('button',{name:n,exact:true});
const shot=(p,n)=>p.screenshot({path:path.join(out,n+'.png'),fullPage:true});
async function scan(p,name,selector){
  await p.evaluate(axe);
  const data=await p.evaluate(sel=>window.axe.run(sel,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}),selector);
  scans.push({name,violations:data.violations,incomplete:data.incomplete,engine:data.testEngine});
  assert.deepEqual(data.violations.map(v=>[v.id,v.nodes.map(n=>n.target)]),[]);
}
async function responsive(p,name){
  await shot(p,name+'-escritorio');
  for(const width of [768,390,320]){
    await p.setViewportSize({width,height:900});
    assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth),width);
    if(width===390)await shot(p,name+'-movil');
  }
  await p.setViewportSize({width:1440,height:960});
}
const admin=await login('administradora');
const equipo=await login('equipo');
await nav(admin,'Cuentas').click();
const row=admin.locator('#cuTabla tr').filter({hasText:'equipo13f@example.invalid'});
await row.waitFor();
await check('account-directory-filters',async()=>{
  await admin.locator('#taAccountSearch').fill('equipo13f@example.invalid');
  assert.equal(await admin.locator('#cuTabla tr:visible').count(),1);
  await admin.locator('#taAccountRole').selectOption('entidad');
  await admin.locator('#taAccountStatus').getByText('Ninguna cuenta coincide con los filtros.').waitFor();
  await admin.locator('#taAccountRole').selectOption('equipo');
  await admin.locator('#taAccountState').selectOption('inactiva');
  assert.equal(await admin.locator('#cuTabla tr:visible').count(),0);
  await admin.locator('#taAccountState').selectOption('activa');
  await row.waitFor();
});
await check('account-native-validation',async()=>{
  let calls=0;
  admin.on('request',r=>{if(r.url().endsWith('/cuentas/crear'))calls++;});
  await admin.locator('#cuNombre').fill('Usuario sintético de validación');
  await admin.locator('#cuCorreo').fill('correo-invalido');
  await admin.locator('#taNewAccount button[type=submit]').click();
  assert.equal(await admin.locator('#cuCorreo').evaluate(e=>e.validity.typeMismatch),true);
  assert.equal(calls,0);
  await admin.locator('#cuNombre').fill('');
  await admin.locator('#cuCorreo').fill('');
});
await check('pending-exception-remains-disabled',async()=>{
  const control=row.getByLabel('Aprueba lo propio');
  assert.equal(await control.isChecked(),false);
  assert.equal(await control.isDisabled(),true);
});
const dialog=admin.locator('#taAccountConfirm');
await check('cancel-confirmation-keyboard-focus',async()=>{
  const trigger=row.getByRole('button',{name:'Desactivar',exact:true});
  let mutations=0;
  admin.on('request',r=>{if(r.method()==='PUT'&&r.url().endsWith('/cuentas/equipo13f%40example.invalid'))mutations++;});
  await trigger.focus();
  await admin.keyboard.press('Enter');
  await dialog.waitFor();
  assert.equal(await admin.evaluate(()=>document.activeElement.textContent),'Cancelar');
  await shot(admin,'administracion-confirmacion');
  await admin.keyboard.press('Escape');
  await dialog.waitFor({state:'hidden'});
  await admin.waitForFunction(()=>document.activeElement?.dataset.cuentaAccion==='desactivar');
  assert.equal(mutations,0);
});
await check('deactivation-and-revocation',async()=>{
  const call=(p)=>p.evaluate(async()=> (await fetch(API+'/cuentas/yo',{headers:{Authorization:'Bearer '+PASE}})).status);
  assert.equal(await call(equipo),200);
  await row.getByRole('button',{name:'Desactivar',exact:true}).click();
  await dialog.getByRole('button',{name:'Confirmar',exact:true}).click();
  await admin.locator('#cuAviso').getByText(/cuenta desactivada/).waitFor();
  assert.equal(await call(equipo),401);
  await admin.locator('#taAccountState').selectOption('inactiva');
  await row.getByRole('button',{name:'Activar',exact:true}).click();
  await dialog.getByRole('button',{name:'Confirmar',exact:true}).click();
  await admin.locator('#cuAviso').getByText(/cuenta activada/).waitFor();
  assert.equal(await call(equipo),401);
  await admin.locator('#taAccountSearch').fill('');
  await admin.locator('#taAccountRole').selectOption('');
  await admin.locator('#taAccountState').selectOption('');
});
await check('account-audit-filters',async()=>{
  const endpoint=admin.waitForResponse(r=>r.request().method()==='GET'&&r.url().includes('/vigilancia/descargas?desde=2026-01-01'));
  await admin.locator('#dsDesde').fill('2026-01-01');
  await admin.locator('#cuDescargas').getByRole('button',{name:'Consultar',exact:true}).click();
  const response=await endpoint;
  assert.equal(response.status(),200);
  assert.match(response.url(),/2026-01-01/);
});
await check('directory-pagination-synthetic-response',async()=>{
  await admin.route('**/cuentas',async route=>{
    const response=await route.fetch();
    const original=await response.json();
    const fixtures=Array.from({length:26},(_,i)=>({...original[0],correo:'paginacion'+i+'@example.invalid',nombre:'SINTÉTICO PAGINACIÓN '+i}));
    await route.fulfill({response,json:[...original,...fixtures]});
  });
  try{
    await admin.evaluate(()=>cargarCuentas());
    assert.equal(await admin.locator('#cuTabla tr:visible').count(),25);
    const expected=await admin.locator('#cuTabla tr').count();
    await admin.locator('#taAccountNext').click();
    assert.equal(await admin.locator('#cuTabla tr:visible').count(),expected-25);
    assert.equal(await admin.evaluate(()=>document.activeElement.id),'taAccountPrevious');
  }finally{
    await admin.unroute('**/cuentas');
    await admin.evaluate(()=>cargarCuentas());
  }
});
await check('administration-responsive',async()=>{
  await responsive(admin,'administracion');
  await admin.setViewportSize({width:390,height:900});
  for(const id of ['dsDesde','dsHasta','dsPersona']){
    const width=await admin.locator('#'+id).evaluate(el=>el.getBoundingClientRect().width);
    assert.ok(width>=130,id+' width: '+width);
  }
  await admin.setViewportSize({width:1440,height:960});
});
await check('administration-axe',()=>scan(admin,'Administración','#vCuentas'));
await nav(admin,'Centro de control').click();
await check('report-source-and-informative-label',async()=>{
  const expected=await admin.evaluate(()=>pedir('/unidades/produccion'));
  await admin.locator('#metrosAvance .metro,#metrosAvance .ficha').first().waitFor();
  assert.match(await admin.locator('#selloAvance').innerText(),new RegExp(expected.embudo.folios_registrados+' folios registrados'));
  assert.match(await admin.locator('#vAvance .ta-report-note').innerText(),/informativos/);
});
await check('report-day-filter',async()=>{
  const day=admin.getByLabel('Día consultado');
  await day.locator('option').first().waitFor({state:'attached'});
  const value=await day.locator('option').first().getAttribute('value');
  const hit=admin.waitForResponse(r=>r.url().includes('/unidades/produccion?dia='));
  await day.selectOption(value);
  const r=await hit;
  assert.equal(r.status(),200);
  assert.equal(new URL(r.url()).searchParams.get('dia'),value);
});
await check('reports-responsive',()=>responsive(admin,'reportes'));
await check('reports-axe',()=>scan(admin,'Centro de control','#vAvance'));
await nav(admin,'Seguimiento').click();
await check('tracking-and-real-xlsx',async()=>{
  const save=admin.waitForEvent('download');
  await admin.locator('#segTablero').getByRole('button',{name:'Descargar en Excel'}).click();
  const dl=await save;
  assert.match(dl.suggestedFilename(),/\.xlsx$/i);
  const data=await fs.readFile(await dl.path());
  assert.equal(data.subarray(0,2).toString(),'PK');
  await shot(admin,'seguimiento-escritorio');
});
await check('tracking-axe',()=>scan(admin,'Seguimiento','#vSeguimiento'));
for(const role of ['administradora','equipo','lider','consulta','entidad']){
  await check('role-'+role,async()=>{
    const p=await login(role);
    const menu=await p.locator('#menu button').allTextContents();
    const api=await p.evaluate(async()=>Object.fromEntries(await Promise.all(['/cuentas','/unidades/produccion'].map(async url=>[url,(await fetch(API+url,{headers:{Authorization:'Bearer '+PASE}})).status]))));
    assert.equal(api['/cuentas'],role==='administradora'?200:403);
    assert.equal(menu.includes('Cuentas'),role==='administradora');
    if(role==='entidad')assert.equal(api['/unidades/produccion'],403);
    permissions.push({role,menu,api});await p.close();
  });
}
await check('no-browser-errors',()=>assert.deepEqual(errors,[]));
await browser.close();
const result={tests,permissions,passed:tests.filter(x=>x.status==='PASS').length,failed:tests.filter(x=>x.status==='FAIL').length};
await fs.writeFile(path.join(out,'admin-report-tests.json'),JSON.stringify(result,null,2));
await fs.writeFile(path.join(out,'axe-admin-report.json'),JSON.stringify(scans,null,2));
console.log(JSON.stringify({passed:result.passed,failed:result.failed,failures:tests.filter(x=>x.status==='FAIL')}));
process.exitCode=result.failed?1:0;
