# TEC-ARCHIVA 13G

Resultado **PASS**. Candidata aislada geology-auto11e-a11y13g-full-a5118e9e, disponible en http://127.0.0.1:18095/app. La verificación comprobó los hashes de 13E, las evidencias 13F y el respaldo protegido. Se preservaron las imágenes certificadas y los recursos de 202 contenedores preexistentes.

## Correcciones

- **Menú móvil.** El evento de medios se coordina con el punto de corte que ya observó la interacción. La misma aserción falló en el código de 13E y pasó diez veces con 13G. El recorrido adicional observó 0 interrupciones en 6 cambios de ancho. También verificó Enter, Space, Escape, salida con Tab y recuperación de foco al cruzar el punto de corte.
- **Hoja de control.** Las filas nuevas y existentes reciben etiquetas para folio inicial, folio final, radicado y observaciones. Los mensajes se vinculan al campo correspondiente y el resumen se anuncia como estado. Se verificaron varios mensajes sobre un campo y su retiro al limpiar la validación. El alcance del código se limitó a la interfaz.

## Certificación

- Referencia: 768 aprobadas, 0 fallidas y 0 bloqueadas de 768.
- Pruebas nuevas: 15 aprobadas y 0 fallidas. La falla esperada de 13E sirve de control y no se cuenta como falla de 13G.
- Recorrido: 135 combinaciones de vista, perfil y tamaño, con 0 desbordamientos de página. Se comprobaron RBAC, revocación, cargue, división, PDF/A con veraPDF, conciliación, rollback y conservación de originales.
- Axe-core: 40 análisis, 0 infracciones detectadas y 7 resultados para revisión manual. WCAG 2.2 AA permanece sin certificar. Quedan pendientes NVDA, Chrome nativo, zoom real, reflow integral y revisión manual. La inspección visual todavía muestra compresión en las etiquetas del encabezado de metadatos de Hoja de control en móvil; esa fila queda fuera de los cuatro campos corregidos.

Los ensayos técnicos se ejecutaron sobre a01. La revisión de a02 reveló ocho aserciones fallidas de reflow. Las etiquetas visualmente ocultas desbordaban el área desplazable. La variante final a03 las ancla dentro de sus celdas; el navegador volvió a comprobar que el desplazamiento se limita a la tabla. Se conservaron las evidencias de a02. Se repitió la sonda de cambio de ancho de a03 porque su escucha inicial capturó el resize anterior; la repetición verifica la entrega del evento de escritorio antes de armar la apertura móvil. Los archivos Python son idénticos entre variantes.

- [Matriz de defectos](Matriz_defectos.json)
- [Matriz de pantallas](Matriz_pantallas.md)
- [Matriz de perfiles](Matriz_perfiles.json)
- [Diagnóstico móvil](Diagnostico_movil.json)
- [Resultados](resultado13g.json)
- [Manifiesto](Manifiesto_candidata.json)
- [Actualización y reversión](Actualizacion_y_rollback.md)

## Capturas

![consulta-movil](capturas/consulta-movil.png)
![hoja-control-escritorio](capturas/hoja-control-escritorio.png)
![hoja-control-tableta](capturas/hoja-control-tableta.png)
![hoja-validacion-movil](capturas/hoja-validacion-movil.png)
![menu-teclado-movil](capturas/menu-teclado-movil.png)
