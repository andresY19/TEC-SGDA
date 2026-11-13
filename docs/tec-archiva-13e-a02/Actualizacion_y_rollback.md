# Actualización y reversión

1. Registrar los identificadores vigentes de FastAPI y Celery. Verificar respaldo y restauración aislada. Confirmar permisos con datos sintéticos.
2. En una ventana autorizada, suspender nuevos cargues y esperar las tareas en curso. Registrar operaciones inciertas, configuración, colas y volúmenes.
3. Usar los identificadores validados, mantener IA deshabilitada y comprobar el endpoint de estado, los permisos, un cambio de estado con usuario sintético, la revocación y una exportación de seguimiento. La entrega cambia la interfaz y no incluye migraciones.
4. Ante una regresión, suspender nuevos cargues, registrar los envíos aceptados y restablecer imágenes y configuración de 13D. Conservar PostgreSQL, Redis, archivos y diarios. Verificar sesiones, colas, referencias y hashes antes de reabrir. Evaluar por separado las escrituras posteriores al respaldo antes de cualquier restauración.
