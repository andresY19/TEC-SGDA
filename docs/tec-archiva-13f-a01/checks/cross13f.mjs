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
const roles=['administradora','equipo','lider','consulta','entidad'];
const modes={escritorio:{width:1440,height:1000},tableta:{width:768,height:1024},movil:{width:390,height:844}};
const tests=[],screens=[],permissions=[],scans=[],events=[],errors=[];
const axe=await fs.readFile(path.join(root,'tools/axe.min.js'),'utf8');
const snapshot=()=>({
  width:innerWidth, compact:matchMedia('(max-width:850px)').matches,
  expanded:document.getElementById('taMenuToggle')?.getAttribute('aria-expanded'),
  sidebarVisible:!!document.getElementById('taSidebar')?.getClientRects().length,
  focus:document.activeElement?.id||document.activeElement?.dataset?.vista||document.activeElement?.tagName
});
async function check(id,fn){
  try{tests.push({id,status:'PASS',detail:await fn()});}
  catch(e){tests.push({id,status:'FAIL',error:String(e.message).slice(0,1300)});}
}
async function page(width,role){
  const p=await browser.newPage({viewport:width});
  p.setDefaultTimeout(6000);
  p.on('pageerror',e=>errors.push({role,message:e.message}));
  await p.goto(base+'/app');
  if(role){
    await p.locator('#correo').fill(role+'13f@example.invalid');
    await p.locator('#clave').fill(creds.password);
    await p.locator('#btnIngresar').click();
    await p.locator('#pApp').waitFor({state:'visible'});
    await p.locator('#menu button').first().waitFor({state:'attached'});
  }
  return p;
}
const shot=(p,name)=>p.screenshot({path:path.join(out,name+'.png'),fullPage:true});
async function open(p,key){
  const button=p.locator('#menu [data-vista="'+key+'"]');
  const toggle=p.locator('#taMenuToggle');
  if(await toggle.isVisible() && await toggle.getAttribute('aria-expanded')!=='true')await toggle.click();
  const title=await button.innerText();
  await button.click();
  const v=p.locator('main .vista:not(.oculto)');
  await v.waitFor({state:'visible'});
  assert.equal(await p.locator('#taCrumb').innerText(),title);
  assert.equal(await button.getAttribute('aria-current'),'page');
  return v;
}
async function scan(p,key,viewport){
  await p.evaluate(axe);
  const result=await p.evaluate(()=>window.axe.run({runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']}}));
  scans.push({key,viewport,violations:result.violations.map(v=>({id:v.id,impact:v.impact,help:v.help,targets:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))})),incomplete:result.incomplete.map(x=>x.id),engine:result.testEngine});
}
const markers={inicio:'#taIndicators',planeacion:'#plCajas',cargue:'#cgEtapas',hojas:'#hcCarpeta',proceso:'#cuerpoProceso',revision:'#cuerpoRevision',localizacion:'#taRecordsResults',reubicacion:'#prPeriodo',instrumentos:'#insResumen',calidad:'#vCalidad',avance:'#metrosAvance',seguimiento:'#segHitos',contrato:'#ctPestanas',consulta:'#taPublished',cuentas:'#cuTabla'};
for(const [mode,viewport] of Object.entries(modes)){
  const p=await page(viewport,null);
  await check('login-'+mode,async()=>{
    assert.equal(await p.title(),'TEC-ARCHIVA | Gestión documental inteligente');
    const style=await p.evaluate(()=>{const css=getComputedStyle(document.documentElement);return {width:document.documentElement.scrollWidth,palette:['violet','indigo','blue','white','ink'].map(k=>css.getPropertyValue('--ta-'+k).trim().toUpperCase())};});
    assert.equal(style.width,viewport.width);
    assert.deepEqual(style.palette,['#6257DC','#4848B6','#29577E','#FFFFFF','#172033']);
    await shot(p,'login-'+mode);
    if(mode==='escritorio')await scan(p,'login',mode);
    return style;
  });
  await p.close();
  for(const role of roles){
    const view=await page(viewport,role);
    await check('menu-'+mode+'-'+role,async()=>{
      const identity=await view.evaluate(()=>pedir('/cuentas/yo'));
      const allowed=identity.pestanas;
      const menu=await view.locator('#menu button').evaluateAll(nodes=>nodes.map(n=>n.dataset.vista));
      assert.deepEqual([...menu].sort(),[...allowed].sort());
      const protectedReads=await view.evaluate(async()=>Object.fromEntries(await Promise.all(['/cuentas','/unidades/AC-CP-99881','/cargue/ver/AC-CP-99881','/consulta/unidades/AC-CP-99913'].map(async endpoint=>{
        const r=await fetch(API+endpoint,{headers:{Authorization:'Bearer '+PASE}});
        return [endpoint,{status:r.status,pdf:r.headers.get('content-type')?.startsWith('application/pdf')||false}];
      }))));
      assert.equal(protectedReads['/cuentas'].status,role==='administradora'?200:403);
      assert.equal(protectedReads['/cargue/ver/AC-CP-99881'].status,role==='entidad'?403:200);
      if(role!=='entidad')assert.equal(protectedReads['/cargue/ver/AC-CP-99881'].pdf,true);
      if(role==='entidad')assert.equal(protectedReads['/consulta/unidades/AC-CP-99913'].status,404);
      permissions.push({role,mode,menu,api:protectedReads});
    });
    const keys=await view.locator('#menu button').evaluateAll(nodes=>nodes.map(n=>n.dataset.vista));
    for(const key of keys){
      await check('view-'+mode+'-'+role+'-'+key,async()=>{
        const v=await open(view,key);
        const id=await v.getAttribute('id');
        assert.ok(await v.getByRole('heading',{level:2}).count()||await v.getByRole('heading',{level:1}).count());
        if(markers[key])assert.ok(await view.locator(markers[key]).count(),key);
        if(key==='cuentas')await view.waitForFunction(()=>document.querySelector('#taAccountStatus')?.textContent.includes('Página'));
        if(key==='inicio')await view.locator('#taIndicators[aria-busy=false]').waitFor();
        if(key==='avance')await view.locator('#metrosAvance .metro').first().waitFor();
        if(key==='proceso')await view.locator('#vCola[aria-busy=false]').waitFor();
        if(key==='localizacion')await view.locator('#taRecordsResults[aria-busy=false]').waitFor();
        if(key==='revision')await view.waitForFunction(()=>!document.getElementById('taReviewStatus').textContent.includes('Consultando'));
        const width=await view.evaluate(()=>document.documentElement.scrollWidth);
        const legacy=await v.evaluate(e=>[...e.querySelectorAll('h1,h2,h3,button,caption')].filter(n=>n.getClientRects().length&&/\bGEOLOGY\b/.test(n.textContent)).map(n=>n.textContent.trim().slice(0,100)));
        screens.push({role,mode,key,id,width,expected:viewport.width,visibleLegacyBrand:legacy});
        if(role==='administradora'&&['inicio','planeacion','cargue','revision','avance','cuentas','contrato'].includes(key))await shot(view,key+'-'+mode);
        if(role==='entidad'&&key==='consulta')await shot(view,key+'-'+mode);
        if(mode==='escritorio'&&(role==='administradora'||(role==='entidad'&&key==='consulta')))await scan(view,key,mode);
        assert.deepEqual(legacy,[]);
        assert.equal(width,viewport.width,'Desbordamiento de la página');
      });
    }
    await view.close();
  }
}
await check('help-mobile-dialog',async()=>{
  const p=await page(modes.movil,'equipo');
  try {
    const view=await open(p,'cargue');
    const trigger=view.getByRole('button',{name:/Qué hacer/});
    await trigger.click();
    const dialog=p.getByRole('dialog',{name:'Ayuda de la pantalla'});
    await dialog.waitFor();
    const inside=await dialog.evaluate(node=>node.contains(document.activeElement));
    assert.equal(inside,true);
    await shot(p,'ayuda-movil');
    await scan(p,'ayuda','movil');
    await p.keyboard.press('Escape');
    await dialog.waitFor({state:'hidden'});
    assert.equal(await trigger.evaluate(node=>node===document.activeElement),true);
  }finally{await p.close();}
});
await check('mobile-menu-direct',async()=>{
  for(let i=0;i<3;i++){
    const p=await page(modes.movil,'administradora');
    try{
      const toggle=p.locator('#taMenuToggle');
      await toggle.focus();
      await p.keyboard.press('Enter');
      const opened=await p.evaluate(snapshot);
      assert.equal(opened.expanded,'true');
      assert.equal(opened.focus,'inicio');
      await p.keyboard.press('Escape');
      const closed=await p.evaluate(snapshot);
      events.push({case:'direct-mobile',run:i,opened,closed});
      assert.equal(closed.expanded,'false');
      assert.equal(closed.focus,'taMenuToggle');
    }finally{await p.close();}
  }
});
await check('mobile-menu-viewport-diagnostic',async()=>{
  const p=await page(modes.escritorio,'administradora');
  try{
    await p.evaluate(()=>{
      window.mobileTrace=[];
      const toggle=document.getElementById('taMenuToggle');
      const mm=matchMedia('(max-width:850px)');
      const log=type=>window.mobileTrace.push({type,time:Math.round(performance.now()),width:innerWidth,compact:mm.matches,expanded:toggle.getAttribute('aria-expanded'),focus:document.activeElement?.id||document.activeElement?.dataset?.vista});
      mm.addEventListener('change',()=>log('media-change'));
      document.addEventListener('focusin',()=>log('focusin'));
      toggle.addEventListener('click',()=>log('click'));
      new MutationObserver(()=>log('expanded-mutation')).observe(toggle,{attributes:true,attributeFilter:['aria-expanded']});
    });
    for(let run=0;run<6;run++){
      await p.setViewportSize(modes.escritorio);
      await p.waitForFunction(()=>window.mobileTrace.at(-1)?.compact===false || !matchMedia('(max-width:850px)').matches);
      await p.evaluate(()=>{window.mobileTrace=[];});
      await p.setViewportSize(modes.movil);
      const toggle=p.locator('#taMenuToggle');
      await toggle.focus();
      await p.keyboard.press('Enter');
      const immediate=await p.evaluate(snapshot);
      await p.waitForFunction(()=>window.mobileTrace.some(e=>e.type==='media-change'&&e.compact));
      const stable=await p.evaluate(snapshot);
      const trace=await p.evaluate(()=>window.mobileTrace);
      events.push({case:'resize-menu',run,immediate,stable,trace});
      if(stable.expanded==='true'&&stable.focus==='inicio')await p.keyboard.press('Escape');
      else if(stable.expanded==='true')await toggle.click();
    }
    // Force the click at the resize boundary and observe the real media event.
    await p.setViewportSize(modes.escritorio);
    await p.waitForFunction(()=>window.mobileTrace.at(-1)?.compact===false || !matchMedia('(max-width:850px)').matches);
    await p.evaluate(()=>{
      window.mobileTrace=[];
      window.resizeClick=null;
      window.addEventListener('resize',()=>{
        if(!matchMedia('(max-width:850px)').matches)return;
        const toggle=document.getElementById('taMenuToggle');
        toggle.click();
        window.resizeClick={expanded:toggle.getAttribute('aria-expanded'),focus:document.activeElement?.dataset?.vista};
      },{once:true});
    });
    await p.setViewportSize(modes.movil);
    await p.waitForFunction(()=>window.mobileTrace.some(e=>e.type==='media-change'&&e.compact));
    events.push({case:'resize-boundary-click',after:await p.evaluate(snapshot),before:await p.evaluate(()=>window.resizeClick),trace:await p.evaluate(()=>window.mobileTrace)});
  }finally{await p.close();}
  return {samples:6,controlledBoundary:1};
});
await check('account-layout-async-diagnostic',async()=>{
  const p=await page(modes.escritorio,'administradora');
  try{
    let interceptedResolve,release;
    const intercepted=new Promise(r=>interceptedResolve=r);
    const gate=new Promise(r=>release=r);
    await p.route('**/cuentas',async r=>{interceptedResolve();await gate;await r.continue();});
    const navigation=open(p,'cuentas');
    await intercepted;
    await p.setViewportSize({width:320,height:700});
    const measure=()=>p.locator('#cuTabla input[type=checkbox]').evaluateAll(nodes=>nodes.map(e=>[e.getBoundingClientRect().width,e.getBoundingClientRect().height]));
    const before=await measure();
    release();
    await navigation;
    await p.waitForFunction(()=>document.querySelector('#taAccountStatus')?.textContent.includes('Página'));
    const after=await measure();
    events.push({case:'account-load',width:320,before,after});
    assert.equal(before.length,0);
    assert.ok(after.length>0 && after.every(([w,h])=>w>=24&&h>=24));
    await p.unroute('**/cuentas');
    for(let run=0;run<4;run++){
      await p.setViewportSize(modes.escritorio);
      await open(p,'localizacion');
      await open(p,'cuentas');
      await p.setViewportSize({width:320,height:256});
      const immediate=await measure();
      await p.waitForFunction(()=>document.querySelector('#taAccountStatus')?.textContent.includes('Página'));
      const stable=await measure();
      events.push({case:'account-revisit',run,width:320,immediate,stable});
      assert.ok(stable.length>0 && stable.every(([w,h])=>w>=24&&h>=24));
    }
  }finally{await p.close();}
});
await check('no-browser-errors',()=>assert.deepEqual(errors,[]));
await browser.close();
const result={tests,passed:tests.filter(t=>t.status==='PASS').length,failed:tests.filter(t=>t.status==='FAIL').length,screens,permissions,events,scans};
await fs.writeFile(path.join(out,'cross13f.json'),JSON.stringify(result,null,2));
console.log(JSON.stringify({passed:result.passed,failed:result.failed,scans:scans.length,failures:tests.filter(t=>t.status==='FAIL')}));
process.exitCode=result.failed?1:0;
