/* Candidate 12F: navigation and accessibility only. No document or archival writes. */
(() => {
'use strict';
const $=id=>document.getElementById(id);
const css=document.createElement('style');css.textContent=`button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,a:focus-visible,[tabindex]:focus-visible{outline:3px solid #155aab;outline-offset:3px}.salto12f{position:fixed;left:8px;top:-100px;z-index:100;background:white;padding:12px}.salto12f:focus{top:8px}.sr12f{position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap}button:disabled{cursor:not-allowed}.vista[aria-busy=true]{border-top:3px solid #155aab}caption{text-align:left;font-weight:bold;padding:6px}#fichaLectura12f{max-width:1180px;margin:20px auto;padding:20px}#fichaLectura12f dt{font-weight:bold}#fichaLectura12f dd{margin:0 0 12px;overflow-wrap:anywhere}nav{scrollbar-width:auto}`;document.head.append(css);
const skip=document.createElement('a');skip.className='salto12f';skip.href='#contenido12f';skip.textContent='Saltar al contenido principal';document.body.prepend(skip);
const status=document.createElement('div');status.id='estado12f';status.role='status';status.setAttribute('aria-live','polite');status.className='sr12f';document.body.append(status);
const main=document.createElement('span');main.id='contenido12f';main.tabIndex=-1;$('pApp').prepend(main);
skip.onclick=e=>{e.preventDefault();(document.querySelector('.vista:not(.oculto) h2')||main).focus();};
function announce(text){status.textContent=text;}
let context=null,requestNumber=0;
const card=document.createElement('section');card.id='fichaLectura12f';card.className='caja ta-record-card oculto';card.setAttribute('aria-label','Ficha de expediente de solo lectura');$('taMain').append(card);
window.volverFicha12f=function(){++requestNumber;card.classList.add('oculto');TEC.restaurarRuta();if(!context)return;context.view?.classList.remove('oculto');context.focus?.focus();window.scrollTo(0,context.scroll);context=null;};
window.verFichaLectura=async function(code){
 if(!SESION||SESION.es_entidad){announce('Acceso no autorizado a esta ficha. Utilice Consulta.');return;}
 const view=document.querySelector('.vista:not(.oculto)');
 if(!context)context={view,focus:document.activeElement,scroll:window.scrollY};
 document.querySelectorAll('.vista').forEach(v=>v.classList.add('oculto'));TEC.rutaFicha();
 card.classList.remove('oculto');
 card.innerHTML='<button class="btn2" onclick="volverFicha12f()">Volver al listado</button><h2 tabindex="-1">Ficha de expediente</h2><p role="status">Cargando ficha…</p>';card.setAttribute('aria-busy','true');card.querySelector('h2').focus();
 const serial=++requestNumber;
 try{
  const f=await pedir('/unidades/'+encodeURIComponent(code));
  // Both endpoints retain their own authentication/authorization. No synchronization GET.
  const trace=await pedir('/unidades/'+encodeURIComponent(code)+'/trazabilidad');
  if(serial!==requestNumber)return;
  const entries=[['Estado',f.estado],['Título',f.titulo||f.nombre_expediente],['Período',f.periodo],['Subserie',f.subserie],['Caja de trabajo',f.caja_trabajo],['Caja definitiva',f.caja_definitiva],['Folios',f.folios]];
  card.innerHTML='<button class="btn2" onclick="volverFicha12f()">Volver al listado</button><h2 tabindex="-1">'+esc(f.codigo_carpeta)+'</h2><p>Solo lectura. No permite editar, revisar, aprobar ni publicar.</p><dl>'+entries.map(([k,v])=>'<dt>'+esc(k)+'</dt><dd>'+esc(v??'Sin información')+'</dd>').join('')+'</dl>';
  if(f.documento?.disponibles){const b=document.createElement('button');b.className='btn2';b.textContent='Consultar documento autorizado';b.onclick=()=>verDocumento(code);const documents=document.createElement('section');documents.className='ta-document-card';const title=document.createElement('h3');title.textContent='Documentos asociados';const info=document.createElement('p');info.textContent=f.documento.disponibles+' de '+f.documento.cargados+' disponibles';documents.append(title,info,b);card.append(documents);}
  const description=document.createElement('section');const title=document.createElement('h3');title.textContent='Metadatos ISAD(G) — solo lectura';description.append(title);const metadata=document.createElement('dl');metadata.id='metadatos12f';for(const field of (f.isadg||[])){const term=document.createElement('dt');term.textContent=[field.numeral,field.etiqueta].filter(Boolean).join(' · ');const value=document.createElement('dd');value.textContent=field.valor===null||field.valor===undefined||field.valor===''?'Sin información':String(field.valor);metadata.append(term,value);}description.append(metadata);card.append(description);
  const heading=document.createElement('h3');heading.textContent='Hoja de control';card.append(heading);
  const control=document.createElement('p');control.textContent=(f.tramites||[]).map(t=>[t.no_item,t.fecha||'Sin fecha',t.tipo_documental,t.folio_desde+'–'+t.folio_hasta].join(' · ')).join('; ')||'Sin trámites registrados';card.append(control);
  const h=document.createElement('h3');h.textContent='Trazabilidad';card.append(h);
  const list=document.createElement('ul');list.className='ta-record-history';for(const t of trace){const item=document.createElement('li');item.textContent=[t.fecha,t.accion,t.de,t.a,t.usuario,t.motivo].filter(Boolean).join(' · ');list.append(item);}card.append(list);
  if(!trace.length){const p=document.createElement('p');p.textContent='Sin movimientos registrados';card.append(p);}
  card.querySelector('h2').focus();announce('Ficha cargada en modo de solo lectura.');
 }catch(e){if(serial!==requestNumber)return;const error=document.createElement('p');error.role='alert';error.textContent='No se pudo consultar la ficha: '+e.message;card.append(error);}
 finally{if(serial===requestNumber)card.setAttribute('aria-busy','false');}
};
const originalView=mostrarVista;mostrarVista=function(v,b){++requestNumber;card.classList.add('oculto');context=null;originalView(v,b);document.querySelectorAll('nav button').forEach(x=>{if(x===b)x.setAttribute('aria-current','page');else x.removeAttribute('aria-current');});const h=$(v.id)?.querySelector('h2,h1');if(h){h.tabIndex=-1;h.focus();}};
const oldProcess=cargarProceso;cargarProceso=async function(...args){const panel=$('vCola');panel.setAttribute('aria-busy','true');announce('Actualizando proceso…');try{return await oldProcess(...args);}finally{panel.setAttribute('aria-busy','false');announce('Actualización de proceso finalizada.');}};
for(const v of VISTAS){if(v.al===oldProcess)v.al=(...a)=>cargarProceso(...a);}
let modalTrigger=null;
function openedModal(){modalTrigger=document.activeElement;const m=$('modal');m.setAttribute('role','dialog');m.setAttribute('aria-modal','true');m.setAttribute('aria-label','Ayuda de la pantalla');$('pApp').inert=true;m.querySelector('button')?.focus();}
const oldHelp=ayuda;ayuda=function(...a){oldHelp(...a);openedModal();};
cerrarModal=function(){$('modal').classList.add('oculto');$('pApp').inert=false;modalTrigger?.focus();};
$('modal').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();cerrarModal();}if(e.key==='Tab'){const items=[...$('modal').querySelectorAll('button,a[href],input,select,textarea,[tabindex="0"]')].filter(x=>!x.disabled&&x.getClientRects().length);if(!items.length)return;const first=items[0],last=items.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}});
const labels={buscarProceso:'Buscar carpeta en Proceso',buscarCodigo:'Código de carpeta',cuNombre:'Nombre de la cuenta',cuCorreo:'Correo de la cuenta',cuCargo:'Cargo de la cuenta',cuRol:'Rol de la cuenta',dsDesde:'Fecha inicial de descargas',dsHasta:'Fecha final de descargas',dsPersona:'Persona de las descargas'};
for(const [id,name] of Object.entries(labels)){const e=$(id);if(!e)continue;let lab=e.parentElement.querySelector('label');if(lab&&!lab.htmlFor)lab.htmlFor=id;else e.setAttribute('aria-label',name);}
for(const id of ['errIngreso','errCambio','resultadoBusqueda']){$(id)?.setAttribute('aria-live','assertive');$(id)?.setAttribute('aria-atomic','true');}
for(const id of ['correo','clave'])$(id).setAttribute('aria-describedby','errIngreso');
const oldEnter=entrar;entrar=async function(...a){for(const id of ['correo','clave'])$(id).removeAttribute('aria-invalid');await oldEnter(...a);if($('errIngreso').textContent){for(const id of ['correo','clave'])$(id).setAttribute('aria-invalid','true');($('correo').value?$('clave'):$('correo')).focus();}};
$('btnIngresar').removeEventListener('click',oldEnter);$('btnIngresar').addEventListener('click',()=>entrar());
function enhance(){
 for(const t of document.querySelectorAll('table')){if(!t.caption){const c=t.createCaption();c.textContent=t.closest('.vista')?.querySelector('h2')?.textContent||'Datos del expediente';}for(const th of t.querySelectorAll('th')){if(!th.hasAttribute('scope'))th.scope=th.closest('thead')?'col':'row';if(!th.textContent.trim())th.textContent='Acciones';}}
 for(const b of document.querySelectorAll('button[onclick]')){const handler=b.getAttribute('onclick')||'';if(/levantarHoja\(|generarIsadg\(/.test(handler)&&SESION&&!SESION.lectura_ia_disponible){b.disabled=true;b.title='No disponible: proveedores externos deshabilitados';b.setAttribute('aria-describedby','motivoIA12f');}}
 const active=document.querySelector('nav button.act');if(active&&!active.hasAttribute('aria-current'))active.setAttribute('aria-current','page');
}
// 12H: WCAG 2.5.8 targets in Cuentas only; no event, value or permission changes.
const targets12h=document.createElement('style');targets12h.textContent=`#vCuentas input[type=checkbox]{box-sizing:border-box;width:24px;height:24px;min-width:24px;min-height:24px;vertical-align:middle;margin:6px}`;document.head.append(targets12h);
const reason=document.createElement('p');reason.id='motivoIA12f';reason.textContent='Lectura y revisión IA no disponibles: proveedores externos deshabilitados. El estado En cola no certifica ni invalida el procesamiento técnico PDF/A.';$('vCola').prepend(reason);
let pending=false;new MutationObserver(()=>{if(pending)return;pending=true;queueMicrotask(()=>{pending=false;enhance();});}).observe(document.body,{subtree:true,childList:true});enhance();
})();
