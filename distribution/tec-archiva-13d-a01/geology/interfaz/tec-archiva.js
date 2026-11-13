/* Presentation layer for the existing GEOLOGY views and read endpoints. */
const TEC = (() => {
  const get = id => document.getElementById(id);
  const sidebar = get('taSidebar');
  const toggle = get('taMenuToggle');
  const compact = matchMedia('(max-width:850px)');
  const groups = {
    inicio:'Dashboard', planeacion:'Inventarios', localizacion:'Expedientes',
    reubicacion:'Expedientes', hojas:'Expedientes', cargue:'Digitalización',
    proceso:'Digitalización', revision:'Revisión', calidad:'Revisión',
    consulta:'Consulta', instrumentos:'Reportes', avance:'Reportes',
    seguimiento:'Reportes', contrato:'Administración', cuentas:'Administración'
  };
  const quickViews = ['cargue','proceso','revision','localizacion'];
  const number = new Intl.NumberFormat('es-CO');
  let viewTitle = 'Dashboard';
  let refreshId = 0;

  function setMenu(open, restoreFocus = false) {
    sidebar.classList.toggle('is-open', open);
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Cerrar navegación' : 'Abrir navegación');
    if (restoreFocus) toggle.focus();
  }
  toggle.addEventListener('click', () => {
    const open = toggle.getAttribute('aria-expanded') !== 'true';
    setMenu(open);
    if (open) sidebar.querySelector('button')?.focus();
  });
  sidebar.addEventListener('keydown', event => {
    if (event.key === 'Escape' && compact.matches) {
      event.preventDefault();
      setMenu(false, true);
    }
  });
  compact.addEventListener('change', () => setMenu(false));

  function navegacion(vista) {
    viewTitle = vista.titulo;
    restaurarRuta();
    if (compact.matches) setMenu(false);
  }
  function restaurarRuta() { get('taCrumb').textContent = viewTitle; }
  function rutaFicha() { get('taCrumb').textContent = viewTitle + ' / Ficha de expediente'; }

  function empty(message) {
    const p = document.createElement('p');
    p.className = 'ta-empty';
    p.textContent = message;
    return p;
  }
  function list(items, textFor) {
    const ul = document.createElement('ul');
    ul.className = 'ta-list';
    for (const item of items) {
      const li = document.createElement('li');
      const [name, detail] = textFor(item);
      const label = document.createElement('strong');
      label.textContent = name;
      const description = document.createElement('span');
      description.textContent = detail;
      li.append(label, description);
      ul.append(li);
    }
    return ul;
  }

  function metric(label, value, detail) {
    const card = document.createElement('div');
    card.className = 'ta-metric';
    const name = document.createElement('span');
    const total = document.createElement('strong');
    const caption = document.createElement('small');
    name.textContent = label;
    total.textContent = Number.isFinite(value) ? number.format(value) : '—';
    caption.textContent = Number.isFinite(value) ? detail : 'Dato no disponible';
    card.append(name, total, caption);
    return card;
  }
  function states(summary) {
    const host = get('taStates');
    const rows = summary?.estados;
    if (!rows?.length) {
      host.replaceChildren(empty(summary ? 'No hay estados registrados.' : 'Distribución no disponible.'));
      return;
    }
    const maximum = Math.max(1, ...rows.map(row => row.cantidad));
    host.replaceChildren(...rows.map(row => {
      const item = document.createElement('div');
      item.className = 'ta-state-row';
      const label = document.createElement('div');
      label.className = 'ta-state-label';
      const name = document.createElement('span');
      const count = document.createElement('strong');
      name.textContent = row.estado;
      count.textContent = number.format(row.cantidad);
      label.append(name, count);
      const track = document.createElement('span');
      track.className = 'ta-track';
      track.setAttribute('aria-hidden','true');
      const bar = document.createElement('i');
      bar.style.width = 100 * row.cantidad / maximum + '%';
      track.append(bar);
      item.append(label, track);
      return item;
    }));
  }
  function activity(loads) {
    const entries = (loads?.detalle || []).filter(row => row.subido_en)
      .sort((a,b) => b.subido_en.localeCompare(a.subido_en)).slice(0,5);
    get('taActivity').replaceChildren(entries.length
      ? list(entries, row => [row.carpeta, row.subido_en.replace('T',' ').slice(0,16)])
      : empty(loads ? 'No hay cargas registradas.' : 'Actividad no disponible.'));
  }
  function shortcuts() {
    const permitted = SESION?.pestanas || [];
    const buttons = quickViews.filter(key => permitted.includes(key)).map(key => {
      const view = VISTAS.find(item => item.clave === key);
      const button = document.createElement('button');
      button.className = 'btn2';
      button.type = 'button';
      button.textContent = view.titulo;
      button.dataset.shortcut = key;
      button.onclick = () => mostrarVista(view, get('menu').querySelector('[data-vista="'+key+'"]'));
      return button;
    });
    get('taQuick').replaceChildren(...buttons);
  }
  function alertas(rows) {
    if (!SESION?.pestanas?.includes('inicio')) return;
    const pending = rows.filter(row => !row.leida).slice(0,4);
    get('taAlerts').replaceChildren(pending.length
      ? list(pending, row => [row.titulo || 'Alerta', row.mensaje || row.texto || 'Consultar en alertas'])
      : empty('No hay alertas sin leer.'));
  }
  async function dashboard() {
    if (!SESION?.pestanas?.includes('inicio')) return;
    const current = ++refreshId;
    const indicators = get('taIndicators');
    indicators.setAttribute('aria-busy','true');
    indicators.replaceChildren(...Array.from({length:4}, () => {
      const skeleton = document.createElement('div');
      skeleton.className = 'ta-skeleton';
      skeleton.setAttribute('aria-hidden','true');
      return skeleton;
    }));
    get('taDashboardStatus').textContent = 'Actualizando indicadores…';
    shortcuts();
    const sources = await Promise.allSettled([
      pedir('/unidades/resumen'),
      SESION.pestanas.includes('proceso') ? pedir('/cargue/estado-de-cargas') : Promise.resolve(null),
      pedir('/unidades/ahora')
    ]);
    if (current !== refreshId) return;
    const [summary, loads, now] = sources.map(source => source.value);
    indicators.replaceChildren(
      metric('Expedientes registrados', summary?.total, 'Registro operativo'),
      metric('Archivos digitalizados', loads?.resumen?.archivos_cargados, 'Archivos registrados, incluidas partes'),
      metric('Hojas por revisar', now?.en_vuelo?.hojas_por_revisar, 'Revisión de hoja de control'),
      metric('En procesamiento', summary?.estados?.find(row => row.estado === 'En procesamiento')?.cantidad, 'Estado de expedientes')
    );
    states(summary);
    activity(loads);
    indicators.setAttribute('aria-busy','false');
    get('taDashboardStatus').textContent = sources.some(source => source.status === 'rejected')
      ? 'Algunos indicadores no están disponibles.' : 'Indicadores operativos actualizados.';
  }
  get('taRefresh').addEventListener('click', dashboard);
  return {grupo:key => groups[key], navegacion, restaurarRuta, rutaFicha, dashboard, alertas};
})();
