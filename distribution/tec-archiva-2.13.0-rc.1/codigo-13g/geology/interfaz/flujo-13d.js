const TECFlujo = (() => {
  const byId = id => document.getElementById(id);
  const current = byId("cgEtapas").children;
  const confirm = byId("cgConfirmar");
  const clear = byId("cgLimpiar");
  let files = [], invalid = false, sending = false, lookup = 0;
  let reviews = [], reviewNotice = "", reviewTrigger;

  function step(index) {
    Array.from(current).forEach((item, i) => {
      if (i === index) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
  }

  function seleccionar(selection) {
    if (sending) return;
    files = selection;
    const list = byId("cgArchivosLista");
    const errors = [];
    list.replaceChildren(...files.map(file => {
      if (!/\.(pdfa?|jpe?g|png|tiff?)$/i.test(file.name)) errors.push("Formato no admitido: " + file.name);
      if (!file.size) errors.push("Archivo vacío: " + file.name);
      const li = document.createElement("li");
      li.textContent = file.name + " · " + new Intl.NumberFormat("es-CO").format(file.size) + " bytes";
      return li;
    }));
    invalid = errors.length > 0;
    byId("cgError").textContent = errors.join(". ");
    byId("cgSeleccionEstado").textContent = files.length
      ? files.length + " archivo(s) seleccionado(s). El servidor verifica el contenido, el inventario y los duplicados al recibirlos."
      : "Seleccione los documentos que desea cargar.";
    clear.disabled = !files.length;
    confirm.disabled = !files.length || invalid;
    step(!files.length ? 1 : invalid ? 2 : 3);
  }

  byId("cgInventario").addEventListener("submit", async event => {
    event.preventDefault();
    const code = byId("cgCarpeta").value.trim().toUpperCase();
    const status = byId("cgInventarioEstado");
    const query = ++lookup;
    if (!code) { status.textContent = "Escriba un código de carpeta."; return; }
    status.textContent = "Consultando inventario…";
    try {
      const result = await pedir("/unidades/inventario/" + encodeURIComponent(code));
      if (query !== lookup) return;
      status.textContent = [code, result.caja_origen && "Caja " + result.caja_origen, result.asunto].filter(Boolean).join(" · ");
      if (!files.length) step(1);
    } catch (error) {
      if (query === lookup) status.textContent = error.message;
    }
  });
  byId("cgCarpeta").addEventListener("input", () => { lookup++; byId("cgInventarioEstado").textContent = ""; });
  clear.addEventListener("click", () => { seleccionar([]); byId("cgSeleccionar").focus(); });
  confirm.addEventListener("click", async () => {
    if (sending || invalid || !files.length) return;
    sending = true;
    const controls = [confirm, clear, byId("cgSeleccionar"), byId("cgDefinitiva"), byId("cgReemplazar")];
    controls.forEach(control => control.disabled = true);
    const status = byId("cgTransferencia");
    status.textContent = "Enviando documentos…";
    try {
      const sent = await subirArchivos(files);
      if (sent) {
        status.textContent = "Envío finalizado. Revise la recepción de cada documento y consulte su procesamiento.";
      } else {
        status.textContent = "No se enviaron documentos.";
      }
      sending = false;
      if (sent) { seleccionar([]); step(4); }
    } catch (error) {
      status.textContent = "No se pudo terminar el envío. Consulte el resultado antes de reintentar.";
    } finally {
      sending = false;
      controls.slice(2).forEach(control => control.disabled = false);
      confirm.disabled = invalid || !files.length;
      clear.disabled = !files.length;
      if (document.activeElement === document.body) (files.length ? confirm : byId("cgIrProceso")).focus();
    }
  });
  byId("cgIrProceso").addEventListener("click", () => {
    const view = VISTAS.find(v => v.clave === "proceso");
    const trigger = Array.from(document.querySelectorAll("nav button")).find(b => b.textContent.trim() === view.titulo);
    if (trigger) { mostrarVista(view, trigger); byId("buscarProceso").focus(); }
  });

  let lastBatch;
  function archivar() {
    const latest = byId("lecturaNombres");
    if (latest.childElementCount && lastBatch) {
      const entry = document.createElement("details");
      const heading = document.createElement("summary");
      heading.textContent = "Envío del " + lastBatch.toLocaleString("es-CO");
      entry.append(heading, ...Array.from(latest.children));
      const history = byId("cgHistorialLotes");
      history.prepend(entry);
      if (history.childElementCount > 5) history.lastElementChild.remove();
      byId("cgHistorial").hidden = false;
    }
    lastBatch = new Date();
  }

  function renderReviews() {
    const query = byId("taReviewQuery").value.trim().toLocaleLowerCase("es");
    const state = byId("taReviewState").value;
    const results = reviews.filter(row => (!state || row.estado === state) &&
      [row.codigo_carpeta, row.codigo_referencia, row.titulo].some(value => String(value || "").toLocaleLowerCase("es").includes(query)));
    const table = byId("cuerpoRevision");
    table.replaceChildren();
    const status = byId("taReviewStatus");
    status.textContent = reviewNotice || results.length + " expediente(s) para revisión.";
    if (!results.length) {
      const cell = table.insertRow().insertCell();
      cell.colSpan = 5;
      cell.className = "vacio";
      cell.textContent = reviewNotice || "No hay expedientes que coincidan con los filtros.";
      return;
    }
    for (const result of results) {
      const row = table.insertRow();
      for (const value of [result.codigo_carpeta, result.codigo_referencia, result.titulo]) row.insertCell().textContent = value || "—";
      const badge = document.createElement("span");
      badge.className = "pill";
      badge.textContent = result.estado;
      row.insertCell().append(badge);
      const button = document.createElement("button");
      button.className = "btn2";
      button.textContent = "Abrir";
      button.setAttribute("aria-label", "Abrir revisión de " + result.codigo_carpeta);
      button.addEventListener("click", () => { reviewTrigger = button; verFicha(result.codigo_carpeta); });
      row.insertCell().append(button);
    }
  }

  let processQuery = 0, processTrigger;
  async function tecnico(code, trigger) {
    const id = ++processQuery;
    processTrigger = trigger;
    const detail = byId("taProcessDetail");
    const list = byId("taProcessParts");
    const status = byId("taProcessStatus");
    byId("taProcessTitle").textContent = "Detalle técnico · " + code;
    list.replaceChildren();
    detail.hidden = false;
    status.textContent = "Consultando archivos…";
    detail.focus();
    try {
      const parts = await pedir("/cargue/partes/" + encodeURIComponent(code));
      if (id !== processQuery) return;
      status.textContent = parts.length ? "Disponibilidad de archivos registrados." : "No se encontraron archivos registrados.";
      for (const part of parts) {
        const item = document.createElement("li");
        const title = document.createElement("strong");
        title.textContent = part.nombre;
        const note = document.createElement("p");
        note.textContent = (part.en_disco ? "Archivo registrado disponible" : "Archivo registrado ausente") +
          (part.paginas ? " · " + part.paginas + " páginas" : "") + " · " +
          (part.tiene_copia_de_consulta ? "Copia de consulta disponible" : "Copia de consulta sin disponibilidad confirmada");
        item.append(title, note);
        if (part.en_disco || part.tiene_copia_de_consulta) {
          const view = document.createElement("button");
          view.className = "btn2";
          view.textContent = "Ver documento";
          view.addEventListener("click", () => verDocumento(code,part.fragmento,part.tiene_copia_de_consulta ? "consulta" : "original"));
          item.append(view);
        }
        list.append(item);
      }
    } catch (error) {
      if (id === processQuery) status.textContent = error.message;
    }
  }
  byId("taProcessClose").addEventListener("click", () => {
    processQuery++;
    byId("taProcessDetail").hidden = true;
    (processTrigger?.isConnected ? processTrigger : byId("buscarProceso")).focus();
  });

  byId("taReviewQuery").addEventListener("input", renderReviews);
  byId("taReviewState").addEventListener("change", renderReviews);
  return {
    seleccionar,
    archivar,
    tecnico,
    revision(rows, notice) { reviews = rows; reviewNotice = notice; renderReviews(); },
    cerrarRevision() {
      byId("fichaRevision").replaceChildren();
      (reviewTrigger?.isConnected ? reviewTrigger : byId("taReviewQuery")).focus();
    }
  };
})();
