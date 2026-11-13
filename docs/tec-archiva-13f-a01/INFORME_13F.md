# TEC-ARCHIVA 13F

Resultado **PARTIAL**. Entorno sintético geology-auto11e-a11y13f-full-1d91af86, disponible en http://127.0.0.1:18094/app. Se ejecutaron las imágenes exactas certificadas en 13E. El manifiesto comprueba el código incorporado, la configuración aislada, los volúmenes propios y la protección de 196 contenedores preexistentes. La fase mantuvo IA deshabilitada.

## Regresión y recorrido

- Referencia: 607 aprobadas, 0 fallidas y 0 bloqueadas de 607.
- Transversal: 161 aprobadas y 0 fallidas. 135 observaciones de pantallas y 15 comprobaciones de menú y API por perfil y ancho.
- Cobertura documental: conservación del original, cargue, duplicados, PDF/A, veraPDF, conciliación, restauración de servicios y rollback. Los resultados de sesiones comprueban desactivación, logout y revocación.
- Identidad: se verificaron los cinco colores y el nombre comercial. El inventario distingue las vistas y estados cubiertos.

## Móvil y accesibilidad

El ensayo controlado reprodujo el cierre del menú inmediatamente después de abrirlo durante el cambio de ancho. La traza separa la apertura por clic del reinicio de estado del evento de medios. El caso espontáneo registró el cierre un milisegundo después de abrir, seguido de foco en el cuerpo de la página. El manejador de cambio de medios restablece el menú cerrado; el ensayo controlado confirmó el mismo orden. Las repeticiones directas parten del ancho móvil y ejercitan Enter y Escape.

Se registraron 0 desbordamientos. La reproducción instrumentó el evento de consulta de medios, el clic, los cambios de foco y la expansión. Hubo 1 aperturas interrumpidas en 6 cambios de ancho. La prueba de cuentas retuvo la respuesta HTTP de forma controlada y midió los objetivos antes y después de cargar la tabla. Los registros detallan la secuencia observada y los límites de atribución respecto a 13E. La medición posterior a la carga comprobó el tamaño de los controles; el fallo histórico de medición por sí solo no identifica su causa. Antes de completar la consulta controlada no había casillas en la tabla. Tras completarla, las 24 casillas midieron al menos 24 × 24 píxeles CSS; cuatro revisitas conservaron ese tamaño.

Axe-core ejecutó 18 escaneos de referencia y 19 adicionales. Quedan pendientes NVDA, Chrome nativo, zoom real, reflow integral y revisión manual. **WCAG 2.2 AA sin certificar**. El recorrido certifica el comportamiento observado y conserva los defectos de la versión evaluada para una fase correctiva. Se documentaron los hallazgos sobre la misma imagen certificada, sin aplicar correcciones.

- hojas · label · 4 objetivo(s)

## Fallos transversales

Sin fallos en las aserciones transversales.

Las pruebas de diagnóstico pasaron cuando registraron la secuencia esperada. Los defectos que revelaron se contabilizan como hallazgos de certificación y determinan el resultado de navegación, responsive y accesibilidad.

## Entregables

- [Matriz de pantallas](Matriz_pantallas.md)
- [Matriz de perfiles](Matriz_perfiles.json)
- [Diagnóstico móvil](Diagnostico_movil.json)
- [Hallazgos y selectores](Hallazgos.json)
- [Resultados](resultado13f.json)
- [Manifiesto](Manifiesto_candidata.json)
- [Actualización y reversión](Actualizacion_y_rollback.md)

## Capturas representativas

![avance-movil](capturas/avance-movil.png)
![ayuda-movil](capturas/ayuda-movil.png)
![cargue-tableta](capturas/cargue-tableta.png)
![consulta-movil](capturas/consulta-movil.png)
![contrato-cargado-tableta](capturas/contrato-cargado-tableta.png)
![cuentas-movil](capturas/cuentas-movil.png)
![inicio-escritorio](capturas/inicio-escritorio.png)
![login-escritorio](capturas/login-escritorio.png)
![planeacion-tableta](capturas/planeacion-tableta.png)
