# GEOLOGY — Fase 11D: conciliación documental e idempotencia

## Resultado y alcance

Certificación aislada completada: **428/428 pruebas aprobadas**, 0 fallidas, 0 omitidas y 0 bloqueadas. Se ejecutaron las 403 regresiones de referencia y 25 pruebas adicionales. PASS corresponde al conciliador conservador probado en PostgreSQL y almacenamiento Linux local; no autoriza integración ni despliegue.

Proyecto independiente: `geology-recon11d-b8194863`. Copia de trabajo: `C:/Users/andre/GEOLOGY_Reconciliation_11D/candidate-e8caffdf2e`. PostgreSQL, Redis y almacenamiento documental propios; sin usar bases ni volúmenes originales. El entorno queda conservado para revisión. Se reutilizaron imágenes existentes y se montó la copia de código de certificación: no se certificó una nueva imagen OCI.

## Preflight e integridad

- Los 109 hashes del contexto certificado 11C coinciden antes y después. La candidata `geology-cand11c-858e84aa` no se modificó.
- Respaldos protegidos: siete archivos verificados por hash, directorio con ACL restringida. No se restauraron ni divulgaron contenidos.
- Docker disponible; cola original sin tareas pendientes, sin confirmar ni desconocidas. IA deshabilitada; claves API vacías verificadas sin exponer valores.
- Espacio observado: C 185,88 GB; D 16,67 GB; F 25,06 GB.
- Identidad, imagen, arranque, reinicios y montajes de todos los contenedores preexistentes se conservaron, incluidos original, 11C y TEC-MAIL.
- Código, archivos protegidos, documentos y diarios originales conservaron hashes. No se ejecutaron migraciones sobre recursos originales.

Evidencias: `phase11d-preflight.json`, `phase11d-original-final.json`, `phase11d-source-manifest.json`, `phase11d-results.json` y `phase11d-reconciliation-integrity.json` en la raíz del repositorio.

## Diagnóstico y estados

Cargue, reemplazo y división PDF comparten el diario `operacion.json`: carpeta de operación, registros previstos y referencias documentales. PDF/A utiliza eventos de preservación, referencias SQL a derivados y evidencia de validación. Una excepción o un indicador de rollback en un diario no acreditan por sí solos el resultado de una transacción. Puede haberse confirmado el commit y perdido su respuesta; también pueden quedar archivos sin referencias SQL.

| Estado lógico | Evidencia y transición permitida |
|---|---|
| PENDING | Operación iniciada; todavía no hay resultado probado. Se conserva el diario del productor. |
| UNCERTAIN | Commit pendiente, respuesta perdida o resultado no acreditado. No se repite la operación sensible. |
| COMMITTED | Coincidencia exacta de registros SQL bloqueados, ámbito, referencias, tamaños y hashes; PDF/A exige además su validación. Es el resultado probado de la observación. |
| ROLLED_BACK | Requiere evidencia autoritativa de rollback. El contrato legacy no proporciona prueba suficiente para automatizar esta clasificación. La ausencia de filas no basta. |
| NEEDS_REVIEW | Evidencia incompleta, contradictoria, inaccesible o concurrencia incompatible. Conservar archivos y diarios; intervención humana. |
| RECONCILED | Recibo inmutable de una observación COMMITTED verificada. No reescribe el diario original ni modifica SQL. |

Los seis estados definen el contrato de interpretación; no se añadió una columna SQL ni un ciclo paralelo de negocio. El ejecutable emite RECONCILED/COMMITTED o NEEDS_REVIEW. ROLLED_BACK no se fabrica para cerrar casos ambiguos. La certificación de una observación no promete que los registros nunca cambien después de liberar sus bloqueos.

## Mecanismo implementado

Código entregado en `distribution/reconciliation11d/`:

- `geology/dominio/conciliacion.py`: lectura correlacionada y recibos conservadores.
- `scripts/reconcile_documents_11d.py`: entrada explícita de operador, restringida al proyecto aislado y con IA deshabilitada.
- `tests/reconciliation_11d_tests.py`, `tests/reconciliation_redis_outage_11d.py` y metadatos históricos sintéticos.

Cada operación conserva su identificador estable: ruta relativa del directorio de operación/UUID existente. El conciliador verifica pertenencia a la raíz autorizada, rechaza enlaces simbólicos y rutas externas, JSON ambiguo, registros duplicados y evidencia incompleta. Compara identificadores, expediente, carpeta, fragmentos, rutas, tamaño y SHA-256. Para reemplazos conserva los archivos anteriores y verifica que sus referencias anteriores no contradigan la nueva operación. Para PDF/A exige ambos derivados, referencias SQL exactas y evidencia de validación.

Un bloqueo exclusivo no bloqueante de archivo serializa conciliadores de la misma operación. Bloqueos PostgreSQL NOWAIT sobre los recursos correspondientes se coordinan con el productor; la transacción es de lectura/bloqueo y termina en rollback, sin DML de negocio. Se releen diarios y hashes antes de emitir resultado. No depende de Redis.

El recibo `reconciliation-<SHA256>.json` deriva de contenido canónico; se crea exclusivamente, se sincroniza a disco y no se sobrescribe. Una observación idéntica reutiliza el recibo existente, cuya integridad vuelve a comprobarse. Evidencia diferente produce una nueva observación, conservando las anteriores. Un recibo parcial o conflictivo bloquea la conciliación; no se borra ni repara silenciosamente.

No hay borrado automático, regeneración, reentrega, cambio de sesión ni decisión archivística. No se modificaron productores existentes de 11C ni se incorporó un trabajador automático al original. Los fallos se sanitizan; no se registran credenciales.

## Fallos y concurrencia

| Escenario requerido | Evidencia ejecutada / resultado |
|---|---|
| Antes de escribir archivos | Diario ausente: NEEDS_REVIEW. |
| Durante escritura | Escritura/JSON parcial: NEEDS_REVIEW. |
| Después de escribir archivos | SQL ausente: conservar archivos, NEEDS_REVIEW. |
| SQL antes de commit | Rollback real de prueba; no se declara COMMITTED. |
| Commit aceptado, respuesta perdida | Commit PostgreSQL real y diario incierto; coincidencia exacta permite RECONCILED. También probado con el trabajador PDF/A. |
| Reinicio del trabajador | Regresiones de reinicio y nueva invocación del conciliador en otro proceso reutilizan evidencia. |
| Reintento de misma operación | Mismo recibo, sin registros ni derivados nuevos. |
| Dos conciliadores | Exclusión concurrente real; segundo intento rechaza conflicto, sin duplicación. |
| Archivo faltante | Referencia a archivo inexistente: NEEDS_REVIEW. |
| Hash inconsistente | NEEDS_REVIEW, documento conservado. |
| Diario incompleto | NEEDS_REVIEW, diario conservado. |
| Redis no disponible | Prueba adicional con Redis del proyecto temporal realmente detenido; conciliación idempotente correcta. Redis restaurado y saludable. |

Además: productor SQL concurrente, sustitución de ámbito, división en tres documentos, ruta externa, fallo de conexión SQL, enlaces simbólicos, identificadores duplicados, diarios reales de cargue/reemplazo/división sintéticos y rechazo del proyecto original por el CLI.

## Caso histórico de 25 bytes

Se leyeron únicamente metadatos y hashes del archivo histórico rechazado y su diario. El ensayo utiliza nuevos identificadores, rutas y 25 bytes sintéticos, no una copia del contenido original. El diario declara rollback pero no contiene un recibo SQL autoritativo: resultado NEEDS_REVIEW. No se interpreta la excepción HTTP ni la ausencia de filas como prueba suficiente de rollback.

Archivo histórico SHA-256: `00213efca06810211e3415538b600d1755aabe1a754c4a58c04f2c6a968dfbde`.
Diario SHA-256: `7368abba2d180d3143b42e3cf61f67393d934959a526d9c834de30537c48a300`.
Ambos permanecen intactos; evidencia en `phase11d-historical-metadata.json`.

## Regresión ejecutada

| Suite | Aprobadas |
|---|---:|
| Unitarias | 321 |
| Operacionales | 16 |
| Herramientas PDF/A aisladas | 13 |
| Runtime normal | 6 |
| Reinicio | 3 |
| Sesiones HTTP | 22 |
| Durabilidad | 2 |
| Seguridad documental | 20 |
| Conciliación | 24 |
| Redis realmente indisponible | 1 |
| **Total** | **428** |

Fallidas: 0; omitidas: 0; bloqueadas: 0 en las ejecuciones finales. Hubo dos interrupciones preparatorias del harness heredado: prefijo de proyecto 11C y guard de etapa posterior a runtime. Se corrigieron exclusivamente las copias aisladas, conservando sus registros. Esos intentos abortaron antes de ejecutar sus casos; no se cuentan como pruebas aprobadas ni se ocultan como fallos de aplicación.

Los logs originales están en `C:/Users/andre/GEOLOGY_Reconciliation_11D/candidate-e8caffdf2e/results`; sus nombres, cantidades y hashes quedan en el índice de evidencia. Las pruebas de sesiones de referencia usan identidades sintéticas; el conciliador no modifica sesiones.

Una pasada adicional por 40 operaciones conservó los 303 archivos previamente existentes y el hash de las 27 tablas de negocio sintéticas: `812a13e9ea33156f55995fcbf287d3512e8e2edd7760721d4ef96f431ea40222`. No se suma esta comprobación al contador de pruebas. No se afirma un hash nuevo de toda la base original: la preservación del original se acredita por aislamiento, alcance de comandos y comparaciones de archivos/contenedores.

## Riesgos residuales y plan de integración

1. Sin prueba SQL autoritativa de rollback, mantener NEEDS_REVIEW y pedir revisión humana; no eliminar archivos huérfanos ni diarios.
2. Bloqueo certificado en Linux y almacenamiento local. NFS, múltiples hosts y productores que no respeten los bloqueos requieren certificación adicional. Los permisos del almacenamiento deben impedir escritores ajenos.
3. Un fallo de persistencia del propio recibo impide acreditar conciliación; conservar cualquier parcial y escalar, sin sobrescribirlo.
4. No se certifica un mecanismo de reparación SQL, restauración ni nueva ejecución del cargue. No se infiere corrección histórica de documentos por superar las pruebas.
5. La integración posterior debe revisar autorización del operador, límites de rutas y cuotas, observabilidad de NEEDS_REVIEW, concurrencia con todos los productores y empaquetado del módulo. Requiere aprobación explícita y nueva distribución; no alterar 11C.
6. Conservar respaldos, manifiestos y proyecto temporal para revisión; su retirada debe decidirse aparte. No se ejecutó prune ni eliminación documental.

## Estados finales

```text
GEOLOGY_RECONCILIATION=PASS
UNCERTAIN_COMMIT=PASS
IDEMPOTENCY=PASS
CONCURRENT_RECONCILIATION=PASS
ORIGINALS_PRESERVED=YES
JOURNALS_PRESERVED=YES
TESTS_PASSED=428
TESTS_FAILED=0
ORIGINAL_DATA_MODIFIED=NO
PRODUCTION_CHANGES=0
NEXT_PHASE=PENDING_APPROVAL
```
