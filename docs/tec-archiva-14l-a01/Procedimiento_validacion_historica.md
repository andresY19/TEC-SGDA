# Procedimiento de validación histórica · 14L

Estado PENDING_VALIDATION. El propietario se declaró custodio. El resultado de ingreso sigue pendiente.

1. Revisar primero si el custodio dispone de evidencia saneada de un ingreso autorizado y aplicable al destino. Cotejar cuenta por referencia, fecha, entorno, rol y función administrativa permitida. Excluir contraseñas, tokens y cabeceras.
2. Si hace falta un ingreso nuevo, detenerse y pedir autorización independiente al propietario. Los originales están detenidos. La solicitud debe precisar IDs, servicios, ventana, alcance del arranque, ingreso, posibles escrituras de autenticación y cierre de la ventana. La aprobación de la política de conciliación queda separada de esta autorización.
3. En el entorno autorizado, el custodio introduce personalmente la credencial y verifica identidad, rol administrativo y una consulta permitida. Si falla el ingreso, cambia el rol o se exige un cambio de contraseña, suspender y registrar el motivo. Cualquier cambio de credencial requiere autorización propia.
4. Registrar fecha, destino, referencia de cuenta, resultado del ingreso, rol, consulta y conformidad del custodio. Usar PASS solo con evidencia suficiente y FAIL solo ante un ensayo autorizado fallido. Mientras no exista evidencia aplicable, conservar PENDING_VALIDATION.

La recuperación sintética de 14H acredita el procedimiento de ensayo. La validación histórica se sustenta en el resultado del custodio.
