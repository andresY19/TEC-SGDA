"""
Asistente de redacción para un elemento de la ficha ISAD(G).

A diferencia de «Generar ISAD(G)», que redacta varios elementos de una vez, aquí quien
describe manda: elige un elemento, escribe lo que sabe o lo que quiere decir, y la IA propone
un texto que se muestra al lado. Nada se guarda hasta que la persona lo acepte y pulse Guardar.

Modos
  redactar   la IA escribe el elemento desde los datos verificados y el documento.
  mejorar    la IA pule lo que la persona ya escribió, sin agregar hechos.
  ampliar    la IA toma las notas o ideas de la persona y las convierte en prosa de archivo.
"""
from __future__ import annotations

from geology.dominio.campos_isadg import POR_CLAVE, quitar_marca

MODOS = ("redactar", "mejorar", "ampliar")


def instruccion_campo(clave: str, modo: str, actual: str, indicaciones: str,
                      contexto: dict) -> str:
    e = POR_CLAVE[clave]
    tramites = "\n".join(
        f"  {t.get('no_item')}. {t.get('fecha') or 'SF'} · {t.get('tipo_documental') or 'sin tipo'}"
        f" · folios {t.get('folio_desde')} a {t.get('folio_hasta')}"
        for t in (contexto.get("tramites") or [])[:80]) or "  (sin trámites)"
    actual = quitar_marca(actual) or ""

    if modo == "mejorar":
        tarea = ("Mejore la redacción del texto de la persona: ortografía, claridad y tono de "
                 "archivo. NO agregue hechos nuevos ni quite los que escribió.")
    elif modo == "ampliar":
        tarea = ("Convierta las notas o ideas de la persona en prosa sobria de archivo. Use solo "
                 "lo que ella dice y lo verificado abajo.")
    else:
        tarea = ("Redacte este elemento a partir de los datos verificados y del documento, si "
                 "viene adjunto.")

    return f"""Usted es archivista y apoya a una profesional que describe una unidad documental
conforme a la norma ISAD(G) segunda edición y a la NTC 4095 de 2013, fondo acumulado del
Servicio Geológico Colombiano, contrato 733 de 2026. La profesional decide; usted propone.

Elemento: {e.numeral} {e.etiqueta}. {e.ayuda}

{tarea}

Texto actual del elemento:
{actual or '  (vacío)'}

Indicaciones o notas de la profesional:
{indicaciones.strip() or '  (ninguna)'}

Datos verificados, que NO debe contradecir:
  Código de carpeta: {contexto.get('codigo_carpeta')}
  Periodo: {contexto.get('periodo')} ({contexto.get('rango_periodo')})
  Entidad productora: {contexto.get('entidad_productora')}
  Oficina productora: {contexto.get('oficina_productora')}
  Serie y subserie: {contexto.get('serie')} › {contexto.get('subserie')}
  Fechas extremas: {contexto.get('fechas_extremas')}
  Folios: {contexto.get('folios')}
  Hoja de control:
{tramites}

Reglas. La ficha es un documento institucional: NO mencione inteligencia artificial, modelos, propuestas, ni cómo se elaboró, y no cite la hoja de control: describa la unidad directamente. Español, prosa sobria de archivo, sin viñetas, sin adjetivos de valoración, sin repetir
lo que dice otro elemento. No invente fechas, nombres, lugares ni cifras. Si no alcanza la
información, devuelva el texto vacío antes que suponer.

Responda EXCLUSIVAMENTE un objeto JSON con la clave "texto", sin nada más."""
