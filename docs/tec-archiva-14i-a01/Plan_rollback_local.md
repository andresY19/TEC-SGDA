# Plan de rollback local

El ensayo aislado 14E acreditó recuperación GEOLOGY, conservación de 63 archivos y rechazo de cuatro pases previos tras la nueva rotación. El plan se cotejó con ese ensayo en 14I. La ejecución sobre el destino requiere aprobación expresa.

1. Mantener cerrado el acceso y detener publicaciones según la ventana aprobada. Conservar el estado posterior al corte, incluidas las escrituras, archivos, tareas, diarios y recibos. Cotejar las operaciones inciertas antes de repetirlas.
2. Cotejar el esquema y los datos con el respaldo al corte. Recuperar las imágenes y configuraciones previas verificadas. Si hay divergencias, restaurar primero en una copia, conciliar las escrituras posteriores y aprobar su tratamiento antes de intervenir el destino.
3. Deshabilitar el ejecutor de conciliación de rc.3 para el destino revertido y conservar su ledger y evidencias. Cualquier futura operación bajo otra identidad requiere una política y permiso específicos.
4. Preparar Redis nuevo o limpio y rotar nuevamente la llave de firma. Exigir nuevo ingreso y probar que se rechazan los pases previos, revocados y emitidos por la candidata. GEOLOGY anterior carece de revocación individual.
5. Recuperar los servicios aprobados y comprobar el ingreso del custodio, su rol, la salud HTTP y Celery. Verificar esquema, filas, referencias SQL, hashes de originales, partes, derivados y expedidos, hojas auxiliares y trazabilidad.
6. Mantener el acceso cerrado ante pérdida de acceso administrativo, reaparición de pases, referencias rotas o hashes inexplicados. Registrar aceptación, responsables y evidencia antes de reabrir.

El rollback documental probado en 14H cubre la transacción de conciliación. La reversión entre versiones se sustenta en el ensayo de 14E, sin nueva ejecución durante 14I.
