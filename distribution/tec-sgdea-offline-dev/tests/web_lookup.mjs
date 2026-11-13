import fs from 'node:fs';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import path from 'node:path';
const [root, run, playwrightBase] = process.argv.slice(2);
const require=createRequire(playwrightBase);
const {chromium}=require('playwright');
const resultPath=path.join(run,'result.json');
const result=JSON.parse(fs.readFileSync(resultPath));
const [url,mail,pass]=fs.readFileSync(path.join(root,'acceso-local.txt'),'utf8').trim().split(/\r?\n/);
const browser=await chromium.launch({headless:true});
try {
 const p=await browser.newPage({viewport:{width:1440,height:1000}});
 await p.goto(process.env.TEC_SGDEA_TEST_URL ? process.env.TEC_SGDEA_TEST_URL+'/app' : url);
 assert.equal(await p.title(),'TEC-SGDEA | Gestión documental inteligente');
 const colors=await p.evaluate(()=>['violet','indigo','blue','white','ink'].map(k=>getComputedStyle(document.documentElement).getPropertyValue('--ta-'+k).trim().toUpperCase()));
 assert.deepEqual(colors,['#6257DC','#4848B6','#29577E','#FFFFFF','#172033']);
 await p.locator('#correo').fill(mail.slice(8));
 await p.locator('#clave').fill(pass.slice(12));
 await p.locator('#btnIngresar').click();
 await p.locator('#pApp').waitFor({state:'visible'});
 await p.locator('#menu [data-vista=localizacion]').click();
 const input=p.locator('#buscarCodigo');
 await input.fill(result.code);
 const loaded=p.waitForResponse(r=>r.url().endsWith('/unidades/'+result.code)&&r.request().method()==='GET');
 await input.press('Enter');
 const response=await loaded;
 assert.equal(response.status(),200);
 if(result.expected_sheet) assert.equal((await response.json()).nombre_expediente,result.expected_sheet);
 await p.locator('#resultadoBusqueda').getByRole('button',{name:'Ver la ficha completa'}).click();
 await p.locator('#fichaLectura12f').getByText(result.code,{exact:false}).first().waitFor({state:'visible',timeout:6000});
 result.browser_ui=true;
 result.institutional_palette_verified=true;
 fs.writeFileSync(resultPath,JSON.stringify(result,null,2));
 console.log('WEB_UI_PASS',result.code);
} finally {await browser.close();}


