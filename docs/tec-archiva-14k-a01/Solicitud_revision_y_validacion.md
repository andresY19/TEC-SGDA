# Solicitud para el custodio y los responsables de aprobación

**Destino** `geology-local-20261106-57a99a`  
**Candidata** `2.13.0-rc.3-14h`  
**Estado de presentación** Pendiente de destinatarios autorizados.

## Al custodio histórico

Confirme su disponibilidad y el canal para realizar la validación. Si ya cuenta con evidencia de una validación autorizada para este destino, adjunte la referencia saneada. El resultado debe identificar la cuenta por una referencia, el rol administrativo, la consulta permitida que se verificó, la fecha, el entorno y el resultado. Excluya contraseñas, tokens y cabeceras de autorización.

Si se necesita un ingreso nuevo, el responsable de la ventana debe aprobar previamente el alcance y, si corresponde, el arranque de los servicios originales. El ingreso puede actualizar registros de autenticación. Si falla o exige cambiar la contraseña, suspenda y documente el motivo.

## A los responsables de proyecto y seguridad u operación

Revisen el [alcance de la política de 14J](../tec-archiva-14j-a01/Solicitud_aprobacion_politica_destino.md), el [borrador de 14I](../tec-archiva-14i-a01/Politica_destino.borrador.json) y las huellas cotejadas en [la evidencia de 14K](Evidencia_14K.json).

La decisión solicitada cubre el diseño de autorización para conciliación. El alcance es una operación en el worker aprobado, bajo /srv/geology/deposito, con permiso firmado de un solo consumo y plazo máximo de 300 segundos. El aprovisionamiento futuro requiere verificar las identidades efectivas del destino.

Registren APROBADA, APROBADA CON CONDICIONES o RECHAZADA, con nombre, rol, fecha, huellas revisadas y condiciones. El arranque, la actualización y la emisión de un permiso se autorizan mediante decisiones separadas.
