# Secuencia propuesta de cambio local

Estado NO_GO. UPGRADE_AUTHORIZATION=NOT_GRANTED. Destino actual geology-local-20261106-57a99a. Las operaciones descritas requieren autorización posterior y no se ejecutaron en 14G.

| Paso | Operación prevista | Evidencia para avanzar | Suspensión antes de avanzar |
|---|---|---|---|
| 1 | Obtener autorización expresa de ventana, responsables, imágenes y alcance. | Aprobación registrada y matriz GO/NO_GO actualizada. | Falta aprobación, falta custodio o la compatibilidad CLI del destino sigue sin cerrar. |
| 2 | Confirmar el estado del destino por los cuatro IDs completos de Evidencia_destino.json, imágenes, redes, volúmenes y montajes. | Coincidencia con el inventario aprobado y ausencia de escritores o tareas desconocidas. | Diferencias de identidad, imágenes o datos sin explicación. Excluir auxiliares que heredan etiquetas. |
| 3 | Ejecutar la captura coherente al corte según el procedimiento de 14F, inmediatamente antes del cambio. | Captura privada de PostgreSQL, Redis, depósito, expedidos, datos, configuraciones, código montado y metadatos. | Espacio insuficiente, ACL del destino no aplicada, datos cambiando o cualquier error de captura. Con el original detenido, recuperar PostgreSQL únicamente en una copia. |
| 4 | Verificar hashes y restauración aislada completa. | Dump lógico restaurable, catálogo, filas, secuencias, índices, restricciones, referencias SQL y archivos cotejados. | Hash inexplicado, error de restauración, pérdida documental o pérdida de acceso administrativo. |
| 5 | Preparar Redis autenticado con usuarios ACL, AOF, volumen aprobado y AUTH_REDIS_URL. Preparar el rol PostgreSQL restringido. | Pruebas de conexión autorizada, rechazo sin credenciales, durabilidad y permisos por tabla y secuencia. | Necesidad de superusuario en runtime, Redis público, fallo de persistencia o conexión fuera del destino aprobado. |
| 6 | Aplicar la política de sesiones aprobada: cierre general, firma nueva, registro limpio y nuevo ingreso. | Rechazo de pases anteriores y recuperación administrativa custodiada. Generar secretos nuevos para el cambio real. | Pases antiguos aceptados, indisponibilidad del registro o pérdida de acceso. No depender de contar pases originales. |
| 7 | Arrancar TEC-ARCHIVA con los digests autorizados, UID/GID 10001:10001, raíz de solo lectura y permisos mínimos. | Salud HTTP y Celery, ausencia de DDL de arranque, sin montajes de código, IA deshabilitada y puertos limitados por el plan aprobado. | Configuración distinta de la certificada, errores críticos o cambios de esquema inesperados. |
| 8 | Verificar acceso administrativo con participación del custodio. | Identidad, rol, permisos, nuevo ingreso y controles de sesión aprobados. | Fallo de acceso, privilegios ampliados o sesión revocada reactivada. |
| 9 | Ejecutar pruebas funcionales y documentales autorizadas con registros sintéticos nuevos. | Login, logout, revocación, consulta restringida, cargue, división, Celery, ambos PDF/A, veraPDF, trazabilidad, conciliación CLI, rollback y hashes. | Referencias rotas, pérdida de originales, operación incierta sin diario o ausencia de permisos necesarios. |
| 10 | Decidir aceptación o rollback. | Verificación conjunta del operador y custodio, manifiestos y control de diferencias. | Mantener el acceso cerrado mientras falte evidencia o quede un defecto crítico. Preservar escrituras y diarios antes de revertir. |

## Pendiente de compatibilidad CLI

La candidata contiene un rechazo explícito de GEOLOGY_LOCAL_PROJECT=geology-local-20261106-57a99a. También lo rechaza cuando --local-project coincide. La certificación de 14F usó geology-restore14f-cli como contexto del proceso.

Antes de emitir GO se debe definir y certificar un mecanismo de ejecución aplicable al destino aprobado. Si se conserva el identificador actual, el guardia requiere una candidata derivada y pruebas de la modificación. Una eventual propuesta de otro proyecto debe aprobar su identidad, redes, almacenamiento y transición. Cambiar una variable únicamente para evitar el guardia no constituye evidencia de compatibilidad ni de aislamiento.

Este preflight conserva la candidata y el destino. La observación se registra como CFG-14G-01.

## Respaldo al corte y capacidad

El procedimiento vigente está en docs/tec-archiva-14f-a01/Procedimiento_respaldo_al_corte.md. Se revalidó su cobertura contra el inventario y la restauración 14E. El destino previsto es un directorio nuevo C:\Users\andre\TEC_ARCHIVA_Cutover\<ventana>, cuya ACL debe protegerse al crearlo. Ese directorio no se creó durante 14G.

El respaldo previo en C:\Users\andre\TEC_ARCHIVA_14E\restore14e-a01 conserva sus hashes y ACL protegida. La capacidad actual y el tamaño base de staging se registran en Evidencia_candidata.json. La estimación base no incluye crecimiento futuro, WAL adicional ni nuevas evidencias. Volver a medir y reservarlos antes de la captura. No existe un respaldo al corte certificado de esta ventana.
