/* Shared records UI. Server routes remain the authority for every document read. */
const REGISTROS = (() => {
  const get = id => document.getElementById(id);
  const collator = new Intl.Collator('es', {numeric:true, sensitivity:'base'});
  const pageSize = 10;
  const text = value => value == null || value === '' ? '—' : String(value);
  const fold = value => String(value ?? '').normalize('NFD').replace(/\p{Diacritic}/gu,'').toLocaleLowerCase('es');
  function node(tag, value, className) {
    const el = document.createElement(tag);
    if (value != null) el.textContent = value;
    if (className) el.className = className;
    return el;
  }
  function action(label, fn, primary = false) {
    const button = node('button',label,primary ? 'btn' : 'btn2');
    button.type = 'button';
    button.addEventListener('click',fn);
    return button;
  }
  function badge(label, tone = '') {
    return node('span',text(label),['pill',tone].filter(Boolean).join(' '));
  }

  function DataTable(host, title, columns, grupos = null) {
    const status = node('p',null,'ta-status ta-results-message');
    status.setAttribute('role','status');
    const region = node('div',null,'ta-data-scroll');
    region.tabIndex = 0;
    region.setAttribute('role','region');
    region.setAttribute('aria-label',title);
    const table = node('table',null,'ta-data-table');
    table.createCaption().textContent = title;
    const headings = table.createTHead().insertRow();
    const body = table.createTBody();
    const footer = node('div',null,'ta-pagination');
    const summary = node('p');
    const controls = node('div',null,'ta-record-actions');
    const previous = action('Anterior',() => {page--; render();});
    const next = action('Siguiente',() => {page++; render();});
    controls.append(previous,next);
    footer.append(summary,controls);
    region.append(table);
    const message = node('div');
    host.replaceChildren(status,message,region,footer);
    let rows = [];
    let page = 0;
    let sortIndex = -1;
    let direction = 1;
    columns.forEach((column,index) => {
      const th = node('th');
      th.scope = 'col';
      if (column.sort) {
        const sort = action(column.label,() => {
          direction = sortIndex === index ? -direction : 1;
          sortIndex = index;
          page = 0;
          render();
        });
        sort.setAttribute('aria-label','Ordenar por '+column.label);
        th.append(sort);
      } else th.textContent = column.label;
      headings.append(th);
    });

    function render() {
      const pages = Math.max(1,Math.ceil(rows.length/pageSize));
      page = Math.min(Math.max(0,page),pages-1);
      const ordenar = items => sortIndex < 0 ? items : [...items].sort((a,b) =>
        direction * collator.compare(text(columns[sortIndex].sort(a)),text(columns[sortIndex].sort(b))));
      const visibles = (grupos ? rows : ordenar(rows)).slice(page*pageSize,(page+1)*pageSize);
      Array.from(headings.cells).forEach((th,index) => {
        if (index === sortIndex) th.setAttribute('aria-sort',direction > 0 ? 'ascending' : 'descending');
        else th.removeAttribute('aria-sort');
      });
      const fila = item => {
        const tr = node('tr');
        for (const column of columns) {
          const cell = node('td');
          const value = column.cell(item);
          if (value instanceof Node) cell.append(value);
          else cell.textContent = text(value);
          tr.append(cell);
        }
        return tr;
      };
      body.replaceChildren(...(grupos ? visibles.flatMap(grupo =>
        [grupos.encabezado(grupo, columns.length), ...ordenar(grupo.carpetas).map(fila)]
      ) : visibles.map(fila)));
      previous.disabled = page === 0;
      next.disabled = page + 1 >= pages;
      summary.textContent = 'Página '+(page+1)+' de '+pages+' · '+rows.length+(grupos ? ' cajas' : ' resultados');
      status.textContent = summary.textContent;
      region.hidden = footer.hidden = rows.length === 0;
    }

    function clear() {
      rows = [];
      page = 0;
      body.replaceChildren();
      region.hidden = footer.hidden = true;
      message.replaceChildren();
      status.textContent = '';
    }
    clear();
    return {
      loading() {
        clear();
        host.setAttribute('aria-busy','true');
        status.textContent = 'Cargando resultados…';
        const skeleton = node('div',null,'ta-skeleton ta-table-skeleton');
        skeleton.setAttribute('aria-hidden','true');
        message.append(skeleton);
      },
      error(error) {
        clear();
        host.setAttribute('aria-busy','false');
        const alert = node('p',error.message,'aviso mal');
        alert.setAttribute('role','alert');
        message.append(alert);
      },
      results(items,emptyText) {
        clear();
        host.setAttribute('aria-busy','false');
        rows = items;
        if (rows.length) render();
        else {
          status.textContent = '0 resultados';
          message.append(node('p',emptyText,'ta-empty'));
        }
      }
    };
  }
  const field = (label,key) => ({label,sort:row=>row[key],cell:row=>row[key]});
  const dateRange = row => [row.fecha_inicial,row.fecha_final].filter(Boolean).join(' – ');
  const dateColumn = {label:'Fechas',sort:dateRange,cell:dateRange};
  const can = key => SESION?.pestanas?.includes(key);
  function encabezadoCaja(caja, columnas) {
    const fila = node('tr');
    const celda = node('td');
    celda.colSpan = columnas;
    celda.append(node('strong', caja.caja+' · '+caja.total+(caja.total === 1 ? ' carpeta' : ' carpetas')));
    if (caja.mixta) {
      const periodos = (caja.periodos || []).join(', ');
      celda.append(' ', badge(periodos ? 'Caja mixta · '+periodos : 'Caja mixta', 'rev'));
    }
    fila.append(celda);
    return fila;
  }
  const inventoryTable = DataTable(get('plCajas'),'Carpetas del inventario de origen',[
    field('Carpeta','carpeta'),field('Caja de origen','caja_origen'),field('Folios','folios'),dateColumn,
    {label:'Periodo calculado',sort:row=>row.periodo,cell:row=>[row.periodo,row.origen_periodo].filter(Boolean).join(' · ')},
    field('Periodo del inventario','periodo_inventario'),
    {label:'Etapa',sort:row=>row.etapa_rotulo,cell:row=>badge(row.etapa_rotulo)},
    {label:'Alertas',cell:row=>(row.banderas||[]).map(key=>PL_BANDERAS[key]||key).join(' · ')},
    {label:'Acciones',cell:row=>can('revision') ? action('Abrir expediente',()=>irAVerFicha(row.carpeta)) : '—'}
  ], {encabezado: encabezadoCaja});
  const recordsTable = DataTable(get('taRecordsResults'),'Expedientes',[
    field('Carpeta','codigo_carpeta'),{label:'Estado',sort:row=>row.estado,cell:row=>badge(row.estado)},
    field('Responsable','responsable'),field('Fechas','fechas_extremas'),field('Folios','folios'),
    {label:'Documentos disponibles',sort:row=>row.documento?.disponibles,cell:row=>row.documento?.disponibles},
    {label:'Acciones',cell:row=>action('Abrir ficha',()=>verFichaLectura(row.codigo_carpeta))}
  ]);
  const publishedTable = DataTable(get('taPublishedResults'),'Unidades publicadas',[
    field('Carpeta','carpeta'),field('Unidad documental','nombre'),field('Periodo','periodo'),dateColumn,
    field('Folios','folios'),field('Caja definitiva','caja_definitiva'),field('Código de referencia','codigo_referencia'),
    {label:'Etapa',sort:row=>row.etapa,cell:row=>badge(row.etapa,row.en_inventario?'apr':row.tiene_descripcion?'rev':'')},
    {label:'Acciones',cell:row=>{
      const actions=node('div',null,'ta-record-actions');
      actions.append(action('Ver ficha publicada',event=>publishedDetail(row.carpeta,event.currentTarget)));
      appendPublishedActions(actions,row);
      return actions;
    }}
  ]);

  let inventorySerial=0, recordsSerial=0, publishedSerial=0, detailSerial=0;
  let inventoryReady=false, recordsReady=false;
  let inventoryBoxes=[];
  function filterInventory() {
    const period=get('taInventoryPeriod').value;
    const boxes = period ? inventoryBoxes.map(box => ({
      ...box, carpetas: box.carpetas.filter(row => row.periodo === period)
    })).filter(box => box.carpetas.length) : inventoryBoxes;
    inventoryTable.results(boxes,'No hay carpetas que coincidan con los filtros.');
  }
  async function inventario() {
    if (!can('planeacion')) return;
    const serial=++inventorySerial;
    inventoryTable.loading();
    inventoryBoxes=[];
    try {
      const r=await pedir('/planeacion/cajas?buscar='+encodeURIComponent(get('plBuscar').value.trim()));
      if (serial!==inventorySerial) return;
      inventoryBoxes=r.cajas||[];
      const select=get('taInventoryPeriod');
      const selected=select.value;
      const periods=[...new Set(inventoryBoxes.flatMap(box=>box.carpetas.map(row=>row.periodo)).filter(Boolean))].sort(collator.compare);
      select.replaceChildren(new Option('Todos',''),...periods.map(period=>new Option(period,period)));
      select.value=periods.includes(selected)?selected:'';
      inventoryReady=true;
      filterInventory();
    } catch (error) { if (serial===inventorySerial) inventoryTable.error(error); }
  }
  async function expedientes() {
    if (!can('localizacion') || SESION.es_entidad) return;
    const serial=++recordsSerial;
    recordsTable.loading();
    const params=new URLSearchParams({limite:'1000'});
    const state=get('taRecordState').value;
    const query=fold(get('taRecordQuery').value.trim());
    if (state) params.set('estado',state);
    try {
      const rows=await pedir('/unidades?'+params);
      if (serial!==recordsSerial) return;
      recordsReady=true;
      recordsTable.results(rows.filter(row=>[row.codigo_carpeta,row.responsable].some(value=>fold(value).includes(query))),'No hay expedientes que coincidan con los filtros.');
    } catch (error) { if (serial===recordsSerial) recordsTable.error(error); }
  }
  function closePublished(restore) {
    ++detailSerial;
    get('taPublishedDetail').hidden=true;
    get('taPublishedDetail').replaceChildren();
    get('taPublished').hidden=false;
    TEC.restaurarRuta();
    if (restore?.isConnected) restore.focus();
  }
  async function publicadas() {
    if (!can('consulta')) return;
    const serial=++publishedSerial;
    closePublished();
    publishedTable.loading();
    const params=new URLSearchParams();
    for (const [id,key] of [['coBuscar','buscar'],['coCaja','caja'],['coPeriodo','periodo']]) {
      const value=get(id).value.trim();
      if (value) params.set(key,value);
    }
    try {
      const rows=await pedir('/consulta/unidades?'+params);
      if (serial===publishedSerial) publishedTable.results(rows,'No hay unidades publicadas que cumplan esa búsqueda.');
    } catch (error) { if (serial===publishedSerial) publishedTable.error(error); }
  }
  function appendPublishedActions(host,ficha) {
    const permissions=CONSULTA.habilitado;
    if (permissions.hojas_control && ficha.tiene_hoja) {
      host.append(action('Ver hoja',()=>verHojaConsulta(ficha.carpeta)));
      host.append(action('Descargar',()=>descargarConsulta('hoja-de-control/'+encodeURIComponent(ficha.carpeta))));
    }
    if (permissions.imagenes && ficha.partes_digitalizadas) host.append(action('Ver imágenes',()=>verImagenes(ficha.carpeta)));
  }
  async function publishedDetail(code,trigger) {
    if (!can('consulta')) return;
    const serial=++detailSerial;
    const card=get('taPublishedDetail');
    const heading=node('h2','Ficha publicada');
    heading.tabIndex=-1;
    const back=action('Volver a resultados',()=>closePublished(trigger));
    const busy=node('p','Cargando ficha…','ta-status');
    busy.setAttribute('role','status');
    card.classList.add('ta-record-card');
    card.replaceChildren(back,heading,busy);
    get('taPublished').hidden=true;
    card.hidden=false;
    TEC.rutaFicha();
    heading.focus();
    try {
      const f=await pedir('/consulta/unidades/'+encodeURIComponent(code));
      if (serial!==detailSerial) return;
      heading.textContent=f.carpeta;
      const fields=node('dl');
      for (const [label,value] of [['Nombre',f.nombre],['Etapa',f.etapa],['Periodo',f.periodo],
        ['Serie',f.serie],['Subserie',f.subserie],['Fechas',dateRange(f)],['Folios',f.folios],
        ['Caja de origen',f.caja_origen],['Caja definitiva',f.caja_definitiva],['Posición en caja',f.carpeta_en_caja],
        ['Código de referencia',f.codigo_referencia]]) {
        fields.append(node('dt',label),node('dd',text(value)));
      }
      const docs=node('section',null,'ta-document-card');
      const actions=node('div',null,'ta-record-actions');
      appendPublishedActions(actions,f);
      docs.append(node('h3','Documentos publicados'),actions);
      if (!actions.children.length) docs.append(node('p','Sin acciones documentales habilitadas para esta unidad.','ta-muted'));
      busy.remove();
      card.append(fields,docs);
    } catch (error) {
      if (serial!==detailSerial) return;
      const alert=node('p',error.message,'aviso mal');
      alert.setAttribute('role','alert');
      busy.replaceWith(alert);
    }
  }

  get('taRecordState').append(...ESTADOS.map(state=>new Option(state,state)));
  get('taInventoryFilters').addEventListener('submit',event=>{event.preventDefault();inventario();});
  get('taInventoryPeriod').addEventListener('change',filterInventory);
  get('taRecordsFilters').addEventListener('submit',event=>{event.preventDefault();expedientes();});
  get('resultadoBusqueda').addEventListener('click',event=>{
    const button = event.target.closest('button');
    const match = button?.getAttribute('onclick')?.match(/^verFichaLectura\('((?:AC-CP-)[0-9]+)'\)$/);
    if (!match) return;
    event.stopPropagation();
    REGISTROS.abrirFichaLocalizada(match[1]);
  },true);
  return {
    inventario,publicadas,
    abrirFichaLocalizada(carpeta) {
      if (!can('localizacion') || SESION.es_entidad) return;
      if (SESION.rol === 'consulta' || !can('revision')) return verFichaLectura(carpeta);
      return irAVerFicha(carpeta);
    },
    inventarioInicial() { if (!inventoryReady) inventario(); },
    expedientesInicial() { if (!recordsReady) expedientes(); },
    cambioVista() { if (!get('taPublishedDetail').hidden) closePublished(); }
  };
})();
