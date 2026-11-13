# TEC-ARCHIVA · Fase 14I

**PARTIAL · NO_GO · NOT_GRANTED**

Se prepararon la política de autorización del destino, el checklist del custodio y los planes de actualización y reversión. El borrador de política conserva las identidades protegidas y el alcance previsto. El operador lo rechaza antes de invocar Docker. Su aprovisionamiento y la captura de la identidad operativa requieren una ventana autorizada.

Se completaron ocho comprobaciones en 14I. Se verificaron los archivos e imágenes de rc.3, la identidad y configuración de los cuatro contenedores originales, los metadatos de sus volúmenes, los archivos del host, el respaldo protegido anterior, los archivos de evidencia de 14H y el ensayo de rollback de 14E. Se ejecutó la comprobación de identidad con propósito operation sobre el clon sintético existente. La fotografía coincidió con la certificación de 14H. Dos verificaciones del operador comprobaron que el borrador queda rechazado antes de acceder al destino o al firmante.

Las 856 comprobaciones de 14H y el rollback de 14E son evidencia previa. En 14I se verificaron sus registros, sin repetir esa regresión ni la reversión entre versiones. La última lectura integral de los bytes de los volúmenes originales corresponde a 14F. La verificación de 14I sobre esos volúmenes cubrió identidad, metadatos y ausencia de contenedores activos. El respaldo de 14E conserva sus hashes. El respaldo al corte está pendiente de la ventana.

El acceso histórico permanece PENDING_CUSTODIAN. Los cuatro contenedores originales siguen detenidos y conservan su configuración. En 14I se emitieron cero permisos y se hicieron cero ejecuciones dentro de los originales.

El cierre requiere validar al custodio, aprobar la ventana y sus límites, verificar el respaldo al corte y capturar los recursos efectivos de rc.3 antes de habilitar la operación de conciliación. La autorización de actualizar y la autorización de conciliar una operación concreta son actos independientes.

- [Evidencias de 14I](Evidencias_14I.json)
- [Política y procedimiento de aprovisionamiento](Politica_autorizacion_destino.md)
- [Borrador deliberadamente inejecutable](Politica_destino.borrador.json)
- [Checklist del custodio](Checklist_custodio.md)
- [Plan de actualización](Plan_actualizacion_local.md)
- [Plan de rollback](Plan_rollback_local.md)
- [Decisión](Matriz_GO_NO_GO.json)
