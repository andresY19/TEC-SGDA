import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const root=path.dirname(fileURLToPath(import.meta.url));
const state=JSON.parse(await fs.readFile(path.join(root,'campaign-full/phase13e-environment.json'),'utf8'));
assert.match(state.project,/^geology-auto11e-a11y13e-full-/);
const creds=JSON.parse(await fs.readFile(path.join(state.control,'ui-private.json'),'utf8'));
const origin='http://127.0.0.1:'+state.port;
const out=path.join(root,'results');
const browser=await chromium.launch({headless:true});
const tests=[], permissions=[], scans=[], errors=[];
const axe=await fs.readFile(path.join(root,'tools/axe.min.js'),'utf8');
async function check(id,fn) {
  try { tests.push({id,status:'PASS',detail:await fn()}); }
  catch (error) { tests.push({id,status:'FAIL',error:error.message.slice(0,700)}); }
}
async function login(role) {
  const p=await browser.newPage({viewport:{width:1440,height:1000}});
  p.on('pageerror',error=>errors.push(error.message));
  await p.goto(origin+'/app');
  await p.locator('#correo').fill(role+'13e@example.invalid');
  await p.locator('#clave').fill(creds.password);
  await p.locator('#btnIngresar').click();
  await p.locator('#pApp').waitFor({state:'visible'});
  return p;
}
const nav=(p,name)=>p.locator('#menu').getByRole('button',{name,exact:true});
const capture=(p,name)=>p.screenshot({path:path.join(out,name+'.png'),fullPage:true});
async function scan(p,name) {
  await p.evaluate(axe);
  const result=await p.evaluate(()=>window.axe.run({runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}));
  scans.push({name,engine:result.testEngine,violations:result.violations,incomplete:result.incomplete});
  assert.deepEqual(result.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})),[]);
}
const team=await login('equipo');
await nav(team,'Planeación').click();
const inventory=team.locator('#plCajas');
await inventory.locator('tbody tr').first().waitFor();
await check('inventory-search-and-server-count',async()=>{
  await team.locator('#plBuscar').fill('SYN13E');
  await team.getByRole('button',{name:'Buscar inventario',exact:true}).click();
  await inventory.getByRole('status').filter({hasText:'14 resultados'}).waitFor();
  assert.equal(await inventory.locator('tbody tr').count(),10);
});
await check('inventory-filter-and-pagination',async()=>{
  await team.locator('#taInventoryPeriod').selectOption('I');
  assert.match(await inventory.getByRole('status').innerText(),/12 resultados/);
  await inventory.getByRole('button',{name:'Siguiente',exact:true}).click();
  assert.match(await inventory.getByRole('status').innerText(),/Página 2 de 2/);
  assert.equal(await inventory.locator('tbody tr').count(),2);
  await inventory.getByRole('button',{name:'Anterior',exact:true}).click();
});
await check('inventory-sort-and-focus',async()=>{
  const sort=inventory.getByRole('button',{name:'Ordenar por Carpeta',exact:true});
  await sort.click();
  assert.match(await inventory.locator('tbody tr').first().innerText(),/AC-CP-99900/);
  await sort.click();
  assert.match(await inventory.locator('tbody tr').first().innerText(),/AC-CP-99911/);
  assert.equal(await inventory.locator('th[aria-sort=descending]').count(),1);
  assert.ok(await sort.evaluate(e=>document.activeElement===e));
});
await capture(team,'inventarios-escritorio');
await check('inventory-axe',()=>scan(team,'Inventarios'));
await check('inventory-empty-and-error',async()=>{
  await team.locator('#plBuscar').fill('SIN-RESULTADOS-13E');
  await team.getByRole('button',{name:'Buscar inventario',exact:true}).click();
  await inventory.getByText('No hay carpetas que coincidan con los filtros.',{exact:true}).waitFor();
  assert.ok(await inventory.locator('.ta-pagination').isHidden());
  await team.route('**/planeacion/cajas?**',route=>route.fulfill({status:503,contentType:'application/json',body:'{"detail":"Inventario temporalmente indisponible"}'}));
  await team.getByRole('button',{name:'Buscar inventario',exact:true}).click();
  assert.equal(await inventory.getByRole('alert').innerText(),'Inventario temporalmente indisponible');
  assert.ok(await inventory.locator('.ta-pagination').isHidden());
  await team.unroute('**/planeacion/cajas?**');
  await team.locator('#plBuscar').fill('SYN13E');
  await team.getByRole('button',{name:'Buscar inventario',exact:true}).click();
  await inventory.locator('tbody tr').first().waitFor();
});
await check('inventory-tablet-and-mobile-reflow',async()=>{
  for(const width of [768,390,320]) {
    await team.setViewportSize({width,height:900});
    assert.equal(await team.evaluate(()=>document.documentElement.scrollWidth),width);
    if(width===390)await capture(team,'inventarios-movil');
  }
  await team.setViewportSize({width:1440,height:1000});
});
const consult=await login('consulta');
await consult.locator('#taRecordsResults tbody tr').first().waitFor();
const results=consult.locator('#taRecordsResults');
await check('records-filter-server-and-search',async()=>{
  await consult.locator('#taRecordState').selectOption('En cola');
  await consult.locator('#taRecordQuery').fill('99881');
  await consult.getByRole('button',{name:'Aplicar filtros',exact:true}).click();
  await results.getByRole('status').filter({hasText:'1 resultados'}).waitFor();
  assert.match(await results.locator('tbody').innerText(),/AC-CP-99881.*En cola/s);
});
await capture(consult,'expedientes-escritorio');
await check('records-readonly-context-and-trace',async()=>{
  await results.getByRole('button',{name:'Abrir ficha',exact:true}).click();
  const card=consult.locator('#fichaLectura12f');
  await card.getByRole('heading',{name:'AC-CP-99881',exact:true}).waitFor();
  assert.ok(await card.getByRole('heading',{name:'Trazabilidad'}).isVisible());
  assert.ok(await card.getByRole('heading',{name:'Documentos asociados'}).isVisible());
  assert.deepEqual(await card.locator('button').allTextContents(),['Volver al listado','Consultar documento autorizado']);
  await capture(consult,'ficha-escritorio');
  await card.getByRole('button',{name:'Volver al listado'}).click();
  assert.equal(await consult.locator('#taRecordQuery').inputValue(),'99881');
  assert.equal(await consult.locator('#taRecordState').inputValue(),'En cola');
  assert.ok(await results.getByRole('button',{name:'Abrir ficha',exact:true}).evaluate(e=>document.activeElement===e));
});
await check('records-axe',()=>scan(consult,'Expedientes'));
await check('records-mobile-reflow',async()=>{
  await consult.setViewportSize({width:390,height:844});
  assert.equal(await consult.evaluate(()=>document.documentElement.scrollWidth),390);
  await capture(consult,'expedientes-movil');
});
const entity=await login('entidad');
const published=entity.locator('#taPublishedResults');
await published.locator('tbody tr').first().waitFor();
await check('published-list-excludes-reserved',async()=>{
  assert.deepEqual(await entity.locator('#menu button').allTextContents(),['Consulta']);
  assert.match(await published.getByRole('status').innerText(),/13 resultados/);
  const rows=await entity.evaluate(()=>pedir('/consulta/unidades'));
  assert.ok(rows.every(row=>row.carpeta!=='AC-CP-99913'));
  assert.equal(await entity.getByRole('button',{name:/Descargar|Ver imágenes|Ver hoja/}).count(),0);
});
await capture(entity,'consulta-escritorio');
await check('published-detail-and-page-context',async()=>{
  await published.getByRole('button',{name:'Siguiente',exact:true}).click();
  const trigger=published.getByRole('button',{name:'Ver ficha publicada',exact:true}).first();
  const code=(await trigger.locator('xpath=ancestor::tr/td[1]').innerText()).trim();
  await trigger.click();
  const detail=entity.locator('#taPublishedDetail');
  await detail.getByRole('heading',{name:code,exact:true}).waitFor();
  assert.equal(await detail.getByRole('button',{name:/Descargar|Ver imágenes|Editar|Aprobar/}).count(),0);
  assert.equal(await entity.locator('#vRevision').isVisible(),false);
  await capture(entity,'consulta-ficha-escritorio');
  await detail.getByRole('button',{name:'Volver a resultados',exact:true}).click();
  assert.match(await published.getByRole('status').innerText(),/Página 2 de 2/);
  assert.ok(await trigger.evaluate(e=>document.activeElement===e));
});
await check('published-search-and-query-boundary',async()=>{
  await entity.locator('#coBuscar').fill('AC-CP-99913');
  await entity.locator('#vConsulta').getByRole('button',{name:'Buscar',exact:true}).click();
  await published.getByText('No hay unidades publicadas que cumplan esa búsqueda.',{exact:true}).waitFor();
  const statuses=await entity.evaluate(async()=>Promise.all(['/consulta/unidades/AC-CP-99913','/unidades/AC-CP-99900','/consulta/hoja-de-control/AC-CP-99900','/consulta/ver/AC-CP-99900'].map(async route=>(await fetch(route,{headers:{Authorization:'Bearer '+PASE}})).status)));
  assert.deepEqual(statuses,[404,403,403,403]);
  await entity.locator('#coBuscar').fill('AC-CP-99900');
  await entity.locator('#vConsulta').getByRole('button',{name:'Buscar',exact:true}).click();
  await published.getByRole('status').filter({hasText:'1 resultados'}).waitFor();
});
await check('published-axe',()=>scan(entity,'Consulta'));
await check('published-mobile-reflow',async()=>{
  await entity.setViewportSize({width:390,height:844});
  assert.equal(await entity.evaluate(()=>document.documentElement.scrollWidth),390);
  await capture(entity,'consulta-movil');
});
for(const role of ['administradora','equipo','lider','consulta','entidad']) {
  await check('permission-matrix-'+role,async()=>{
    const p=await login(role);
    try {
      const who=await p.evaluate(()=>pedir('/cuentas/yo'));
      const keys=await p.locator('#menu button').evaluateAll(nodes=>nodes.map(n=>n.dataset.vista));
      assert.deepEqual([...keys].sort(),[...who.pestanas].sort());
      permissions.push({role,menu:keys,inventory:keys.includes('planeacion'),records:keys.includes('localizacion'),published:keys.includes('consulta')});
    } finally { await p.close(); }
  });
}
await check('no-browser-exceptions',async()=>assert.deepEqual(errors,[]));
await browser.close();
const result={tests,permissions,passed:tests.filter(t=>t.status==='PASS').length,failed:tests.filter(t=>t.status==='FAIL').length};
await fs.writeFile(path.join(out,'records-tests.json'),JSON.stringify(result,null,2));
await fs.writeFile(path.join(out,'axe-records.json'),JSON.stringify(scans,null,2));
console.log(JSON.stringify({passed:result.passed,failed:result.failed,failures:tests.filter(t=>t.status==='FAIL')},null,2));
process.exitCode=result.failed?1:0;
