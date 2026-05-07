ANALYSIS_NOTES = {
    "resumen_comercial": {
        "title": "Resumen comercial",
        "que_mide": (
            "Resume la actividad comercial de los pedidos filtrados: kilos, cajas, merma, precio medio real, "
            "precio orientativo, desviaciones, pedidos reclamados y cobertura de precios orientativos."
        ),
        "como_se_calcula": [
            "Se excluyen siempre los pedidos con Cancelado = 1.",
            "Precio medio real = SUM(NetoCliente * EurosKG) / SUM(NetoCliente), usando solo lineas con EurosKG > 0 y NetoCliente > 0.",
            "Importe real estimado = SUM(NetoCliente * EurosKG) con EurosKG valido.",
            "Precio medio orientativo = SUM(NetoCliente * precio orientativo final) / SUM(NetoCliente).",
            "Desviacion EUR/kg = precio medio real - precio medio orientativo.",
            "Desviacion total EUR = importe real estimado - importe orientativo.",
        ],
        "datos_usados": (
            "Pedidos.NetoCliente, NetoCoop, Cajas, EurosKG, EurosOrientativos, Reclamado y los campos de agrupacion. "
            "Si no hay EurosOrientativos original valido, se usa el precio calculado de calcdb.PreciosOrientativosCalc "
            "por IdPedidoLora y Linea."
        ),
        "limitaciones": (
            "Los precios reales ignoran lineas sin EurosKG valido. Los precios orientativos pueden quedar a 0 si no hay "
            "precio original ni auxiliar. Las agrupaciones dependen de que las columnas existan y esten informadas."
        ),
        "interpretacion": (
            "Un precio real superior al orientativo indica ventas por encima de la referencia. Una cobertura baja de "
            "orientativos reduce la fiabilidad de la comparacion."
        ),
        "uso_practico": (
            "Sirve para comprobar rapidamente volumen, rentabilidad comercial estimada, desviaciones y calidad de datos "
            "antes de entrar al detalle por cliente, semana, variedad o reclamacion."
        ),
    },
    "clientes": {
        "title": "Clientes",
        "que_mide": (
            "Analiza la contribucion comercial de cada cliente dentro de los filtros activos."
        ),
        "como_se_calcula": [
            "Se aplican filtros globales y se excluyen pedidos Cancelado = 1.",
            "Las metricas de precio real usan media ponderada por NetoCliente y EurosKG valido.",
            "Las reclamaciones combinan el marcado Reclamado del pedido con registros encontrados en DReclamacion.",
            "Los precios orientativos usan primero el valor original y despues el calculado auxiliar si hace falta.",
        ],
        "datos_usados": (
            "Pedidos por cliente, pais, semana, kilos, cajas, EurosKG, precios orientativos y reclamaciones asociadas "
            "por IdPedidoLora y Linea cuando la linea existe."
        ),
        "limitaciones": (
            "Clientes con nombres escritos de forma distinta aparecen separados. Lineas sin EurosKG valido no pesan en "
            "el precio real, aunque sus kilos si pueden aparecer en volumen total."
        ),
        "interpretacion": (
            "Permite ver si el valor de un cliente viene de volumen, de precio medio, de baja merma o de menor incidencia "
            "de reclamaciones."
        ),
        "uso_practico": (
            "Util para priorizar seguimiento comercial, detectar clientes de alto volumen y revisar desviaciones de precio "
            "o reclamaciones recurrentes."
        ),
    },
    "clientes_ranking": {
        "title": "Ranking clientes",
        "que_mide": (
            "Ordena los clientes por importe real estimado y muestra kilos, merma, precios, reclamaciones y origen del "
            "precio orientativo."
        ),
        "como_se_calcula": [
            "Importe real estimado = SUM(NetoCliente * EurosKG) con EurosKG > 0.",
            "Precio medio real = SUM(NetoCliente * EurosKG) / SUM(NetoCliente) para lineas con EurosKG > 0.",
            "La merma se calcula como kg cliente - kg cooperativa.",
            "El pais principal es el pais mas frecuente del cliente dentro de los filtros.",
        ],
        "datos_usados": (
            "Pedidos.Cliente, Pais, NetoCliente, NetoCoop, Cajas, EurosKG, precios orientativos y DReclamacion."
        ),
        "limitaciones": (
            "El ranking por importe favorece a clientes de alto volumen. Para comparar calidad de precio conviene mirar "
            "tambien EUR/kg y desviacion."
        ),
        "interpretacion": (
            "Clientes arriba aportan mas importe estimado. Si tienen desviacion negativa, pueden ser importantes pero "
            "estar por debajo de referencia."
        ),
        "uso_practico": (
            "Ayuda a preparar revisiones comerciales por cliente y priorizar acciones sobre cuentas con mas impacto."
        ),
    },
    "clientes_evolucion": {
        "title": "Evolucion por cliente",
        "que_mide": (
            "Muestra la evolucion semanal de kilos, precio real, precio orientativo e importe por cliente."
        ),
        "como_se_calcula": [
            "Agrupa por cliente y semana agricola.",
            "Precio real semanal = SUM(NetoCliente * EurosKG) / SUM(NetoCliente) con EurosKG valido.",
            "El orden de semanas es agricola: semanas >= 36 aparecen antes, despues continuan las semanas bajas.",
        ],
        "datos_usados": (
            "Pedidos.Cliente, Semana, NetoCliente, EurosKG y precio orientativo final."
        ),
        "limitaciones": (
            "Semanas sin precio real valido muestran precio 0. Cambios de nombre de cliente separan la serie."
        ),
        "interpretacion": (
            "Saltos de precio o volumen ayudan a localizar cambios de comportamiento dentro de una campana."
        ),
        "uso_practico": (
            "Sirve para revisar tendencias por cliente y preparar conversaciones comerciales con contexto temporal."
        ),
    },
    "precios": {
        "title": "Analisis de precios",
        "que_mide": (
            "Compara el precio real ponderado con el precio orientativo ponderado para los pedidos filtrados."
        ),
        "como_se_calcula": [
            "Precio medio real = SUM(NetoCliente * EurosKG) / SUM(NetoCliente), solo con EurosKG > 0 y NetoCliente > 0.",
            "Precio medio orientativo = SUM(NetoCliente * precio orientativo final) / SUM(NetoCliente).",
            "Precio orientativo final = EurosOrientativos original si es mayor que 0; si no, precio calculado auxiliar si existe.",
            "Cobertura orientativa = kg con precio orientativo / kg total.",
        ],
        "datos_usados": (
            "Pedidos.NetoCliente, EurosKG, EurosOrientativos, Semana, VarCoop, Categoria, Calibre y tabla auxiliar "
            "PreciosOrientativosCalc."
        ),
        "limitaciones": (
            "No usa importes de factura, transporte, envases ni fianzas para calcular EUR/kg. Si faltan precios orientativos, "
            "la comparacion pierde cobertura."
        ),
        "interpretacion": (
            "Una diferencia positiva indica precio real por encima del orientativo. Una diferencia negativa indica ventas "
            "por debajo de referencia."
        ),
        "uso_practico": (
            "Permite detectar desviaciones de precio y decidir donde revisar tarifas, clientes, semanas o variedades."
        ),
    },
    "precios_evolucion_semanal": {
        "title": "Evolucion semanal",
        "que_mide": (
            "Muestra la evolucion del precio medio real y orientativo por semana agricola."
        ),
        "como_se_calcula": [
            "Agrupa los pedidos por Semana.",
            "Precio real por semana = SUM(NetoCliente * EurosKG) / SUM(NetoCliente) con EurosKG valido.",
            "Precio orientativo por semana = SUM(NetoCliente * precio orientativo final) / SUM(NetoCliente).",
            "El orden agricola coloca semanas >= 36 al inicio de la campana y continua con las semanas bajas.",
        ],
        "datos_usados": (
            "Pedidos.Semana, NetoCliente, EurosKG, EurosOrientativos y precio auxiliar calculado cuando aplica."
        ),
        "limitaciones": (
            "Semanas con pocos kilos o muchos precios faltantes pueden ser volatiles. La multiseleccion de filtros puede "
            "mezclar realidades comerciales diferentes."
        ),
        "interpretacion": (
            "La separacion entre lineas real y orientativa muestra si la campana esta vendiendo por encima o por debajo "
            "de referencia en cada momento."
        ),
        "uso_practico": (
            "Sirve para detectar semanas atipicas, cambios de mercado y periodos que conviene revisar con mas detalle."
        ),
    },
    "precios_analisis_semana": {
        "title": "Analisis por semana",
        "que_mide": (
            "Tabla de precios, kilos, importes y cobertura orientativa por semana."
        ),
        "como_se_calcula": [
            "Agrupa por Semana con filtros globales activos.",
            "Usa media ponderada con NetoCliente para precio real y orientativo.",
            "Cuenta lineas con orientativo original, calculado o sin datos.",
        ],
        "datos_usados": (
            "Pedidos.Semana, NetoCliente, EurosKG, EurosOrientativos y PreciosOrientativosCalc."
        ),
        "limitaciones": (
            "La semana debe estar informada y ser numerica para que el orden agricola sea correcto."
        ),
        "interpretacion": (
            "Permite comparar semanas entre si y ver si una desviacion procede de precio real, referencia orientativa o cobertura."
        ),
        "uso_practico": (
            "Util para revisar periodos concretos antes de bajar a cliente, variedad o calibre."
        ),
    },
    "precios_variedad_calibre": {
        "title": "Variedad / calibre",
        "que_mide": (
            "Compara precios reales y orientativos por combinacion de VarCoop y Calibre."
        ),
        "como_se_calcula": [
            "Agrupa por Pedidos.VarCoop y Pedidos.Calibre.",
            "Precio medio real = SUM(NetoCliente * EurosKG) / SUM(NetoCliente) con EurosKG valido.",
            "Precio medio orientativo = SUM(NetoCliente * precio orientativo final) / SUM(NetoCliente).",
        ],
        "datos_usados": (
            "Pedidos.VarCoop, Calibre, NetoCliente, EurosKG, EurosOrientativos y tabla auxiliar de orientativos."
        ),
        "limitaciones": (
            "Variedades o calibres sin informar se agrupan como sin dato. Grupos con pocos kilos pueden generar señales debiles."
        ),
        "interpretacion": (
            "Ayuda a distinguir si una desviacion comercial esta concentrada en una variedad o calibre concreto."
        ),
        "uso_practico": (
            "Sirve para revisar precios por producto y preparar decisiones comerciales por calidad/calibre."
        ),
    },
    "precios_desviacion_cliente": {
        "title": "Desviacion por cliente",
        "que_mide": (
            "Compara el precio real de cada cliente contra una referencia ajustada por mezcla de semana, variedad, categoria "
            "y calibre."
        ),
        "como_se_calcula": [
            "Precio medio real = SUM(NetoCliente * EurosKG) / SUM(NetoCliente) usando solo EurosKG > 0 y NetoCliente > 0.",
            "Precio referencia ajustado = media ponderada del precio orientativo final segun semana, variedad, categoria y calibre.",
            "Desviacion EUR/kg = precio real - precio referencia ajustado.",
            "Impacto EUR = desviacion EUR/kg * kg cliente con EurosKG valido.",
            "Si existe equivalencia forfait VALIDADO para el mismo Cultivo, Campaña y Confeccion, se calcula coste de confeccion y margen ajustado.",
            "Impacto ajustado EUR = (precio real - precio referencia ajustado - coste confeccion EUR/kg) * kg con forfait validado.",
            "Ranking = ordenado por impacto EUR de mayor a menor.",
            "Ranking ajustado = ordenado por impacto ajustado EUR, usando solo equivalencias forfait VALIDADO.",
            "Verde = impacto/desviacion positiva; rojo = impacto/desviacion negativa; amarillo = zona neutra.",
        ],
        "datos_usados": (
            "Pedidos.Cliente, Pais, NetoCliente, EurosKG, Semana, VarCoop, Categoria, Calibre, Reclamado y precios "
            "orientativos originales o calculados. Para forfait se usa EquivalenciaForfaitConfeccion enlazada por "
            "Cultivo, Campaña y ConfeccionPedido."
        ),
        "limitaciones": (
            "Si un cliente tiene mezcla de producto muy distinta, la referencia depende de que existan suficientes datos "
            "comparables. Lineas sin EurosKG valido no entran en el precio real ni en el impacto. Si no hay forfait validado, "
            "se informa como SIN_COSTE_FORFAIT y no se inventa coste."
        ),
        "interpretacion": (
            "Impacto positivo indica que el cliente vende por encima de su referencia ajustada. Impacto negativo senala "
            "posible margen perdido o condiciones comerciales por debajo de referencia."
        ),
        "uso_practico": (
            "Prioriza clientes para revisar tarifas, acuerdos, reclamaciones o patrones de venta con impacto economico."
        ),
    },
    "reclamaciones": {
        "title": "Reclamaciones",
        "que_mide": (
            "Resume pedidos y lineas reclamadas, importes reclamados, kilos reclamados, principales clientes y causas."
        ),
        "como_se_calcula": [
            "Se aplican filtros globales y se excluyen pedidos Cancelado = 1.",
            "Una linea entra si el pedido esta marcado como Reclamado = 'S' o si existe registro en DReclamacion.",
            "DReclamacion se vincula por IdPedido y, cuando existe, por Linea.",
            "% pedidos reclamados = pedidos reclamados / pedidos filtrados.",
            "% importe reclamado = importe reclamado / importe real estimado filtrado.",
        ],
        "datos_usados": (
            "Pedidos.IdPedidoLora, Linea, Reclamado, Cliente, Pais, VarCoop, Calibre, Categoria y DReclamacion.Importe, "
            "Neto, Causa, Fecha, Medida y Observaciones."
        ),
        "limitaciones": (
            "Si faltan lineas o importes en DReclamacion, el cruce puede ser parcial. Pedidos marcados como reclamados sin "
            "detalle aparecen sin causa especifica."
        ),
        "interpretacion": (
            "Importes altos o causas repetidas indican puntos de friccion comercial o de calidad que conviene revisar."
        ),
        "uso_practico": (
            "Permite priorizar analisis de incidencias, clientes afectados y causas que mas coste generan."
        ),
    },
    "reclamaciones_por_causa": {
        "title": "Reclamaciones por causa",
        "que_mide": (
            "Agrupa reclamaciones por causa y muestra frecuencia, importe, neto reclamado, clientes y pedidos afectados."
        ),
        "como_se_calcula": [
            "Agrupa DReclamacion.Causa, usando '(Sin causa)' cuando falta informacion.",
            "Suma importe reclamado y neto reclamado dentro de los filtros.",
            "Cuenta clientes y pedidos distintos afectados por cada causa.",
        ],
        "datos_usados": (
            "DReclamacion.Causa, Importe, Neto, IdPedido y datos de Pedidos para filtros y contexto."
        ),
        "limitaciones": (
            "Causas escritas con variantes se mostraran separadas. Registros sin causa se agrupan juntos."
        ),
        "interpretacion": (
            "Una causa con mucho importe o muchos pedidos indica un problema prioritario aunque no sea la mas frecuente."
        ),
        "uso_practico": (
            "Sirve para detectar causas repetitivas y orientar acciones de calidad, logistica o gestion comercial."
        ),
    },
    "reclamaciones_por_cliente": {
        "title": "Reclamaciones por cliente",
        "que_mide": (
            "Muestra reclamaciones agrupadas por cliente, con pais, importe, kilos, pedidos afectados y causa principal."
        ),
        "como_se_calcula": [
            "Agrupa reclamaciones filtradas por cliente.",
            "Suma importe y neto reclamado.",
            "Cuenta pedidos reclamados distintos.",
            "La causa principal es la causa con mayor importe reclamado para ese cliente.",
        ],
        "datos_usados": (
            "Pedidos.Cliente, Pais e IdPedidoLora junto a DReclamacion.Importe, Neto y Causa."
        ),
        "limitaciones": (
            "Clientes con nombres inconsistentes pueden dividirse. Si no hay causa informada, la causa principal puede quedar vacia."
        ),
        "interpretacion": (
            "Clientes con alto importe reclamado o muchas reclamaciones merecen revision comercial y operativa."
        ),
        "uso_practico": (
            "Ayuda a preparar seguimiento de clientes con incidencias y a priorizar acciones correctivas."
        ),
    },
}
