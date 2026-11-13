"""
Qué se le muestra a la entidad contratante.

Regla de la dirección del proyecto: lo retirado del flujo, lo devuelto y lo que tenga errores
no se muestra en consulta. La entidad solo ve unidades conformes.

Una unidad es publicable cuando
  1. su estado es de los que se publican (hoja revisada en adelante; nunca retirada ni devuelta),
  2. la hoja de control y las imágenes cargadas no se contradicen (sin errores de validación),
  3. si ya tiene descripción, la ficha no trae textos marcados como propuesta del modelo ni
     elementos obligatorios vacíos.

Que falte la imagen no la oculta: hasta que llegue la digitalización definitiva hay hojas de
control buenas que la entidad debe poder ver. Sí la oculta una imagen que contradice la hoja.
"""
from __future__ import annotations

from geology.dominio.campos_isadg import hallazgos, quitar_marca
from geology.dominio.estados import Estado
from geology.dominio.validar_entrega import validar_unidad
from geology.dominio.neutralidad import quitar_marca as _qm, rastros

ESTADOS_CON_DESCRIPCION = (Estado.DESCRIPCION_VALIDADA.value, Estado.ARCHIVADO.value,
                           Estado.EN_INVENTARIO.value)
# Códigos de validación que no ocultan la unidad
TOLERADOS = {"SIN_IMAGEN"}


def motivos_de_bloqueo(db, exp) -> list[str]:
    """Por qué NO se publica, en lenguaje de equipo. Lista vacía significa que se publica."""
    if exp.estado in (Estado.RETIRADO.value, Estado.DEVUELTO.value):
        return [f"Está en «{exp.estado}»."]
    motivos = []
    informe = validar_unidad(db, exp)
    motivos += [h["mensaje"] for h in informe["hallazgos"]
                if h["gravedad"] == "error" and h["codigo"] not in TOLERADOS]
    if exp.estado in ESTADOS_CON_DESCRIPCION:
        motivos += [f"{h['numeral']} {h['etiqueta']}: {h['mensaje']}"
                    for h in hallazgos(exp) if h["gravedad"] == "bloquea"]
    # La entidad no debe enterarse de que hubo IA: ni una mención en la hoja.
    for t in (exp.tramites or []):
        for campo in (t.tipo_documental, t.observaciones):
            r = rastros(campo)
            if r:
                motivos.append(f"El trámite {t.no_item} menciona «{r[0]}». Reescríbalo en la hoja de control.")
                break
    return motivos


def es_publicable(db, exp) -> bool:
    """Se muestra a la entidad solo si una persona la envió Y sigue sin errores."""
    return bool(getattr(exp, "publicado_consulta", False)) and not motivos_de_bloqueo(db, exp)


def se_puede_enviar(db, exp) -> list[str]:
    """Motivos que impiden enviarla a consulta. Vacío significa que puede enviarse."""
    if exp.estado not in ESTADOS_CON_DESCRIPCION:
        return [f"Está en «{exp.estado}». Solo se envía a consulta lo que ya tiene la descripción validada."]
    return motivos_de_bloqueo(db, exp)


def nombre_publico(exp) -> str:
    """El título solo sale cuando la descripción está validada; antes, el campo 7 de la hoja."""
    if exp.estado in ESTADOS_CON_DESCRIPCION and exp.titulo:
        return _qm(exp.titulo) or ""
    return _qm(exp.nombre_expediente) or ""
