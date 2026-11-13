# TEC-ARCHIVA 2.13.0-rc.1 Â· Fase 14E

**Resultado parcial.** Se verificaron el respaldo actual, la restauraciÃ³n, la actualizaciÃ³n funcional y la reversiÃ³n en un entorno aislado. La aceptaciÃ³n operativa queda condicionada a que el custodio pruebe el acceso con la cuenta administrativa histÃ³rica o apruebe su recuperaciÃ³n en una copia autorizada. La CLI de conciliaciÃ³n restringe el prefijo de proyecto; el mecanismo de dominio se verificÃ³ con los mÃ³dulos incorporados y sin alterar la candidata.

## Captura y restauraciÃ³n

La evidencia corresponde al proyecto `geology-restore14e-a01`. Los cuatro contenedores originales ya estaban detenidos. Se excluyÃ³ el auxiliar 14D por ID completo, red y montaje. Las capturas fÃ­sicas se hicieron con montajes de solo lectura y sin red. PostgreSQL 15.19 (Debian 15.19-1.pgdg13+2) recuperÃ³ el WAL sobre un volumen nuevo. Se generÃ³ un dump lÃ³gico y se restaurÃ³ en otro volumen con la misma versiÃ³n, en una transacciÃ³n. Las dos copias coinciden en catÃ¡logo, conteos y huellas de filas. Redis recuperÃ³ AOF en una copia sin red. Ese Redis se mantuvo fuera de las fases de aplicaciÃ³n.

Se verificaron 27 tablas, 26 filas, nueve trazas, nueve referencias SQL a archivos, 17 documentos del depÃ³sito, 43 expedidos y tres hojas auxiliares. Las 17 huellas histÃ³ricas coinciden con la captura actual. Se preservaron configuraciÃ³n, metadatos de contenedores y cÃ³digo montado para reversiÃ³n en C: bajo acceso restringido. La captura incluye datos de autenticaciÃ³n y exige conservar esa restricciÃ³n.

## ActualizaciÃ³n simulada

La RC arrancÃ³ sin publicar puertos, con UID/GID 10001:10001 y el rol limitado de 14D. Se aplicÃ³ ACL de Redis con AOF y se probÃ³ el rechazo de un pase GEOLOGY previo. La cuenta administrativa de ensayo pudo iniciar sesiÃ³n. Las pruebas verificaron RBAC, rechazo tras logout, cambio de contraseÃ±a y desactivaciÃ³n. Se comprobaron 12 rutas internas de lectura y seis denegaciones SQL. Celery procesÃ³ documentos sintÃ©ticos, veraPDF validÃ³ ambos perfiles y la conciliaciÃ³n produjo un recibo idempotente. La prueba de reemplazo corrupto conservÃ³ los archivos y las referencias previas.

## ReversiÃ³n

Se iniciÃ³ GEOLOGY en el mismo entorno aislado usando el cÃ³digo capturado, una tercera llave de firma y un Redis nuevo y vacÃ­o. Los cuatro pases previos de prueba fueron rechazados. El administrador sintÃ©tico volviÃ³ a ingresar y Celery respondiÃ³ a ping. Las 26 filas restauradas y los 63 archivos conservaron sus huellas. Se mantuvieron los registros sintÃ©ticos generados durante el ensayo. GEOLOGY anterior sigue usando pases sin revocaciÃ³n individual. La rotaciÃ³n mitigÃ³ la reactivaciÃ³n durante el cambio de versiÃ³n.

Se aprobaron **379 comprobaciones**. Incluyen 352 pruebas repetidas de la referencia, 18 sondeos HTTP/SQL y nueve controles agrupados de 14E. La regresiÃ³n histÃ³rica restante y la credencial administrativa histÃ³rica no se contabilizaron como aprobadas.

**NO_GO.** Los servicios originales siguen detenidos y el ensayo queda conservado para verificaciÃ³n. El preflight final debe resolver el acceso administrativo custodiado, formalizar el procedimiento de conciliaciÃ³n y revisar la exposiciÃ³n de sesiones durante una reversiÃ³n prolongada.
