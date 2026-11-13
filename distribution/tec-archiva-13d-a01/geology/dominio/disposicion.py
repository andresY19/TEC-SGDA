"""Análisis local de suficiencia; no crea candidatas automáticas de eliminación."""


def evaluar(exp,subserie=None,periodo=None):
    pendientes=[]
    if subserie is None: pendientes.append('Falta subserie TVD identificada inequívocamente.')
    if subserie is not None:
        if getattr(subserie,'disposicion_final',None) not in ('E','S'): pendientes.append('No consta disposición E/S inequívoca.')
        if getattr(subserie,'retencion_central_anios',None) is None: pendientes.append('No consta retención aplicable.')
    if periodo is None or not getattr(periodo,'fecha_convalidacion_tvd',None): pendientes.append('Falta evidencia de convalidación TVD.')
    pendientes.append('Pendiente decisión humana sobre plazos, selección, derechos y procedimiento; no se autoriza destrucción.')
    return {'carpeta':exp.codigo_carpeta,'elegible':False,'requiere_persona':True,'pendientes':pendientes}


def revisar_todo(db):
    from geology.modelos import Expediente,Subserie,Periodo
    with db.no_autoflush:
        revision=[]
        for e in db.query(Expediente).all():
            sub=db.get(Subserie,e.subserie_id) if e.subserie_id else None
            periodo=db.get(Periodo,e.periodo_id) if e.periodo_id else None
            revision.append(evaluar(e,sub,periodo))
    return [],{'revisados':len(revision),'candidatas':0,'revision_pendiente':True,'analisis':revision,
        'motivo':'No se deduce destrucción por parecido de nombres, digitalización o texto libre.'}
