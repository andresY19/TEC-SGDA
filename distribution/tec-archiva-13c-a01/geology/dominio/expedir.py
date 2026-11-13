"""Expedición local de hojas verificadas; jamás completa firmas históricas."""
from geology.dominio.estados import Estado


def completar_revisores(db):
    """Política explícita: conservar el dato ausente; no inferirlo desde eventos."""
    return 0


def datos_de_hoja(db,exp):
    from geology.modelos import Periodo,Subserie,Serie,Seccion
    with db.no_autoflush:
        estados={Estado.HOJA_REVISADA.value,Estado.DESCRIPCION_POR_VALIDAR.value,
            Estado.DESCRIPCION_VALIDADA.value,Estado.ARCHIVADO.value,Estado.EN_INVENTARIO.value}
        if exp.estado not in estados or not exp.reviso_hoja or not exp.fecha_revision:
            raise ValueError('Hoja pendiente de revisión humana; no se expide como instrumento verificado.')
        from geology.dominio.campos_isadg import tiene_marca
        if any(tiene_marca(v) for t in exp.tramites for v in (t.tipo_documental,t.observaciones)):
            raise ValueError('La hoja contiene propuestas pendientes; requiere revisión humana.')
        sub=db.get(Subserie,exp.subserie_id) if exp.subserie_id else None
        serie=db.get(Serie,sub.serie_id) if sub else None
        seccion=db.get(Seccion,serie.seccion_id) if serie else None
        if not sub or not serie or not seccion or seccion.periodo_id != exp.periodo_id:
            raise ValueError('Clasificación TVD incompleta o incompatible con el período; revisión humana pendiente.')
        datos={'codigo_dependencia':seccion.codigo_dependencia if seccion else '',
            'dependencia':seccion.oficina_productora if seccion else '',
            'codigo_serie':serie.codigo if serie else '', 'serie':serie.nombre if serie else '',
            'codigo_subserie':sub.codigo if sub else '', 'subserie':sub.nombre if sub else '',
            'nombre_expediente':exp.nombre_expediente or '', 'reviso_hoja':exp.reviso_hoja or '',
            'fecha_revision':exp.fecha_revision,'responsable_hoja':exp.responsable_hoja or '',
            'fecha_diligenciamiento':exp.fecha_diligenciamiento,
            'tramites':[{**{k:getattr(t,k,None) for k in ('no_item','tipo_documental','folio_desde',
                'folio_hasta','no_radicado','sistema_informacion','expediente_sgdea','enlace_acceso','observaciones')},
                'fecha':getattr(t,'fecha',None) or getattr(t,'fecha_texto',None)}
                for t in exp.tramites]}
        def validar(valor):
            if isinstance(valor,str) and valor.lstrip().startswith('='):
                raise ValueError('Texto interpretable como fórmula; revisión humana pendiente.')
            if isinstance(valor,dict):
                for v in valor.values(): validar(v)
            if isinstance(valor,list):
                for v in valor: validar(v)
        validar(datos)
        return datos


def armar(db,caja=None,periodo=None,limite=300,por_pagina=4):
    from geology.modelos import Expediente,Periodo
    from geology.dominio import formatos_sgc as fmt
    if not 1<=limite<=1000 or por_pagina not in (1,2,4): raise ValueError('Parámetros de expedición inválidos.')
    estados=(Estado.HOJA_REVISADA.value,Estado.DESCRIPCION_POR_VALIDAR.value,
        Estado.DESCRIPCION_VALIDADA.value,Estado.ARCHIVADO.value,Estado.EN_INVENTARIO.value)
    with db.no_autoflush:
        q=db.query(Expediente).filter(Expediente.estado.in_(estados))
        if caja: q=q.filter(Expediente.caja_definitiva==caja)
        if periodo: q=q.join(Periodo,Expediente.periodo_id==Periodo.id).filter(Periodo.numero_romano==periodo)
        archivos={}
        for exp in q.order_by(Expediente.id).limit(limite).all():
            if not exp.reviso_hoja or not exp.fecha_revision or not exp.tramites: continue
            import re
            if not re.fullmatch(r'AC-CP-\d{5,6}',exp.codigo_carpeta): raise ValueError('Código inseguro para expedición.')
            datos=datos_de_hoja(db,exp)
            # Sin clasificacion documentada no se publica una hoja como instrumento final.
            if not datos['codigo_serie'] or not datos['codigo_subserie']: continue
            archivos[f'F-GDM-007_{exp.codigo_carpeta}.xlsx']=fmt.hoja_de_control(datos)
        return archivos
