# Plan de rollback local verificado · 14G

El plan se prepara para una ventana futura autorizada. El ensayo 14E verificó la recuperación aislada de GEOLOGY, el rechazo de cuatro pases anteriores y la conservación de filas y archivos. La cuenta histórica continúa pendiente del custodio.

1. Cerrar el ingreso y nuevas publicaciones según el alcance aprobado. Preservar el estado posterior al cambio, incluidos archivos, filas, tareas y diarios, antes de cualquier reversión.
2. Verificar imágenes anteriores por digest, código montado capturado, configuraciones privadas y correspondencia de volúmenes. Comparar esquema, datos y referencias. Si hay diferencias, restaurar y conciliar primero en copia.
3. Preparar Redis nuevo o limpio según la política aprobada. Rotar nuevamente la llave de firma, exigir un nuevo ingreso y comprobar el rechazo de pases anteriores, revocados y emitidos durante TEC-ARCHIVA. No reutilizar un registro antiguo con pases activos.
4. Recuperar GEOLOGY con las imágenes y configuraciones aprobadas. Verificar que la recuperación administrativa custodiada funcione antes de reabrir. El éxito de la cuenta sintética no demuestra acceso histórico.
5. Verificar disponibilidad de originales, partes, derivados, expedidos, datos auxiliares y diarios. Comparar SHA-256, tamaños, referencias SQL y control de diferencias con el estado esperado, incluidas las escrituras posteriores al corte que se deban conservar.
6. Comprobar HTTP, rol, funciones autorizadas y Celery. Suspender la reapertura si se pierde acceso, aparece un hash inexplicado, se reactiva un pase o surgen datos incompatibles.
7. Registrar la decisión, los responsables y las evidencias. Conservar archivos, respaldos, volúmenes e imágenes para conciliación posterior.

GEOLOGY anterior carece de revocación individual. La mitigación ensayada consiste en otro Redis y nueva rotación global antes de reabrir. Una reversión prolongada exige gestionar esa limitación. La ejecución de la CLI sobre el destino debe respetar el cierre pendiente CFG-14G-01.
