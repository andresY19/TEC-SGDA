import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const b=path.dirname(fileURLToPath(import.meta.url));
const root=process.cwd();
const before=path.join(root,'distribution/tec-archiva-13e-a02/geology/interfaz/tec-archiva.js');
const after=path.join(b,'context/geology/interfaz/tec-archiva.js');
const browser=await chromium.launch({headless:true});
const cases=[];
async function sample(source){
  const p=await browser.newPage({viewport:{width:1440,height:900}});
  try{
    await p.setContent('<style>@media(max-width:850px){aside:not(.is-open){display:none}} @media(min-width:851px){#taMenuToggle{display:none}}</style><button id="taMenuToggle" aria-expanded="false">Abrir</button><aside id="taSidebar"><button id="first">Dashboard</button><button id="second">Cargue</button></aside><button id="taRefresh">Actualizar</button>');
    await p.addScriptTag({path:source});
    await p.evaluate(()=>{
      const media=matchMedia('(max-width:850px)');
      const toggle=document.getElementById('taMenuToggle');
      window.events=[];
      const record=type=>window.events.push({type,compact:media.matches,expanded:toggle.getAttribute('aria-expanded'),focus:document.activeElement.id||document.activeElement.tagName});
      window.addEventListener('resize',()=>{if(media.matches){toggle.click();record('opened-before-media');}},{once:true});
      media.addEventListener('change',()=>record('media'));
    });
    await p.setViewportSize({width:390,height:844});
    await p.waitForFunction(()=>window.events.some(e=>e.type==='media'&&e.compact));
    return await p.evaluate(()=>({events:window.events,expanded:document.getElementById('taMenuToggle').getAttribute('aria-expanded'),focus:document.activeElement.id||document.activeElement.tagName}));
  }finally{await p.close();}
}
try {
  const old=await sample(before);
  const stable=run=>run.events[0]?.type==='opened-before-media'&&run.events[0].expanded==='true'&&run.expanded==='true'&&run.focus==='first';
  assert.equal(old.events[0]?.type,'opened-before-media');
  assert.equal(old.events[0].expanded,'true');
  assert.equal(old.events[0].focus,'first');
  assert.equal(old.expanded,'false');
  assert.equal(old.focus,'BODY');
  assert.throws(()=>assert.ok(stable(old)));
  cases.push({version:'13E',expected:'FAIL',observed:'FAIL',...old});
  for(let run=0;run<10;run++){
    const candidate=await sample(after);
    cases.push({version:'13G',run,expected:'PASS',observed:stable(candidate)?'PASS':'FAIL',...candidate});
  }
  assert.ok(cases.slice(1).every(x=>x.observed==='PASS'));
}finally{
  await browser.close();
  await fs.writeFile(path.join(b,'results/menu-reproduction14a.json'),JSON.stringify(cases,null,2));
}
console.log('Same assertion: 13E reproduced the defect; 13G held focus and menu in all ten trials.');
