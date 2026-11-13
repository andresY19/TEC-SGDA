import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import fs from 'node:fs';
const [modulePath, output] = process.argv.slice(2);
const {chromium} = createRequire(modulePath)('playwright');
const url = 'https://demo-sgdea.innovationsapps.cloud';
const browser = await chromium.launch();
const report = [];
try {
  for (const [label, viewport] of [['desktop',{width:1440,height:1000}],['movil',{width:390,height:844}]]) {
    const page = await browser.newPage({viewport});
    await page.goto(url+'/app');
    assert.match(await page.title(),/TEC-SGDEA/);
    if(label==='desktop') await page.screenshot({path:output+'/login.png'});
    await page.locator('#correo').fill(process.env.SGDEA_TEST_USER);
    await page.locator('#clave').fill(process.env.SGDEA_TEST_PASS);
    await page.locator('#btnIngresar').click();
    await page.locator('#pApp').waitFor({state:'visible'});
    await page.locator('#taIndicatorsTitle').waitFor({state:'visible'});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.screenshot({path:output+'/dashboard-'+label+'.png'});
    const modules = [];
    if(label==='desktop'){
      for(const view of ['localizacion','cargue','digitalizacion','revision','cuentas','produccion']){
        const button=page.locator('#menu [data-vista="'+view+'"]');
        if(await button.count() && await button.isVisible()){
          await button.click();
          modules.push(view);
        }
      }
      await page.locator('#menu [data-vista=localizacion]').click();
      const input=page.locator('#buscarCodigo');
      await input.fill('AC-CP-98002');
      const loaded=page.waitForResponse(r=>r.url().endsWith('/unidades/AC-CP-98002'));
      await input.press('Enter');
      assert.equal((await loaded).status(),200);
      await page.locator('#resultadoBusqueda').getByRole('button',{name:'Ver la ficha completa'}).click();
      await page.locator('#fichaLectura12f').getByText('AC-CP-98002',{exact:false}).first().waitFor();
      await page.screenshot({path:output+'/expediente.png'});
    }
    report.push({label, login:true,dashboard:true,modules});
    await page.close();
  }
  fs.writeFileSync(output+'/web.json',JSON.stringify(report,null,2));
} finally { await browser.close(); }
