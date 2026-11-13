# TEC-ARCHIVA · Preflight final 14G

**Decisión NO_GO. Preparación técnica NOT_READY para el destino indicado.** El preflight es PARTIAL y la autorización continúa NOT_GRANTED. Se identificó el bloqueo CFG-14G-01 y el acceso histórico permanece PENDING_CUSTODIAN.

## Identidad e integridad

Los cuatro contenedores originales se verificaron por sus IDs completos, imágenes, estado, marcas de tiempo, montajes, volúmenes y redes. Continúan detenidos y sus recursos observados coinciden con la referencia de 14F. El auxiliar 14D se excluyó por ID, red deshabilitada y volumen sintético, pese a sus etiquetas heredadas.

Se comprobaron hashes de los archivos del host, de la configuración original y del código montado. Los volúmenes originales conservan identidad, metadatos y ausencia de contenedores activos. Sus bytes no se volvieron a leer en 14G; la última verificación completa de sus huellas corresponde a 14F. Las operaciones de esta fase fueron de inspección y creación de informes.

La candidata conserva los 172 hashes verificados de su manifiesto, las imágenes por digest, la configuración de Redis ACL/AOF y el rol PostgreSQL restringido certificados. Se verificaron los archivos de evidencia de las **824 comprobaciones aprobadas en 14F**. Se ejecutaron cero pruebas de aplicación en 14G. La auditoría documental no se contabiliza como otra ejecución de esa regresión.

## Bloqueo del destino

La candidata rc.2 se identifica internamente como 2.13.0-rc.1+14f.2. En codigo/reconcile_documents.py, línea 25, rechaza explícitamente GEOLOGY_LOCAL_PROJECT=geology-local-20261106-57a99a, incluso cuando --local-project coincide. El contexto certificado en 14F fue geology-restore14f-cli.

Esta observación limita el READY de 14F al ensayo aislado. Para el proyecto destino actual falta cerrar y certificar el mecanismo de ejecución de conciliación. El plan registra el cierre requerido antes de autorizar cambios. La candidata se conserva intacta.

## Custodio y sesiones

No se contó con participación ni evidencia de acceso del custodio durante esta fase. Los servicios originales están detenidos y su inicio requiere autorización independiente. El checklist documenta identidad, ingreso autorizado, rol, funciones permitidas, cambio obligatorio cuando aplique y recuperación aprobada. No se solicitó ni registró ninguna contraseña.

La política de sesiones conserva cierre general, llave nueva, registro limpio, Redis autenticado y persistente y nuevo ingreso. La reversión exige otra rotación y verificación del rechazo de pases previos. El procedimiento no depende de contar sesiones originales. La recuperación sintética de 14F sigue acreditada; el acceso histórico no se declara aprobado.

## Respaldo y capacidad

Los cinco archivos públicos del manifiesto del respaldo 14E y las configuraciones privadas protegidas conservaron sus huellas. La ACL del destino en C: sigue protegida y limitada al operador y SYSTEM. La cobertura incluye PostgreSQL, Redis, depósito, expedidos, datos, configuración, código y metadatos de recuperación. Se revalidó la evidencia de restauración y rollback de 14E.

El espacio observado es C: 173.47 GiB, D: 15.14 GiB y F: 23.31 GiB. El trabajo base conocido de captura y copias de verificación se estima en 149.41 MiB, excluidos el crecimiento futuro, WAL adicional y nuevas evidencias. La capacidad disponible cubre ampliamente esa carga conocida. La medición y reserva definitiva deben renovarse inmediatamente antes del corte.

El procedimiento al corte está READY. Su futuro directorio exclusivo debe crearse y protegerse dentro de la ventana autorizada. **El respaldo al corte no se ejecutó ni se declara existente.**

## Plan y puntos de suspensión

Plan_cambio_local.md define las diez etapas desde autorización hasta aceptación o rollback y sus condiciones de suspensión. Plan_rollback_local.md verifica recuperación de GEOLOGY, Redis limpio, nueva firma, acceso administrativo, conservación documental, hashes y rechazo de pases antiguos.

Para reconsiderar GO se requieren el cierre de CFG-14G-01 y la validación del custodio. La ejecución posterior requiere autorización expresa y respaldo al corte verificado. Los siete entregables de 14G contienen el inventario saneado, evidencias y matriz de decisión.
