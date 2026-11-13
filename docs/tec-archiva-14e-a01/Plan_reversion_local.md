# Reversión local pendiente de aprobación

1. Cerrar acceso y detener publicaciones. Preservar el estado posterior al corte, incluidas escrituras, documentos y diarios. Identificar imágenes y configuración de reversión.
2. Verificar el catálogo contra la referencia y conservar el conjunto de datos posterior si es compatible. Restaurar únicamente en copia cuando haya diferencias o se requiera una reconciliación de escrituras.
3. Usar Redis limpio y una tercera llave de firma. Probar el rechazo de pases de GEOLOGY previos, de pases de la RC y de pases revocados. El código anterior no admite revocación individual.
4. Verificar acceso administrativo custodiado, endpoints, lectura documental, catálogo, referencias, hashes y ping Celery. Mantener bloqueada la reapertura si se pierde acceso o reaparece una sesión.
5. Conservar respaldos, volúmenes, contenedores y evidencias. Gestionar la limpieza con una autorización independiente.
