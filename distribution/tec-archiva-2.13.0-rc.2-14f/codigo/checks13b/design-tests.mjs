import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const root = path.dirname(fileURLToPath(import.meta.url));
const campaign = path.join(root,'campaign-full');
const state = JSON.parse(await fs.readFile(path.join(campaign,'phase13b-environment.json'),'utf8'));
assert.match(state.project,/^geology-auto11e-a11y13b-full-/);
const privateData = JSON.parse(await fs.readFile(path.join(state.control,'ui-private.json'),'utf8'));
const origin = 'http://127.0.0.1:'+state.port;
const output = path.join(root,'results');
const axe = await fs.readFile(path.join(root,'tools/axe.min.js'),'utf8');
const browser = await chromium.launch({headless:true});
const tests = [], permissions = [], exceptions = [];
async function check(id, fn) {
  try { tests.push({id,status:'PASS',detail:await fn()}); }
  catch (error) { tests.push({id,status:'FAIL',error:String(error.message).slice(0,600)}); }
}
const page = await browser.newPage({viewport:{width:1440,height:980}});
page.on('pageerror',error=>exceptions.push(String(error)));
await page.goto(origin+'/app');
const capture = (p,name) => p.screenshot({path:path.join(output,name+'.png'),fullPage:true});
await check('BR01-brand-title-and-message', async()=>{
  assert.equal(await page.title(),'TEC-ARCHIVA | Gestión documental inteligente');
  assert.match(await page.locator('.ta-login-brand').innerText(),/Gestión documental,\s*bajo tu control/);
  assert.match(await page.locator('.ta-login-brand').innerText(),/Gestión documental inteligente/);
});
await check('BR02-palette-and-split-layout', async()=>{
  const result=await page.locator('.ta-login').evaluate(el=>{
    const css=getComputedStyle(document.documentElement);
    const tokens=['violet','indigo','blue','white','ink'].map(key=>css.getPropertyValue('--ta-'+key).trim().toUpperCase());
    return {tokens,columns:getComputedStyle(el).gridTemplateColumns.split(' ').length};
  });
  assert.deepEqual(result.tokens,['#6257DC','#4848B6','#29577E','#FFFFFF','#172033']);
  assert.equal(result.columns,2);
});
await capture(page,'login-desktop');
await check('BR03-mobile-login-reflow', async()=>{
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.locator('.ta-login').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').length),1);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
  await capture(page,'login-mobile');
  await page.setViewportSize({width:1440,height:980});
});
await check('BR04-existing-login-form-only', async()=>{
  assert.equal(await page.getByLabel('Correo institucional',{exact:true}).count(),1);
  assert.equal(await page.getByLabel('Contraseña',{exact:true}).count(),1);
  assert.equal(await page.locator('#pIngreso a').count(),0);
});
async function login(p,role) {
  await p.locator('#correo').fill(role+'13b@example.invalid');
  await p.locator('#clave').fill(privateData.password);
  await p.locator('#btnIngresar').click();
  await p.locator('#pApp').waitFor({state:'visible'});
}
await login(page,'administradora');
await page.locator('#taIndicators[aria-busy=false]').waitFor();
await check('BR05-sidebar-topbar-content',async()=>{
  assert.ok(await page.locator('#taSidebar').isVisible());
  assert.ok(await page.locator('.ta-topbar #quienNombre').isVisible());
  assert.equal(await page.locator('main#taMain').count(),1);
  assert.equal(await page.locator('#taCrumb').innerText(),'Dashboard');
});
await check('BR06-real-dashboard-metrics',async()=>{
  const counts=await page.evaluate(async()=>{
    const [units,loads,now]=await Promise.all([pedir('/unidades/resumen'),pedir('/cargue/estado-de-cargas'),pedir('/unidades/ahora')]);
    return [units.total,loads.resumen.archivos_cargados,now.en_vuelo.hojas_por_revisar,units.estados.find(x=>x.estado==='En procesamiento').cantidad];
  });
  const displayed=await page.locator('.ta-metric strong').allTextContents();
  assert.deepEqual(displayed,counts.map(n=>new Intl.NumberFormat('es-CO').format(n)));
  return counts;
});
await check('BR07-status-and-activity-panels',async()=>{
  assert.ok(await page.locator('#taStates .ta-state-row').count()>0);
  assert.ok(await page.locator('#taActivity li').count()>0);
  assert.ok(await page.locator('#taAlerts').innerText());
});
await capture(page,'dashboard-desktop');
await check('BR08-real-dashboard-request-failure',async()=>{
  await page.route('**/unidades/resumen',r=>r.fulfill({status:503,contentType:'application/json',body:'{"detail":"Fallo de prueba"}'}));
  await page.locator('#taRefresh').click();
  await page.locator('#taIndicators[aria-busy=false]').waitFor();
  assert.equal(await page.locator('.ta-metric strong').first().innerText(),'—');
  assert.match(await page.locator('#taDashboardStatus').innerText(),/no están disponibles/);
  await page.unroute('**/unidades/resumen');
  await page.locator('#taRefresh').click();
  await page.locator('#taIndicators[aria-busy=false]').waitFor();
});
await check('BR09-dashboard-skeleton-and-status',async()=>{
  await page.route('**/unidades/resumen',async r=>{await new Promise(resolve=>setTimeout(resolve,900));await r.continue();});
  await page.locator('#taRefresh').click();
  assert.equal(await page.locator('#taIndicators .ta-skeleton').count(),4);
  assert.equal(await page.locator('#taIndicators').getAttribute('aria-busy'),'true');
  await page.locator('#taIndicators[aria-busy=false]').waitFor();
  await page.unroute('**/unidades/resumen');
});
await check('BR10-quick-access-and-breadcrumb',async()=>{
  await page.locator('#taQuick [data-shortcut=localizacion]').click();
  assert.equal(await page.locator('#taCrumb').innerText(),'Localización');
  assert.equal(await page.locator('#menu [aria-current=page]').innerText(),'Localización');
  await page.locator('#menu [data-vista=inicio]').click();
  await page.locator('#taIndicators[aria-busy=false]').waitFor();
});
await check('BR11-mobile-keyboard-disclosure',async()=>{
  await page.setViewportSize({width:390,height:844});
  const toggle=page.locator('#taMenuToggle');
  await toggle.focus();
  await page.keyboard.press('Enter');
  assert.equal(await toggle.getAttribute('aria-expanded'),'true');
  assert.ok(await page.locator('#menu button').first().evaluate(el=>el===document.activeElement));
  await page.keyboard.press('Escape');
  assert.equal(await toggle.getAttribute('aria-expanded'),'false');
  assert.ok(await toggle.evaluate(el=>el===document.activeElement));
});
for (const [name,width] of [['tablet',768],['mobile',390],['narrow',320]]) {
  await check('BR12-reflow-'+name,async()=>{
    await page.setViewportSize({width,height:900});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),width);
    if (name!=='narrow') await capture(page,'dashboard-'+name);
  });
}
await check('BR13-mobile-navigation-activation',async()=>{
  await page.setViewportSize({width:390,height:844});
  await page.locator('#taMenuToggle').click();
  await capture(page,'navigation-mobile');
  await page.locator('#menu [data-vista=proceso]').click();
  assert.equal(await page.locator('#taMenuToggle').getAttribute('aria-expanded'),'false');
  assert.ok(await page.locator('#vCola').isVisible());
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth),390);
});
await check('BR17-mobile-document-navigation',async()=>{
  await page.locator('#buscarProceso').fill('AC-CP-99881');
  const row=page.locator('tr.carpeta').filter({hasText:'AC-CP-99881'});
  await row.waitFor();
  await row.getByRole('button',{name:'Ver ficha',exact:true}).first().click();
  await page.locator('#fichaLectura12f h2').filter({hasText:'AC-CP-99881'}).waitFor();
  assert.equal(await page.locator('#taCrumb').innerText(),'Proceso / Ficha de expediente');
  assert.equal(await page.locator('#fichaLectura12f form').count(),0);
  await page.getByRole('button',{name:'Volver al listado',exact:true}).click();
  assert.equal(await page.locator('#buscarProceso').inputValue(),'AC-CP-99881');
  assert.equal(await page.locator('#taCrumb').innerText(),'Proceso');
});
await page.setViewportSize({width:1440,height:980});
await page.locator('#menu [data-vista=inicio]').click();
await page.locator('#taIndicators[aria-busy=false]').waitFor();
await page.evaluate(axe);
const scan=await page.evaluate(()=>window.axe.run({runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}));
await fs.writeFile(path.join(output,'axe-dashboard.json'),JSON.stringify({violations:scan.violations,incomplete:scan.incomplete,testEngine:scan.testEngine},null,2));
await check('BR14-dashboard-axe',async()=>assert.deepEqual(scan.violations.map(v=>({id:v.id,targets:v.nodes.map(n=>n.target)})),[]));
for (const role of ['administradora','equipo','lider','consulta','entidad']) {
  await check('BR15-permitted-menu-'+role,async()=>{
    const p=await browser.newPage();
    try {
      p.on('pageerror',error=>exceptions.push(String(error)));
      await p.goto(origin+'/app');
      await login(p,role);
      const identity=await p.evaluate(()=>pedir('/cuentas/yo'));
      const menu=await p.locator('#menu button').evaluateAll(nodes=>nodes.map(node=>node.dataset.vista));
      assert.deepEqual([...menu].sort(),[...identity.pestanas].sort());
      const shortcuts=await p.locator('#taQuick button').evaluateAll(nodes=>nodes.map(node=>node.dataset.shortcut));
      assert.ok(shortcuts.every(key=>identity.pestanas.includes(key)));
      if(!identity.pestanas.includes('inicio')) assert.equal(await p.locator('#vInicio').isVisible(),false);
      permissions.push({role,server:identity.pestanas,menu,shortcuts});
    } finally { await p.close(); }
  });
}
await check('BR16-no-script-exceptions',async()=>assert.deepEqual(exceptions,[]));
await browser.close();
const result={tests,passed:tests.filter(t=>t.status==='PASS').length,failed:tests.filter(t=>t.status==='FAIL').length,permissions};
await fs.writeFile(path.join(output,'design-tests.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({passed:result.passed,failed:result.failed,failures:tests.filter(t=>t.status==='FAIL')},null,2));
process.exitCode=result.failed?1:0;
