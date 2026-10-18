# S7 · Describir imágenes con un CLI en modo headless


## claude

- **grafico_barras.png**: 6.6 s · aciertos 6/6 · coste=0.0009586600000000001 USD, in=4, out=188, subtype=success 
  > Gráfico de barras titulado "Facturas emitidas por mes" con tres meses: Enero (412), Febrero (388) y Marzo (455), destacando Marzo en rojo. Las barras azules representan Enero y Febrero, y la roja, Marzo.
- **diagrama_flujo.png**: 7.5 s · aciertos 4/4 · coste=0.00092526 USD, in=4, out=198, subtype=success 
  > El diagrama titulado "Estados de una factura" muestra un flujo de cuatro estados conectados por flechas: Emitida → Enviada → Vencida → Cobrada. En la parte inferior aparece el texto: "Un recordatorio automático se envía 3 días antes del vencimiento".
- **tabla_planes.png**: 4.8 s · aciertos 5/5 · coste=0.00092836 USD, in=4, out=233, subtype=success 
  > La imagen es una tabla de tres planes de facturación con sus límites y precios: Básico (100 facturas/mes, 1 usuario, 9 €), Profesional (1 000 facturas/mes, 5 usuarios, 29 €) y Empresa (sin límite de facturas ni usuarios, 79 €). Las columnas son Plan, Facturas/mes, Usuarios y Precio.
- **organigrama.png**: 5.3 s · aciertos 4/4 · coste=0.00091966 USD, in=4, out=176, subtype=success 
  > Organigrama de la empresa con un nodo superior "Dirección" (en amarillo) conectado a tres áreas en verde: "Ventas", "Soporte" y "Finanzas". No aparecen números ni datos adicionales.
- **captura_error.png**: 8.5 s · aciertos 2/2 · coste=0.00088296 USD, in=4, out=195, subtype=success 
  > Captura de la aplicación "Aurora - Nueva factura" con el mensaje de error "ERR_4012: el NIF del cliente no es válido. Revise el formato e inténtelo de nuevo." No aparecen números ni datos adicionales más allá del código de error ERR_4012.

**claude**: 6.5 s por imagen de media · palabras clave 21/21 · configuración global sin cambios

## agy

- **grafico_barras.png**: 11.0 s · aciertos 6/6 · usage={"input_tokens": 24712, "output_tokens": 164, "thinking_tokens": 0, "cache_read_tokens": 0, "total_tokens": 24876} 
  > La imagen muestra un gráfico de barras con el título «Facturas emitidas por mes». En el eje horizontal se representan tres meses: «Enero» con una barra azul de valor 412, «Febrero» con una barra azul de valor 388, y «Marzo» con una barra roja destacada de valor 455. El gráfico cuenta con dos ejes perpendiculares de color negro sobre fondo blanco.
- **diagrama_flujo.png**: 10.3 s · aciertos 4/4 · usage={"input_tokens": 24718, "output_tokens": 149, "thinking_tokens": 0, "cache_read_tokens": 0, "total_tokens": 24867} 
  > La imagen muestra un diagrama titulado «Estados de una factura» que describe un flujo secuencial a través de cuatro rectángulos azules conectados por flechas: «Emitida», «Enviada», «Vencida» y «Cobrada». En la parte inferior se incluye la frase explicativa: «Un recordatorio automático se envía 3 días antes del vencimiento».
- **tabla_planes.png**: 10.7 s · aciertos 5/5 · usage={"input_tokens": 24805, "output_tokens": 553, "thinking_tokens": 370, "cache_read_tokens": 0, "total_tokens": 25358} 
  > La imagen muestra una tabla comparativa de planes con las columnas «Plan», «Facturas/mes», «Usuarios» y «Precio». El plan «Básico» incluye 100 facturas al mes y 1 usuario por un precio de 9 €. El plan «Profesional» ofrece 1 000 facturas al mes y 5 usuarios por 29 €. Por último, el plan «Empresa» cuenta con facturas/mes «Sin límite» y usuarios «Sin límite» por 79 €.
- **organigrama.png**: 7.5 s · aciertos 4/4 · usage={"input_tokens": 24671, "output_tokens": 172, "thinking_tokens": 0, "cache_read_tokens": 0, "total_tokens": 24843} 
  > La imagen muestra un organigrama empresarial con un nodo superior de color amarillo claro que indica «Dirección». De este nodo se ramifican tres departamentos en recuadros de color verde claro: «Ventas» a la izquierda, «Soporte» en el centro y «Finanzas» a la derecha. En la parte inferior de la imagen figura el texto descriptivo «Organigrama de la empresa». No aparecen números ni datos cuantitativos adicionales en el gráfico.
- **captura_error.png**: 9.0 s · aciertos 2/2 · usage={"input_tokens": 24724, "output_tokens": 152, "thinking_tokens": 0, "cache_read_tokens": 0, "total_tokens": 24876} 
  > La imagen muestra un mensaje de error con texto en color granate sobre un fondo rosa claro. En la parte superior aparece el encabezado "Aurora - Nueva factura". Debajo se indica el código y mensaje de error "ERR_4012: el NIF del cliente no es válido". Finalmente, incluye la instrucción: "Revise el formato e inténtelo de nuevo.".

**agy**: 9.7 s por imagen de media · palabras clave 21/21 · configuración global sin cambios
