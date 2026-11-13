# Plan de rollback local pendiente de autorización

1. Cerrar entradas y nuevas publicaciones. Preservar las escrituras, documentos y diarios posteriores al corte para evitar perder trabajo.
2. Comparar esquema y datos con la referencia de reversión. Verificar las imágenes anteriores, código montado y configuración capturada. Si se requiere restaurar, hacerlo primero sobre una copia y conciliar las diferencias antes de autorizar el destino.
3. Usar un Redis limpio y otra llave de firma. Exigir nuevo ingreso y comprobar que los pases anteriores, revocados y emitidos por la candidata son rechazados. La versión anterior no proporciona revocación individual.
4. Confirmar acceso del custodio y, si corresponde, su recuperación aprobada. Verificar rol, permisos, salud HTTP, Celery, referencias SQL, hashes y disponibilidad documental.
5. Conservar volúmenes, respaldos, imágenes y evidencia. Mantener cerrada la ventana si falla cualquier comprobación crítica. Acordar seguimiento de la limitación de sesiones durante una reversión prolongada.

La reversión real requiere autorización expresa. La evidencia sintética no sustituye la comprobación de la cuenta histórica.
