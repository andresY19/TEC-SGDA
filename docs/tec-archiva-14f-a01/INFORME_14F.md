# TEC-ARCHIVA · Cierre técnico 14F

**Preparación técnica READY. Autorización de actualización NOT_GRANTED. Decisión NO_GO mientras se completan las comprobaciones del custodio y la aprobación de la ventana.** El acceso histórico permanece PENDING_CUSTODIAN. La fase se cierra como PARTIAL por esa validación externa pendiente.

## Candidata y CLI

Se creó la distribución derivada `distribution/tec-archiva-2.13.0-rc.2-14f`, identificada como `2.13.0-rc.1+14f.2`. Las imágenes nuevas incorporan la corrección en las dos ubicaciones de la CLI. El único cambio funcional está en la confirmación explícita del proyecto local. La lógica archivística y el módulo de conciliación conservan sus hashes. La base, las rutas API y las dependencias se mantienen compatibles con la RC.

La CLI anterior rechazaba el contexto de 14E por su nombre, con código 1. La opción --local-project permite confirmar un contexto local coincidente. La CLI exige IA deshabilitada y conserva el bloqueo explícito del proyecto original. La futura operación debe usar el contexto local aprobado y verificado en el preflight. Si se decide conservar el identificador original para ejecutar la CLI, ese cambio del guardia requiere una intervención y certificación independientes antes del GO.

Pasaron nueve comprobaciones específicas de CLI y las 31 comprobaciones existentes de conciliación e integración. Se verificaron éxito, idempotencia, bloqueo concurrente, recibos inmutables, conservación de archivos, revisión humana y rollback. La confirmación del operador complementa la inspección externa de IDs, redes, volúmenes y conexiones.

## Regresión final

Se ejecutaron nuevamente las **804 comprobaciones de referencia**, con 804 aprobadas, cero fallidas, cero omitidas, cero bloqueadas y cero no aplicables. Incluyen 321 pruebas unitarias del repositorio, 13 de integración PDF/A, 449 comprobaciones automatizadas de operación e interfaz y 21 controles de permisos SQL y almacenamiento.

Se aprobaron además diez pruebas unitarias nuevas de CLI, nueve comprobaciones de ejecución de CLI y un ensayo agrupado de recuperación administrativa sintética. **Total final 824 aprobadas y cero fallidas.** Los resultados históricos y los intentos preliminares no se sumaron como aprobaciones de esta ejecución.

Una prueba nueva cargaba SQLAlchemy antes de que una prueba existente fijara su configuración. Se corrigió el aislamiento del test. El transporte de navegador necesitó adaptar la continuación de peticiones y conservar los bytes del multipart. Se verificó el hash del PDF cargado contra el archivo seleccionado. Estos cambios afectaron al arnés, sin modificar el frontend ni las reglas del producto. Los intentos previos y sus fallos recuperados se conservaron.

## Aislamiento e integridad

El entorno final fue `geology-auto11e-a11y14f-full-88e7e689`, con PostgreSQL, Redis ACL/AOF, almacenamiento, usuarios y secretos propios. Las pruebas de interfaz usaron HTTP interno transmitido por tuberías del proceso Docker, sin publicar puertos. Las intercepciones sintéticas de errores y carga del arnés se mantuvieron documentadas.

Los cuatro contenedores originales conservaron IDs, imágenes, montajes y estado detenido. Se excluyó por identidad el auxiliar heredado de 14D. Los volúmenes PostgreSQL y Redis conservaron las mismas huellas SHA-256 de las capturas 14E al auditarlos mediante montajes de solo lectura. También coincidieron los archivos del host y la configuración original. La RC original, las imágenes certificadas y los respaldos protegidos conservaron sus huellas. La auditoría de lectura no creó un respaldo al corte.

## Administración, sesiones y condiciones finales

El ensayo sintético restableció una cuenta administradora nueva, rechazó la contraseña anterior, impuso el cambio provisional y recuperó los permisos de administración. La sesión anterior quedó revocada. La cuenta histórica conserva sus datos y requiere la verificación de su custodio mediante el checklist.

La política exige cierre general, firma nueva, registro limpio, Redis autenticado con AOF, nuevo ingreso y otra rotación si se revierte. No depende de contar los pases originales. Los secretos sintéticos quedan excluidos de la actualización real.

El procedimiento de respaldo al corte está preparado y **no se ejecutó**. Debe aplicarse inmediatamente antes del cambio autorizado y demostrar restauración e integridad. El plan de actualización y el de reversión permanecen sujetos a autorización expresa. No existen defectos funcionales críticos abiertos dentro de la cobertura ejecutada. La validación institucional y la revisión manual de accesibilidad conservan sus pendientes previos.

