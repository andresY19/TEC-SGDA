const TECAdministracion = (() => {
  const byId = id => document.getElementById(id);
  const body = byId("cuTabla");
  const search = byId("taAccountSearch");
  const role = byId("taAccountRole");
  const state = byId("taAccountState");
  const status = byId("taAccountStatus");
  const pages = byId("taAccountPages");
  const previous = byId("taAccountPrevious");
  const next = byId("taAccountNext");
  const pageSize = 25;
  let page = 0;

  function render() {
    const rows = Array.from(body.rows).filter(row => row.cells.length === 6);
    const query = search.value.trim().toLocaleLowerCase("es");
    const matches = rows.filter(({cells}) => {
      const account = [cells[0].textContent,cells[1].textContent].join(" ").toLocaleLowerCase("es");
      return (!query || account.includes(query)) &&
        (!role.value || cells[2].textContent.trim().split(" · ")[0] === role.value) &&
        (!state.value || cells[3].querySelector(".pill")?.textContent === state.value);
    });
    const total = Math.ceil(matches.length / pageSize);
    page = Math.min(page, Math.max(0,total-1));
    const visible = new Set(matches.slice(page*pageSize,(page+1)*pageSize));
    rows.forEach(row => row.hidden = !visible.has(row));
    pages.hidden = total <= 1;
    previous.disabled = page === 0;
    next.disabled = page >= total-1;
    status.textContent = !rows.length ? "" : matches.length
      ? matches.length + (matches.length === 1 ? " cuenta" : " cuentas") + " · Página " + (page+1) + " de " + total
      : "Ninguna cuenta coincide con los filtros.";
  }

  for (const control of [search,role,state]) control.addEventListener("input", () => {page = 0; render();});
  previous.addEventListener("click", () => {page--; render(); if (previous.disabled) next.focus();});
  next.addEventListener("click", () => {page++; render(); if (next.disabled) previous.focus();});
  new MutationObserver(render).observe(body,{childList:true});
  byId("taNewAccount").addEventListener("submit", event => {
    event.preventDefault();
    const submit = event.submitter;
    if (submit?.disabled) return;
    if (submit) submit.disabled = true;
    crearCuenta().finally(() => {if (submit) submit.disabled = false;});
  });

  function confirmar(correo, activo) {
    const dialog = byId("taAccountConfirm");
    if (dialog.open) return Promise.resolve(false);
    const trigger = document.activeElement;
    byId("taAccountConfirmText").textContent = (activo ? "Activar " : "Desactivar ") + correo + "?";
    dialog.returnValue = "cancel";
    dialog.showModal();
    return new Promise(resolve => {
      dialog.addEventListener("close", () => {
        if (trigger?.isConnected) trigger.focus();
        resolve(dialog.returnValue === "confirm");
      }, {once:true});
    });
  }

  body.addEventListener("change", event => {
    const input = event.target;
    const correo = input.closest("tr")?.dataset.correo;
    if (!correo) return;
    if (input.dataset.cuentaHabilitacion) habilitar(correo,input.dataset.cuentaHabilitacion,input.checked);
    if (input.dataset.cuentaCobertura === "limites") sinLimites(correo,input.checked);
    if (input.dataset.cuentaCobertura === "propio") apruebaLoPropio(correo,input.checked);
  });
  body.addEventListener("click", event => {
    const button = event.target.closest("button[data-cuenta-accion]");
    if (!button) return;
    const correo = button.closest("tr").dataset.correo;
    const action = button.dataset.cuentaAccion;
    if (action === "restablecer") restablecerClave(correo);
    else activarCuenta(correo,action === "activar");
  });

  function enfocarCuenta(correo) {
    const row = Array.from(body.rows).find(item => !item.hidden && item.dataset.correo === correo);
    (row?.querySelector("button[data-cuenta-accion]:last-child") || search).focus();
  }

  return {confirmar,enfocarCuenta};
})();
