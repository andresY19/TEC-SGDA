# Modelo de autorización de conciliación

## Frontera de confianza

El equipo anfitrión y su operador Docker autorizado verifican los recursos y custodian los archivos de autoridad. FastAPI y Celery carecen del socket Docker y de claves privadas de autorización. La política pública se monta en solo lectura, con propietario root, en /run/secrets/reconciliation-policy.json. El directorio anfitrión del ensayo tiene ACL limitada al usuario y SYSTEM. El acceso administrativo al motor forma parte de esta frontera de confianza. [Seguridad de Docker Engine](https://docs.docker.com/engine/security/)

Se usan firmas Ed25519 mediante cryptography 50.0.2, ya fijada en las dependencias, y la API criptográfica nativa de Node para las operaciones del anfitrión. La aplicación recibe únicamente claves públicas. La llave de autorización y la llave de atestación son distintas. [Documentación de Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/)

## Política y recursos

La política fija propósito, claves públicas, ejecutores permitidos, raíces de almacenamiento, plazo máximo y recursos reales. La fotografía incluye IDs completos e imágenes de PostgreSQL, Redis, FastAPI y Celery, huellas de sus configuraciones, redes y direcciones, volúmenes con metadatos de creación, identificador del cluster PostgreSQL y testigos de almacenamiento por dispositivo e inodo.

El ejecutor comprueba las identidades antes de abrir una conexión de comprobación. La resolución del servidor PostgreSQL configurado debe coincidir con las direcciones del PostgreSQL autorizado. Las conexiones de la comprobación y de la conciliación se fijan a esa dirección para evitar depender de un cambio superficial de alias. El rol de aplicación se comprueba sin facultades de superusuario, creación de roles o bases, replicación o bypass de RLS.

En propósito rehearsal, cualquier coincidencia con los IDs protegidos de contenedores, volúmenes o redes del original impide la operación. Un nombre distinto no cambia esa comparación. La política del clon y sus permisos no sirven como política del original. Una operación futura sobre el destino requiere su aprovisionamiento separado, propósito operation, recursos verificados y nuevas claves y permisos específicos aprobados. En 14H no se provisiona ni se emite esa autorización.

## Permiso limitado y ejecución

1. La autoridad verifica la fotografía real y firma un permiso para reconcile, un contenedor, una raíz, una operación y una huella de sus evidencias. El permiso admite un solo consumo y vence como máximo a los cinco minutos.
2. El ejecutor verifica firma, finalidad, caducidad, alcance y coincidencia actual de los recursos y evidencias.
3. La CLI genera un desafío criptográfico nuevo e informa PID, inicio del proceso, namespace de montaje y huella de política. Todavía no concilia ni accede a PostgreSQL.
4. El ejecutor vuelve a comprobar recursos. Consume el permiso mediante una inserción única en un ledger SQLite del anfitrión, con transacción y synchronous=FULL. El consumo se confirma antes de entregar la atestación.
5. Una segunda firma vincula permiso, recursos y evidencias al desafío exacto del proceso. Su validez máxima es de treinta segundos. Una respuesta capturada no funciona en otro proceso.
6. La CLI comprueba ambas firmas, sus ventanas, su política protegida, su desafío y los testigos actuales. Solo entonces invoca el dominio con sesiones restringidas. Sin autorización, una confirmación genérica o FORCE=true no habilitan la operación.
7. El ejecutor conserva auditoría inicial y final, resultados y hashes. La conciliación mantiene sus propios recibos inmutables y no realiza entregas, regeneraciones ni borrados automáticos.

## Fallos y concurrencia

La clave única del ledger impide consumir dos veces un permiso. Dos permisos distintos pueden referirse a la misma operación y el bloqueo de dominio conserva la exclusión. La idempotencia corresponde a la operación y sus recibos; cada nuevo intento requiere otro permiso.

Si se interrumpe el proceso después del consumo, el permiso permanece consumido. Un registro sin resultado exige revisión de las evidencias. No se libera ni se reutiliza automáticamente. La indisponibilidad de inspección, verificación, PostgreSQL o auditoría produce rechazo o revisión pendiente. La ausencia SQL por sí sola no se transforma en un rollback demostrado.

El permiso tiene un plazo de inicio limitado; la ejecución controlada también tiene timeout. El modelo presupone que el operador autorizado mantiene estable la configuración Docker durante la operación. Los cambios posteriores exigen nueva comprobación y nuevo permiso.

