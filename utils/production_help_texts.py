PRODUCTION_FIELD_HELP = {
    "horas_turno": {
        "title": "Horas por turno",
        "description": "Número de horas previstas para cada turno operativo.",
        "example": "8 horas.",
        "impact": "Se usa para calcular las horas brutas disponibles del día.",
    },
    "numero_turnos": {
        "title": "Número de turnos",
        "description": "Cantidad de turnos productivos previstos para la jornada.",
        "example": "1 turno normal o 2 turnos en campaña alta.",
        "impact": "Multiplica la capacidad diaria disponible.",
    },
    "horas_descanso": {
        "title": "Horas de descanso",
        "description": "Tiempo no productivo previsto dentro de la jornada total.",
        "example": "0.5 equivale a 30 minutos.",
        "impact": "Se descuenta de las horas brutas para calcular las horas útiles.",
    },
    "tipo_campana": {
        "title": "Tipo de campaña",
        "description": "Nivel general de actividad del almacén.",
        "example": "Normal, Alta o Pico campaña.",
        "impact": "Puede servir después para ajustar rendimientos y saturaciones recomendadas.",
    },
    "tipos_volcado_activos": {
        "title": "Líneas de volcado activas",
        "description": "Indica qué líneas o formas de entrada de fruta estarán disponibles durante la jornada. No es una opción excluyente: pueden estar activas varias a la vez.",
        "example": "Compacta + Línea invierno si ambas se van a utilizar el mismo día.",
        "impact": "Estas líneas condicionan la capacidad de entrada de fruta, la continuidad de trabajo y posibles cuellos de botella. En fases posteriores se cruzarán con máquinas, rendimientos y saturación.",
    },
    "saturacion_maxima_pct": {
        "title": "Saturación máxima %",
        "description": "Porcentaje máximo recomendable de ocupación de la capacidad disponible.",
        "example": "90%.",
        "impact": "Evita planificar al 100% permanente, dejando margen para paradas, cambios y retrasos.",
    },
    "permitir_horas_extra": {
        "title": "Permitir horas extra",
        "description": "Indica si la simulación podrá considerar ampliación de jornada.",
        "example": "Activado en días de mucho pedido.",
        "impact": "Permite cubrir déficit de capacidad sin aumentar turnos.",
    },
    "permitir_segundo_turno": {
        "title": "Permitir segundo turno",
        "description": "Indica si puede proponerse un segundo turno como solución.",
        "example": "Activado en pico de campaña.",
        "impact": "Aumenta la capacidad diaria disponible, pero requiere personal y organización adicional.",
    },
    "priorizar_pedidos_reales": {
        "title": "Priorizar pedidos reales",
        "description": "Da preferencia a pedidos confirmados frente a pedidos previstos.",
        "example": "Activado por defecto.",
        "impact": "Reduce el riesgo de consumir capacidad en pedidos no firmes.",
    },
    "permitir_adelantar_produccion": {
        "title": "Permitir adelantar producción",
        "description": "Permite producir antes de la fecha límite si hay capacidad libre.",
        "example": "Adelantar pedidos de mañana cuando hoy sobra capacidad.",
        "impact": "Ayuda a suavizar picos de carga y reducir riesgo de retrasos.",
    },
    "agrupar_pedidos_compatibles": {
        "title": "Agrupar pedidos compatibles",
        "description": "Permite considerar juntos pedidos similares por confección, formato, cliente o plataforma.",
        "example": "Agrupar varias mallas de 2 kg del mismo cliente.",
        "impact": "Reduce cambios de máquina, material y etiqueta.",
    },
    "minimizar_cambios_formato": {
        "title": "Minimizar cambios de formato",
        "description": "Prioriza una planificación con menos cambios de kg, material, malla o configuración.",
        "example": "Hacer primero todas las mallas de 2 kg antes de cambiar a 1.5 kg.",
        "impact": "Mejora rendimiento real y reduce tiempos muertos.",
    },
    "kg_objetivo_dia": {
        "title": "Kg objetivo día",
        "description": "Kilos totales que se desea producir en la jornada.",
        "example": "80.000 kg.",
        "impact": "Sirve como referencia contra la capacidad estimada.",
    },
    "palets_objetivo_dia": {
        "title": "Palets objetivo día",
        "description": "Número de palets que se espera preparar durante la jornada.",
        "example": "240 palets.",
        "impact": "Ayuda a prever carga de paletizado, flejado y expedición.",
    },
    "pedidos_maximos_recomendados": {
        "title": "Pedidos máximos recomendados",
        "description": "Número máximo orientativo de pedidos que conviene gestionar en el día.",
        "example": "40 pedidos.",
        "impact": "Controla la fragmentación operativa y los cambios excesivos.",
    },
    "horas_brutas_dia": {
        "title": "Horas brutas día",
        "description": "Resultado de multiplicar horas por turno por número de turnos.",
        "example": "8 horas x 1 turno = 8 horas.",
        "impact": "Indica la capacidad horaria teórica antes de descontar descansos.",
    },
    "horas_utiles_dia": {
        "title": "Horas útiles día",
        "description": "Horas realmente disponibles tras descontar descansos.",
        "example": "8 - 0.5 = 7.5 horas.",
        "impact": "Es la base real para calcular capacidad productiva.",
    },
    "saturacion_util_objetivo": {
        "title": "Saturación útil objetivo",
        "description": "Horas útiles ajustadas por el porcentaje máximo de saturación.",
        "example": "7.5 horas x 90% = 6.75 horas.",
        "impact": "Representa la capacidad planificable recomendada sin forzar el almacén.",
    },
}

PRODUCTION_PERSONAL_HELP = {
    "personal_total": {"title": "Personal disponible total", "description": "Número total de personas disponibles para la jornada.", "example": "80 personas.", "impact": "Sirve como referencia global para comparar plantilla disponible frente a plantilla recomendada."},
    "personal_directo": {"title": "Personal directo disponible", "description": "Personas que trabajan directamente en producción: mallas, encajado, tría, granel, volcado, etc.", "example": "60 personas directas.", "impact": "Determina la capacidad productiva directa."},
    "personal_indirecto": {"title": "Personal indirecto disponible", "description": "Personas de apoyo necesarias para que la producción funcione: calidad, expedición, carretilleros, limpieza, mantenimiento, encargados, etc.", "example": "20 personas indirectas.", "impact": "Permite detectar cuellos de botella fuera de la línea principal."},
    "horas_por_persona": {"title": "Horas por persona", "description": "Horas útiles previstas por trabajador durante la jornada.", "example": "7.5 horas útiles.", "impact": "Se usará para convertir plantilla disponible en horas de trabajo disponibles."},
    "ausencias_previstas": {"title": "Ausencias previstas", "description": "Número de personas inicialmente previstas que no estarán disponibles.", "example": "5 ausencias.", "impact": "Permite ajustar la capacidad real del día."},
    "area": {"title": "Área", "description": "Zona o función operativa del almacén.", "example": "Mallas, Encajado, Expedición.", "impact": "Permite repartir el personal por función y detectar cuellos de botella concretos."},
    "tipo_personal": {"title": "Tipo personal", "description": "Clasificación del área como Directo, Indirecto o Soporte.", "example": "Mallas = Directo; Calidad = Indirecto.", "impact": "Ayuda a separar capacidad productiva directa de personal necesario de apoyo."},
    "disponible": {"title": "Disponible", "description": "Número de personas disponibles en esa área.", "example": "12 personas en Mallas.", "impact": "Se comparará después contra mínimo y óptimo."},
    "minimo_operativo": {"title": "Mínimo operativo", "description": "Número mínimo de personas necesarias para que esa área pueda funcionar.", "example": "4 personas para abrir una línea determinada.", "impact": "Si no se alcanza, la herramienta podrá marcar esa área como no operativa."},
    "optimo": {"title": "Óptimo", "description": "Número recomendado de personas para trabajar con rendimiento normal.", "example": "8 personas en Encajado.", "impact": "Permite saber si se trabaja por debajo del rendimiento esperado."},
    "activo": {"title": "Activo", "description": "Indica si el área estará operativa ese día.", "example": "Desactivar Granelera si no se va a usar.", "impact": "Las áreas inactivas no deberían considerarse en cálculos posteriores."},
    "observaciones": {"title": "Observaciones", "description": "Notas libres para explicar incidencias, restricciones o particularidades.", "example": "Falta carretillero por la tarde.", "impact": "Ayuda a justificar decisiones operativas."},
}


PRODUCTION_PACKAGING_HELP = {
    "codigo": {"title": "Código", "description": "Identificador interno único de la confección.", "example": "MALLA_2KG_CLIP.", "impact": "Se usará para relacionar pedidos, rendimientos, máquinas y reglas de planificación."},
    "descripcion": {"title": "Descripción", "description": "Nombre legible de la confección.", "example": "Malla 2 kg clip-to-clip.", "impact": "Ayuda a producción a reconocer fácilmente el formato."},
    "familia": {"title": "Familia", "description": "Grupo principal al que pertenece la confección.", "example": "Malla, Encajado, Granel o Granelera.", "impact": "Permite agrupar pedidos y aplicar reglas generales de rendimiento."},
    "subtipo": {"title": "Subtipo", "description": "Detalle específico dentro de la familia.", "example": "Tradicional, Clip-to-clip, Girsac, Caja cartón.", "impact": "Ayuda a distinguir formatos con rendimientos y cambios distintos."},
    "kg_formato": {"title": "Kg formato", "description": "Peso unitario del formato de venta o confección.", "example": "2 kg para una malla de 2 kg, 10 kg para una caja.", "impact": "Permite convertir kilos pedidos en unidades, cajas, bolsas o palets estimados."},
    "material": {"title": "Material", "description": "Material principal utilizado en la confección.", "example": "Cartón, madera, malla o plástico.", "impact": "Afecta a disponibilidad de material, cambios y compatibilidad con líneas."},
    "tipo_malla": {"title": "Tipo malla", "description": "Tipo específico de malla si aplica.", "example": "Tradicional, clip-to-clip, girsac.", "impact": "Distintos tipos de malla pueden requerir máquinas y rendimientos diferentes."},
    "requiere_precalibrado": {"title": "Requiere pre calibrado", "description": "Indica si esta confección necesita fruta pre calibrada para funcionar correctamente.", "example": "Algunos formatos especiales pueden requerir pre calibrado.", "impact": "Condiciona el orden de volcado y la disponibilidad real de fruta útil."},
    "compatible_box": {"title": "Compatible BOX", "description": "Indica si esta confección puede trabajar con BOX o alimentación especial.", "example": "Malla con BOX cuando se alimenta desde un contenedor específico.", "impact": "Puede mejorar continuidad y rendimiento en algunos casos."},
    "activo": {"title": "Activo", "description": "Indica si la confección está disponible para usar en planificación.", "example": "Desactivar formatos que no se usan esta campaña.", "impact": "Evita que el sistema proponga formatos no disponibles."},
    "observaciones": {"title": "Observaciones", "description": "Notas internas sobre limitaciones, ajustes o particularidades.", "example": "Solo usar con máquina 2 o requiere etiqueta especial.", "impact": "Ayuda a justificar decisiones operativas."},
}

PRODUCTION_LINES_HELP = {
    "codigo": {"title": "Código", "description": "Identificador interno único de la línea o máquina.", "example": "MALLAS_CLIP.", "impact": "Se usará para relacionar líneas con confecciones, rendimientos y reglas."},
    "nombre": {"title": "Nombre", "description": "Nombre visible de la línea o máquina.", "example": "Línea mallas clip-to-clip.", "impact": "Facilita la interpretación por producción."},
    "tipo_linea": {"title": "Tipo línea", "description": "Clasifica la función principal de la línea.", "example": "Volcado, Malla, Encajado.", "impact": "Permite detectar cuellos de botella por tipo de proceso."},
    "familia_principal": {"title": "Familia principal", "description": "Agrupa la línea dentro del flujo operativo.", "example": "Entrada fruta, Envasado, Expedición.", "impact": "Ayuda a ordenar el proceso productivo."},
    "numero_maquinas": {"title": "Nº máquinas", "description": "Número de máquinas disponibles de ese tipo.", "example": "3 máquinas de malla.", "impact": "Limita la capacidad máxima simultánea."},
    "activa": {"title": "Activa", "description": "Indica si la línea estará disponible para la planificación.", "example": "Desactivar línea verano fuera de campaña.", "impact": "Las líneas inactivas no deben considerarse después."},
    "capacidad_kg_h_referencia": {"title": "Capacidad kg/h referencia", "description": "Capacidad orientativa de la línea en kilos por hora.", "example": "10.000 kg/h en una línea de entrada.", "impact": "Servirá como base para calcular capacidad productiva."},
    "personal_minimo": {"title": "Personal mínimo", "description": "Personas mínimas necesarias para operar la línea.", "example": "4 personas.", "impact": "Si no se alcanza, la línea puede marcarse como no operativa."},
    "personal_optimo": {"title": "Personal óptimo", "description": "Personas recomendadas para operar con rendimiento normal.", "example": "8 personas.", "impact": "Permite estimar pérdida de rendimiento si falta personal."},
    "permite_precalibrado": {"title": "Permite pre calibrado", "description": "Indica si la línea puede trabajar con fruta pre calibrada.", "example": "Línea preparada para recibir fruta pre calibrada.", "impact": "Afectará a optimización de rendimiento y orden de trabajo."},
    "permite_box": {"title": "Permite BOX", "description": "Indica si la línea puede trabajar con BOX o alimentación especial.", "example": "Uso de BOX para alimentar línea de malla.", "impact": "Puede mejorar continuidad y reducir saturaciones."},
    "observaciones": {"title": "Observaciones", "description": "Notas internas sobre limitaciones o uso.", "example": "Solo utilizar con formato 2 kg.", "impact": "Ayuda a tomar decisiones operativas."},
}

PRODUCTION_PERFORMANCE_HELP = {
    "codigo": {"title": "Código", "description": "Identificador interno único de la regla de rendimiento.", "example": "MALLA_PRECALIBRADO.", "impact": "Se usará para relacionar confecciones, líneas y cálculos de capacidad."},
    "familia": {"title": "Familia", "description": "Grupo productivo al que pertenece el rendimiento.", "example": "Malla, Encajado, Granel o Volcado.", "impact": "Permite aplicar reglas por tipo de trabajo."},
    "confeccion_formato": {"title": "Confección / formato", "description": "Formato concreto al que aplica el rendimiento.", "example": "Malla 2 kg clip-to-clip o Encajado 10 kg cartón.", "impact": "Diferentes formatos pueden tener velocidades muy distintas."},
    "tipo_linea": {"title": "Tipo línea", "description": "Línea o proceso donde se aplica el rendimiento.", "example": "Malla, Encajado, Granelera.", "impact": "Ayuda a detectar cuellos de botella por línea."},
    "condicion": {"title": "Condición", "description": "Situación operativa bajo la que aplica el rendimiento.", "example": "Normal, con BOX, con precalibrado o destrío alto.", "impact": "Permite ajustar el rendimiento según la realidad del día."},
    "oph_referencia": {"title": "OPH referencia", "description": "Valor de referencia de producción por hora cuando se trabaja en unidades operativas por hora.", "example": "398 OPH en mallas.", "impact": "Base principal para estimar horas necesarias en procesos medidos en unidades/hora."},
    "oph_minimo": {"title": "OPH mínimo", "description": "Rendimiento mínimo esperable en condiciones desfavorables.", "example": "300 OPH.", "impact": "Permite calcular escenarios conservadores."},
    "oph_optimo": {"title": "OPH óptimo", "description": "Rendimiento esperable en buenas condiciones.", "example": "500 OPH con precalibrado.", "impact": "Permite comparar rendimiento normal frente a rendimiento mejorado."},
    "kg_h_referencia": {"title": "Kg/h referencia", "description": "Capacidad expresada directamente en kilos por hora.", "example": "10.000 kg/h de entrada de fruta.", "impact": "Útil para procesos como volcado, entrada o líneas donde el cálculo se realiza en kilos/hora."},
    "factor_precalibrado": {"title": "Factor precalibrado", "description": "Multiplicador aplicado cuando la fruta está precalibrada.", "example": "1.25 equivale a mejorar un 25%.", "impact": "Permite reflejar la mejora de continuidad y reducción de saturación."},
    "factor_destrio_alto": {"title": "Factor destrío alto", "description": "Multiplicador aplicado cuando hay mucho destrío o dificultad.", "example": "0.90 equivale a reducir el rendimiento un 10%.", "impact": "Evita sobreestimar capacidad en fruta difícil."},
    "dificultad": {"title": "Dificultad", "description": "Valor cualitativo que resume la complejidad del rendimiento.", "example": "Baja, Media, Alta o Muy alta.", "impact": "Servirá para priorizar alertas y ajustar planificación."},
    "activo": {"title": "Activo", "description": "Indica si esta regla de rendimiento se puede usar.", "example": "Desactivar reglas antiguas o no utilizadas.", "impact": "Evita que el motor use parámetros no válidos."},
    "observaciones": {"title": "Observaciones", "description": "Notas internas sobre cuándo aplicar esta regla.", "example": "Usar solo con fruta limpia o requiere máquina específica.", "impact": "Ayuda a producción a interpretar el dato."},
}

PRODUCTION_PENALTIES_HELP = {
    "codigo": {"title": "Código", "description": "Identificador interno único de la penalización.", "example": "CAMBIO_FORMATO_KG.", "impact": "Se usará para aplicar la regla en el cálculo posterior de carga productiva."},
    "tipo_penalizacion": {"title": "Tipo penalización", "description": "Tipo de evento que genera pérdida de tiempo o reducción de rendimiento.", "example": "Cambio cliente, cambio material o pedido pequeño.", "impact": "Permite clasificar el motivo de pérdida productiva."},
    "ambito": {"title": "Ámbito", "description": "Zona o proceso donde aplica la penalización.", "example": "Malla, Encajado, General o Expedición.", "impact": "Evita aplicar penalizaciones donde no corresponden."},
    "minutos_perdida": {"title": "Minutos pérdida", "description": "Tiempo estimado que se pierde cuando ocurre la penalización.", "example": "15 minutos por cambio de formato de kg.", "impact": "Se sumará a las horas necesarias de producción."},
    "factor_rendimiento": {"title": "Factor rendimiento", "description": "Multiplicador que ajusta el rendimiento cuando aplica esta condición.", "example": "0.90 reduce el rendimiento un 10%.", "impact": "Permite reflejar pérdidas de ritmo además del tiempo parado."},
    "aplica_por": {"title": "Aplica por", "description": "Frecuencia con la que debe aplicarse la penalización.", "example": "Cada cambio, cada pedido o cada jornada.", "impact": "Evita contar de más o de menos la misma pérdida."},
    "umbral": {"title": "Umbral", "description": "Condición concreta que activa la penalización.", "example": "< 3 palets o material distinto.", "impact": "Define cuándo debe aplicarse la regla."},
    "activa": {"title": "Activa", "description": "Indica si la penalización se tendrá en cuenta.", "example": "Desactivar reglas que aún no se quieran aplicar.", "impact": "Permite probar escenarios sin borrar la configuración."},
    "observaciones": {"title": "Observaciones", "description": "Notas internas sobre cuándo usar o revisar la regla.", "example": "Revisar en campaña alta.", "impact": "Ayuda a mantener criterios operativos claros."},
}


PRODUCTION_SEMAPHORE_HELP = {
    "codigo": {"title": "Código", "description": "Identificador interno único de la regla.", "example": "SATURACION_MALLA.", "impact": "Permite aplicar la regla de forma estable en el motor de planificación."},
    "tipo_regla": {"title": "Tipo regla", "description": "Clasifica el problema operativo que se quiere controlar.", "example": "Saturación capacidad, falta personal o exceso cambios.", "impact": "Ayuda a ordenar las alertas por tipo de riesgo."},
    "ambito": {"title": "Ámbito", "description": "Zona o nivel donde se aplica la regla.", "example": "General, Malla, Encajado, Personal o Pedido.", "impact": "Evita que una alerta general oculte un cuello de botella concreto."},
    "metrica": {"title": "Métrica", "description": "Dato calculado que se comparará contra los umbrales.", "example": "ocupacion_pct, personas_faltantes o cambios_formato.", "impact": "Define qué variable dispara el semáforo."},
    "operador": {"title": "Operador", "description": "Forma de comparar la métrica con los umbrales.", "example": ">= para saturación, < para rendimiento bajo.", "impact": "Determina cuándo una situación pasa a amarillo o rojo."},
    "umbral_amarillo": {"title": "Umbral amarillo", "description": "Valor a partir del cual se considera riesgo leve o advertencia.", "example": "85% de ocupación.", "impact": "Permite actuar antes de llegar a una situación crítica."},
    "umbral_rojo": {"title": "Umbral rojo", "description": "Valor a partir del cual se considera situación crítica.", "example": "100% de ocupación o más de 5 personas faltantes.", "impact": "Debe generar una alerta clara y accionable."},
    "accion_sugerida": {"title": "Acción sugerida", "description": "Recomendación operativa que se mostrará cuando se active la regla.", "example": "Añadir personal, activar segundo turno o adelantar producción.", "impact": "Convierte la alerta en una decisión útil."},
    "activa": {"title": "Activa", "description": "Indica si la regla debe aplicarse.", "example": "Desactivar reglas en fase de prueba.", "impact": "Permite probar o ajustar criterios sin borrar información."},
    "observaciones": {"title": "Observaciones", "description": "Notas internas sobre el criterio o cuándo debe revisarse.", "example": "Revisar en campaña alta.", "impact": "Ayuda a mantener coherencia en el uso de reglas."},
}

PRODUCTION_CALIBER_FACTORS_HELP = {
    "codigo": {"title": "Código", "description": "Identificador interno único de la regla.", "example": "MALLA_1KG_GRANDE.", "impact": "Permite aplicar la regla de forma estable en los cálculos."},
    "confeccion_familia": {"title": "Confección / familia", "description": "Tipo de confección donde aplica el factor.", "example": "Encajado, Granel o Malla 1 kg.", "impact": "El calibre afecta de forma distinta según la confección."},
    "grupo_calibre": {"title": "Grupo calibre", "description": "Clasificación operativa del calibre.", "example": "Pequeño, Medio, Grande.", "impact": "Permite agrupar calibres para simplificar reglas."},
    "calibres_incluidos": {"title": "Calibres incluidos", "description": "Lista editable de calibres que forman parte del grupo.", "example": "6,7,8.", "impact": "Permite modificar qué se considera pequeño, medio o grande."},
    "factor_rendimiento": {"title": "Factor rendimiento", "description": "Multiplicador que ajusta el rendimiento base.", "example": "0.85 reduce un 15%; 1.10 mejora un 10%.", "impact": "Se aplicará sobre OPH o Kg/h en la futura simulación productiva."},
    "aplica_a": {"title": "Aplica a", "description": "Indica si el factor afecta a OPH, Kg/h o ambos.", "example": "OPH, Kg/h o Ambos.", "impact": "Permite adaptar el ajuste al tipo de rendimiento usado."},
    "activo": {"title": "Activo", "description": "Indica si la regla se usará.", "example": "Desactivar temporalmente una regla para pruebas.", "impact": "Permite probar reglas sin borrarlas."},
    "observaciones": {"title": "Observaciones", "description": "Notas internas.", "example": "Calibre grande penaliza malla 1 kg.", "impact": "Ayuda a explicar por qué existe la regla."},
}
