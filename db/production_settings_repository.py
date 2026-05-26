from __future__ import annotations

from datetime import datetime
import json

from db.connection import get_connection

DEFAULT_GENERAL_SETTINGS = {
    "horas_turno": 8.0,
    "numero_turnos": 1,
    "horas_descanso": 0.5,
    "tipo_campana": "Normal",
    "tipo_volcado": "Línea invierno",
    "tipos_volcado_activos": ["Compacta", "Línea invierno"],
    "saturacion_maxima_pct": 88.0,
    "permitir_horas_extra": 1,
    "permitir_segundo_turno": 0,
    "priorizar_pedidos_reales": 1,
    "permitir_adelantar_produccion": 1,
    "agrupar_pedidos_compatibles": 1,
    "minimizar_cambios_formato": 1,
    "kg_objetivo_dia": 0.0,
    "palets_objetivo_dia": 0.0,
    "pedidos_maximos_recomendados": 36,
}
DEFAULT_STAFF_SUMMARY = {
    "personal_total": 44,
    "personal_directo": 32,
    "personal_indirecto": 12,
    "horas_por_persona": 7.5,
    "ausencias_previstas": 2,
    "observaciones": "",
}

DEFAULT_PACKAGING_TYPES = [
    {"codigo": "MALLA_1KG_TRAD", "descripcion": "Malla 1 kg tradicional", "familia": "Malla", "subtipo": "Tradicional", "kg_formato": 1.0, "material": "Malla", "tipo_malla": "Tradicional", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_2KG_TRAD", "descripcion": "Malla 2 kg tradicional", "familia": "Malla", "subtipo": "Tradicional", "kg_formato": 2.0, "material": "Malla", "tipo_malla": "Tradicional", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_2KG_CLIP", "descripcion": "Malla 2 kg clip-to-clip", "familia": "Malla", "subtipo": "Clip-to-clip", "kg_formato": 2.0, "material": "Malla", "tipo_malla": "Clip-to-clip", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_3KG_GIRSAC", "descripcion": "Malla 3 kg girsac", "familia": "Malla", "subtipo": "Girsac", "kg_formato": 3.0, "material": "Malla", "tipo_malla": "Girsac", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "ENCAJADO_10KG_CARTON", "descripcion": "Encajado 10 kg cartón", "familia": "Encajado", "subtipo": "Caja cartón", "kg_formato": 10.0, "material": "Cartón", "tipo_malla": "No aplica", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "ENCAJADO_15KG_MADERA", "descripcion": "Encajado 15 kg madera", "familia": "Encajado", "subtipo": "Caja madera", "kg_formato": 15.0, "material": "Madera", "tipo_malla": "No aplica", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "GRANEL", "descripcion": "Granel", "familia": "Granel", "subtipo": "Granel", "kg_formato": 0.0, "material": "Sin material", "tipo_malla": "No aplica", "requiere_precalibrado": 0, "compatible_box": 1, "activo": 1, "observaciones": "Admite apoyo con BOX para alimentación estable."},
    {"codigo": "GRANELERA", "descripcion": "Granelera", "familia": "Granelera", "subtipo": "Granelera", "kg_formato": 0.0, "material": "Sin material", "tipo_malla": "No aplica", "requiere_precalibrado": 0, "compatible_box": 1, "activo": 1, "observaciones": "Priorizar cuando el calibre permita flujo continuo."},
]



DEFAULT_PRODUCTION_LINES = [
    {"codigo": "VOLCADO_COMPACTA", "nombre": "Compacta", "tipo_linea": "Volcado", "familia_principal": "Entrada fruta", "numero_maquinas": 1, "activa": 1, "capacidad_kg_h_referencia": 14000.0, "personal_minimo": 4, "personal_optimo": 5, "permite_precalibrado": 1, "permite_box": 1, "observaciones": "Volcado base de campaña con alimentación por BOX opcional."},
    {"codigo": "VOLCADO_INVIERNO", "nombre": "Línea invierno", "tipo_linea": "Volcado", "familia_principal": "Entrada fruta", "numero_maquinas": 1, "activa": 1, "capacidad_kg_h_referencia": 12000.0, "personal_minimo": 3, "personal_optimo": 4, "permite_precalibrado": 1, "permite_box": 1, "observaciones": "Apoyo habitual en días de carga media/alta."},
    {"codigo": "VOLCADO_VERANO", "nombre": "Línea verano", "tipo_linea": "Volcado", "familia_principal": "Entrada fruta", "numero_maquinas": 1, "activa": 0, "capacidad_kg_h_referencia": 0.0, "personal_minimo": 0, "personal_optimo": 0, "permite_precalibrado": 0, "permite_box": 0, "observaciones": ""},
    {"codigo": "VOLCADO_TOLVA", "nombre": "Tolva", "tipo_linea": "Volcado", "familia_principal": "Entrada fruta", "numero_maquinas": 1, "activa": 0, "capacidad_kg_h_referencia": 0.0, "personal_minimo": 0, "personal_optimo": 0, "permite_precalibrado": 0, "permite_box": 0, "observaciones": ""},
    {"codigo": "VOLCADO_MANUAL", "nombre": "Manual", "tipo_linea": "Volcado", "familia_principal": "Entrada fruta", "numero_maquinas": 1, "activa": 0, "capacidad_kg_h_referencia": 0.0, "personal_minimo": 0, "personal_optimo": 0, "permite_precalibrado": 0, "permite_box": 0, "observaciones": ""},
    {"codigo": "MALLAS_TRADICIONAL", "nombre": "Línea mallas tradicional", "tipo_linea": "Malla", "familia_principal": "Envasado", "numero_maquinas": 2, "activa": 1, "capacidad_kg_h_referencia": 3200.0, "personal_minimo": 6, "personal_optimo": 8, "permite_precalibrado": 1, "permite_box": 1, "observaciones": "Tría malla y mallas como bloque principal."},
    {"codigo": "MALLAS_CLIP", "nombre": "Línea mallas clip-to-clip", "tipo_linea": "Malla", "familia_principal": "Envasado", "numero_maquinas": 1, "activa": 1, "capacidad_kg_h_referencia": 2600.0, "personal_minimo": 4, "personal_optimo": 6, "permite_precalibrado": 1, "permite_box": 1, "observaciones": "Soporte para pedidos pequeños y cambios de formato."},
    {"codigo": "MALLAS_GIRSAC", "nombre": "Línea mallas girsac", "tipo_linea": "Malla", "familia_principal": "Envasado", "numero_maquinas": 1, "activa": 0, "capacidad_kg_h_referencia": 0.0, "personal_minimo": 0, "personal_optimo": 0, "permite_precalibrado": 0, "permite_box": 0, "observaciones": ""},
    {"codigo": "ENCAJADO", "nombre": "Línea encajado", "tipo_linea": "Encajado", "familia_principal": "Envasado", "numero_maquinas": 1, "activa": 1, "capacidad_kg_h_referencia": 2200.0, "personal_minimo": 4, "personal_optimo": 5, "permite_precalibrado": 0, "permite_box": 1, "observaciones": "Reforzar cuando suban pedidos de caja."},
    {"codigo": "GRANEL_MANUAL", "nombre": "Granel manual", "tipo_linea": "Granel", "familia_principal": "Envasado", "numero_maquinas": 1, "activa": 1, "capacidad_kg_h_referencia": 3600.0, "personal_minimo": 3, "personal_optimo": 4, "permite_precalibrado": 1, "permite_box": 1, "observaciones": "Uso flexible para absorber picos diarios."},
    {"codigo": "GRANELERA", "nombre": "Granelera", "tipo_linea": "Granelera", "familia_principal": "Envasado", "numero_maquinas": 1, "activa": 1, "capacidad_kg_h_referencia": 6500.0, "personal_minimo": 2, "personal_optimo": 3, "permite_precalibrado": 1, "permite_box": 1, "observaciones": "Activar para cargas altas de granel continuo."},
    {"codigo": "CALIBRADOR", "nombre": "Calibrador", "tipo_linea": "Calibrador", "familia_principal": "Clasificación", "numero_maquinas": 1, "activa": 1, "capacidad_kg_h_referencia": 0.0, "personal_minimo": 0, "personal_optimo": 0, "permite_precalibrado": 0, "permite_box": 0, "observaciones": ""},
    {"codigo": "FINAL_LINEA", "nombre": "Final de línea", "tipo_linea": "Final línea", "familia_principal": "Salida / expedición", "numero_maquinas": 1, "activa": 1, "capacidad_kg_h_referencia": 0.0, "personal_minimo": 0, "personal_optimo": 0, "permite_precalibrado": 0, "permite_box": 0, "observaciones": ""},
]



DEFAULT_PERFORMANCE_RULES = [
    {"codigo": "ENCAJADO_NORMAL", "familia": "Encajado", "confeccion_formato": "Encajado general", "tipo_linea": "Encajado", "condicion": "Normal", "oph_referencia": 250.0, "oph_minimo": 200.0, "oph_optimo": 300.0, "kg_h_referencia": 0.0, "factor_precalibrado": 1.00, "factor_destrio_alto": 0.90, "dificultad": "Media", "activo": 1, "observaciones": "Referencia general encajado."},
    {"codigo": "MALLA_NORMAL", "familia": "Malla", "confeccion_formato": "Malla general", "tipo_linea": "Malla", "condicion": "Normal", "oph_referencia": 398.0, "oph_minimo": 300.0, "oph_optimo": 465.0, "kg_h_referencia": 0.0, "factor_precalibrado": 1.00, "factor_destrio_alto": 0.90, "dificultad": "Media", "activo": 1, "observaciones": "Referencia general mallas."},
    {"codigo": "MALLA_CON_BOX", "familia": "Malla", "confeccion_formato": "Malla con BOX", "tipo_linea": "Malla", "condicion": "Con BOX", "oph_referencia": 465.0, "oph_minimo": 350.0, "oph_optimo": 500.0, "kg_h_referencia": 0.0, "factor_precalibrado": 1.00, "factor_destrio_alto": 0.90, "dificultad": "Media", "activo": 1, "observaciones": "Mejora por alimentación con BOX."},
    {"codigo": "MALLA_PRECALIBRADO", "familia": "Malla", "confeccion_formato": "Malla con precalibrado", "tipo_linea": "Malla", "condicion": "Con precalibrado", "oph_referencia": 500.0, "oph_minimo": 400.0, "oph_optimo": 550.0, "kg_h_referencia": 0.0, "factor_precalibrado": 1.25, "factor_destrio_alto": 0.95, "dificultad": "Baja", "activo": 1, "observaciones": "Referencia con fruta precalibrada."},
    {"codigo": "GRANEL_MANUAL_NORMAL", "familia": "Granel", "confeccion_formato": "Granel manual", "tipo_linea": "Granel", "condicion": "Normal", "oph_referencia": 420.0, "oph_minimo": 350.0, "oph_optimo": 450.0, "kg_h_referencia": 0.0, "factor_precalibrado": 1.00, "factor_destrio_alto": 0.90, "dificultad": "Baja", "activo": 1, "observaciones": "Referencia granel manual."},
    {"codigo": "GRANEL_MANUAL_PRECALIBRADO", "familia": "Granel", "confeccion_formato": "Granel manual con precalibrado", "tipo_linea": "Granel", "condicion": "Con precalibrado", "oph_referencia": 450.0, "oph_minimo": 380.0, "oph_optimo": 500.0, "kg_h_referencia": 0.0, "factor_precalibrado": 1.10, "factor_destrio_alto": 0.95, "dificultad": "Baja", "activo": 1, "observaciones": "Mejora por precalibrado."},
    {"codigo": "VOLCADO_REFERENCIA", "familia": "Volcado", "confeccion_formato": "Entrada fruta", "tipo_linea": "Volcado", "condicion": "Normal", "oph_referencia": 0.0, "oph_minimo": 0.0, "oph_optimo": 0.0, "kg_h_referencia": 10000.0, "factor_precalibrado": 1.00, "factor_destrio_alto": 0.90, "dificultad": "Media", "activo": 1, "observaciones": "Referencia orientativa de entrada de fruta."},
]
DEFAULT_PENALTY_RULES = [
    {"codigo": "CAMBIO_CLIENTE", "tipo_penalizacion": "Cambio cliente", "ambito": "General", "minutos_perdida": 5.0, "factor_rendimiento": 1.00, "aplica_por": "Cada cambio", "umbral": "cliente distinto", "activa": 1, "observaciones": "Tiempo orientativo por cambio administrativo/operativo de cliente."},
    {"codigo": "CAMBIO_PLATAFORMA", "tipo_penalizacion": "Cambio plataforma", "ambito": "General", "minutos_perdida": 5.0, "factor_rendimiento": 1.00, "aplica_por": "Cada cambio", "umbral": "plataforma distinta", "activa": 1, "observaciones": ""},
    {"codigo": "CAMBIO_FORMATO_KG", "tipo_penalizacion": "Cambio formato kg", "ambito": "Malla", "minutos_perdida": 15.0, "factor_rendimiento": 1.00, "aplica_por": "Cada cambio", "umbral": "cambia kg por bolsa", "activa": 1, "observaciones": ""},
    {"codigo": "CAMBIO_TIPO_MALLA", "tipo_penalizacion": "Cambio tipo malla", "ambito": "Malla", "minutos_perdida": 25.0, "factor_rendimiento": 0.95, "aplica_por": "Cada cambio", "umbral": "tradicional / clip-to-clip / girsac", "activa": 1, "observaciones": ""},
    {"codigo": "CAMBIO_MATERIAL", "tipo_penalizacion": "Cambio material", "ambito": "General", "minutos_perdida": 20.0, "factor_rendimiento": 1.00, "aplica_por": "Cada cambio", "umbral": "cartón / madera / malla / plástico", "activa": 1, "observaciones": ""},
    {"codigo": "CAMBIO_ETIQUETA", "tipo_penalizacion": "Cambio etiqueta", "ambito": "General", "minutos_perdida": 3.0, "factor_rendimiento": 1.00, "aplica_por": "Cada cambio", "umbral": "etiqueta distinta", "activa": 1, "observaciones": ""},
    {"codigo": "CAMBIO_CONFECCION", "tipo_penalizacion": "Cambio confección", "ambito": "General", "minutos_perdida": 40.0, "factor_rendimiento": 0.90, "aplica_por": "Cada cambio", "umbral": "familia de confección distinta", "activa": 1, "observaciones": ""},
    {"codigo": "PEDIDO_PEQUENO", "tipo_penalizacion": "Pedido pequeño", "ambito": "General", "minutos_perdida": 12.0, "factor_rendimiento": 0.88, "aplica_por": "Cada pedido", "umbral": "< 4 palets", "activa": 1, "observaciones": "Penalización por fragmentación del trabajo en pedidos pequeños."},
    {"codigo": "ARRANQUE_LINEA", "tipo_penalizacion": "Arranque línea", "ambito": "General", "minutos_perdida": 20.0, "factor_rendimiento": 1.00, "aplica_por": "Cada arranque", "umbral": "inicio línea", "activa": 1, "observaciones": ""},
    {"codigo": "LIMPIEZA_CAMBIO", "tipo_penalizacion": "Limpieza", "ambito": "General", "minutos_perdida": 15.0, "factor_rendimiento": 1.00, "aplica_por": "Cada cambio", "umbral": "limpieza necesaria", "activa": 1, "observaciones": ""},
    {"codigo": "ESPERA_MATERIAL", "tipo_penalizacion": "Espera material", "ambito": "General", "minutos_perdida": 10.0, "factor_rendimiento": 0.95, "aplica_por": "Cada parada", "umbral": "material no disponible", "activa": 1, "observaciones": ""},
]


DEFAULT_SEMAPHORE_RULES = [
    {"codigo": "SATURACION_GENERAL", "tipo_regla": "Saturación capacidad", "ambito": "General", "metrica": "ocupacion_pct", "operador": ">=", "umbral_amarillo": 82.0, "umbral_rojo": 95.0, "accion_sugerida": "Revisar adelantos, horas extra o segundo turno.", "activa": 1, "observaciones": "Control general de ocupación productiva."},
    {"codigo": "SATURACION_MALLA", "tipo_regla": "Saturación capacidad", "ambito": "Malla", "metrica": "ocupacion_pct", "operador": ">=", "umbral_amarillo": 85.0, "umbral_rojo": 100.0, "accion_sugerida": "Agrupar formatos, reducir cambios o activar más máquinas de malla.", "activa": 1, "observaciones": ""},
    {"codigo": "SATURACION_ENCAJADO", "tipo_regla": "Saturación capacidad", "ambito": "Encajado", "metrica": "ocupacion_pct", "operador": ">=", "umbral_amarillo": 85.0, "umbral_rojo": 100.0, "accion_sugerida": "Adelantar encajado o reforzar personal.", "activa": 1, "observaciones": ""},
    {"codigo": "FALTA_PERSONAL_GENERAL", "tipo_regla": "Falta personal", "ambito": "Personal", "metrica": "personas_faltantes", "operador": ">", "umbral_amarillo": 0.0, "umbral_rojo": 5.0, "accion_sugerida": "Revisar plantilla disponible o reducir carga prevista.", "activa": 1, "observaciones": ""},
    {"codigo": "EXCESO_PEDIDOS_DIA", "tipo_regla": "Exceso pedidos", "ambito": "General", "metrica": "pedidos_dia", "operador": ">=", "umbral_amarillo": 35.0, "umbral_rojo": 50.0, "accion_sugerida": "Agrupar pedidos compatibles o adelantar preparación.", "activa": 1, "observaciones": ""},
    {"codigo": "EXCESO_CAMBIOS_FORMATO", "tipo_regla": "Exceso cambios", "ambito": "General", "metrica": "cambios_formato", "operador": ">=", "umbral_amarillo": 8.0, "umbral_rojo": 15.0, "accion_sugerida": "Reordenar producción minimizando cambios de formato.", "activa": 1, "observaciones": ""},
    {"codigo": "PEDIDOS_PEQUENOS", "tipo_regla": "Exceso pedidos", "ambito": "General", "metrica": "pedidos_pequenos", "operador": ">=", "umbral_amarillo": 6.0, "umbral_rojo": 12.0, "accion_sugerida": "Agrupar pedidos pequeños por cliente, plataforma o formato.", "activa": 1, "observaciones": ""},
    {"codigo": "FECHA_SALIDA_CRITICA", "tipo_regla": "Fecha salida crítica", "ambito": "Pedido", "metrica": "dias_hasta_salida", "operador": "<=", "umbral_amarillo": 1.0, "umbral_rojo": 0.0, "accion_sugerida": "Priorizar pedido o revisar posibilidad real de salida.", "activa": 1, "observaciones": ""},
    {"codigo": "RENDIMIENTO_BAJO", "tipo_regla": "Rendimiento bajo", "ambito": "General", "metrica": "rendimiento_pct", "operador": "<", "umbral_amarillo": 90.0, "umbral_rojo": 75.0, "accion_sugerida": "Revisar fruta, personal, máquina, material o exceso de cambios.", "activa": 1, "observaciones": ""},
    {"codigo": "STOCK_COBERTURA_BAJA", "tipo_regla": "Stock insuficiente", "ambito": "General", "metrica": "stock_cobertura_pct", "operador": "<", "umbral_amarillo": 100.0, "umbral_rojo": 80.0, "accion_sugerida": "Programar recolección o ajustar pedidos.", "activa": 1, "observaciones": ""},
]
DEFAULT_CALIBER_PERFORMANCE_FACTORS = [
    {"codigo": "ENCAJADO_PEQUENO", "confeccion_familia": "Encajado", "grupo_calibre": "Pequeño", "calibres_incluidos": "6,7,8", "factor_rendimiento": 0.85, "aplica_a": "Ambos", "activo": 1, "observaciones": "En encajado los calibres pequeños ralentizan por mayor número de piezas."},
    {"codigo": "ENCAJADO_MEDIO", "confeccion_familia": "Encajado", "grupo_calibre": "Medio", "calibres_incluidos": "4,5", "factor_rendimiento": 1.00, "aplica_a": "Ambos", "activo": 1, "observaciones": "Calibre medio como referencia normal."},
    {"codigo": "ENCAJADO_GRANDE", "confeccion_familia": "Encajado", "grupo_calibre": "Grande", "calibres_incluidos": "0,1,2,3", "factor_rendimiento": 1.10, "aplica_a": "Ambos", "activo": 1, "observaciones": "En encajado los calibres grandes suelen aumentar velocidad por menor número de piezas."},
    {"codigo": "GRANEL_PEQUENO", "confeccion_familia": "Granel", "grupo_calibre": "Pequeño", "calibres_incluidos": "6,7,8", "factor_rendimiento": 0.90, "aplica_a": "Ambos", "activo": 1, "observaciones": ""},
    {"codigo": "GRANEL_MEDIO", "confeccion_familia": "Granel", "grupo_calibre": "Medio", "calibres_incluidos": "4,5", "factor_rendimiento": 1.00, "aplica_a": "Ambos", "activo": 1, "observaciones": ""},
    {"codigo": "GRANEL_GRANDE", "confeccion_familia": "Granel", "grupo_calibre": "Grande", "calibres_incluidos": "0,1,2,3", "factor_rendimiento": 1.12, "aplica_a": "Ambos", "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_1KG_PEQUENO", "confeccion_familia": "Malla 1 kg", "grupo_calibre": "Pequeño", "calibres_incluidos": "6,7,8", "factor_rendimiento": 1.05, "aplica_a": "Ambos", "activo": 1, "observaciones": "En malla pequeña, calibres pequeños/medios suelen ajustar mejor."},
    {"codigo": "MALLA_1KG_MEDIO", "confeccion_familia": "Malla 1 kg", "grupo_calibre": "Medio", "calibres_incluidos": "4,5", "factor_rendimiento": 1.00, "aplica_a": "Ambos", "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_1KG_GRANDE", "confeccion_familia": "Malla 1 kg", "grupo_calibre": "Grande", "calibres_incluidos": "0,1,2,3", "factor_rendimiento": 0.80, "aplica_a": "Ambos", "activo": 1, "observaciones": "En malla 1 kg los calibres grandes complican pesadora y ajuste."},
    {"codigo": "MALLA_2KG_PEQUENO", "confeccion_familia": "Malla 2 kg", "grupo_calibre": "Pequeño", "calibres_incluidos": "6,7,8", "factor_rendimiento": 1.05, "aplica_a": "Ambos", "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_2KG_MEDIO", "confeccion_familia": "Malla 2 kg", "grupo_calibre": "Medio", "calibres_incluidos": "4,5", "factor_rendimiento": 1.00, "aplica_a": "Ambos", "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_2KG_GRANDE", "confeccion_familia": "Malla 2 kg", "grupo_calibre": "Grande", "calibres_incluidos": "0,1,2,3", "factor_rendimiento": 0.90, "aplica_a": "Ambos", "activo": 1, "observaciones": ""},
]
DEFAULT_UNLOADING_PRIORITY_RULES = [
    {"criterio": "Mayor cobertura de pedidos", "descripcion": "Priorizar partidas que cubran mayor porcentaje del pedido total.", "peso": 1.0, "activo": 1, "observaciones": ""},
    {"criterio": "Menor destrío", "descripcion": "Favorecer partidas con menor porcentaje de destrío previsto.", "peso": 1.0, "activo": 1, "observaciones": ""},
    {"criterio": "Calibre dominante necesario", "descripcion": "Priorizar partidas con calibre dominante alineado con demanda.", "peso": 1.0, "activo": 1, "observaciones": ""},
    {"criterio": "Variedad demandada", "descripcion": "Favorecer variedades con mayor tensión comercial del día.", "peso": 1.0, "activo": 1, "observaciones": ""},
    {"criterio": "Fecha salida próxima", "descripcion": "Priorizar partidas de pedidos con salida más inmediata.", "peso": 1.0, "activo": 1, "observaciones": ""},
    {"criterio": "Kg útiles estimados", "descripcion": "Maximizar kilos útiles tras destrío y mermas.", "peso": 1.0, "activo": 1, "observaciones": ""},
    {"criterio": "Riesgo de sobrante", "descripcion": "Reducir probabilidad de sobrante no comercializable.", "peso": 1.0, "activo": 1, "observaciones": ""},
]

DEFAULT_STAFF_AREAS = [
    ("Volcado", "Directo", 5, 4, 5, 1, "Config. base para compacta + invierno."),
    ("Tría principal", "Directo", 6, 5, 7, 1, ""),
    ("Tría mallas", "Directo", 4, 3, 5, 1, ""),
    ("Mallas", "Directo", 8, 6, 9, 1, ""),
    ("Encajado", "Directo", 5, 4, 6, 1, ""),
    ("Granel manual", "Directo", 4, 3, 5, 1, ""),
    ("Granelera", "Directo", 2, 2, 3, 1, ""),
    ("Calibrador", "Soporte", 0, 0, 0, 1, ""),
    ("Calidad", "Indirecto", 2, 1, 2, 1, ""),
    ("Control destrío", "Soporte", 0, 0, 0, 1, ""),
    ("Alimentación", "Soporte", 3, 2, 3, 1, "Incluye apoyo de BOX en líneas con alta carga."),
    ("Loteado", "Soporte", 0, 0, 0, 1, ""),
    ("Expedición", "Indirecto", 2, 1, 2, 1, ""),
    ("Carretilleros", "Indirecto", 2, 1, 2, 1, ""),
    ("Flejado", "Soporte", 0, 0, 0, 1, ""),
    ("Mantenimiento", "Soporte", 0, 0, 0, 1, ""),
    ("Limpieza", "Indirecto", 0, 0, 0, 1, ""),
    ("Encargados", "Indirecto", 0, 0, 0, 1, ""),
]


class ProductionSettingsRepository:
    def __init__(self) -> None:
        self.ensure_defaults()
        self.ensure_staff_defaults()
        self.ensure_lines_defaults()
        self.ensure_packaging_defaults()
        self.ensure_performance_defaults()
        self.ensure_penalties_defaults()
        self.ensure_semaphore_defaults()
        self.ensure_caliber_factors_defaults()
        self.ensure_unloading_priority_defaults()

    def ensure_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_general_settings (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    horas_turno REAL NOT NULL,
                    numero_turnos INTEGER NOT NULL,
                    horas_descanso REAL NOT NULL,
                    tipo_campana TEXT NOT NULL,
                    tipo_volcado TEXT NOT NULL,
                    tipos_volcado_activos TEXT,
                    saturacion_maxima_pct REAL NOT NULL,
                    permitir_horas_extra INTEGER NOT NULL,
                    permitir_segundo_turno INTEGER NOT NULL,
                    priorizar_pedidos_reales INTEGER NOT NULL,
                    permitir_adelantar_produccion INTEGER NOT NULL,
                    agrupar_pedidos_compatibles INTEGER NOT NULL,
                    minimizar_cambios_formato INTEGER NOT NULL,
                    kg_objetivo_dia REAL NOT NULL,
                    palets_objetivo_dia REAL NOT NULL,
                    pedidos_maximos_recomendados INTEGER NOT NULL,
                    updated_at TEXT
                )
                """
            )
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(production_general_settings)").fetchall()
            }
            if "tipos_volcado_activos" not in columns:
                conn.execute("ALTER TABLE production_general_settings ADD COLUMN tipos_volcado_activos TEXT")

    def ensure_defaults(self) -> None:
        self.ensure_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_general_settings (
                    id, horas_turno, numero_turnos, horas_descanso, tipo_campana,
                    tipo_volcado, tipos_volcado_activos, saturacion_maxima_pct, permitir_horas_extra,
                    permitir_segundo_turno, priorizar_pedidos_reales,
                    permitir_adelantar_produccion, agrupar_pedidos_compatibles,
                    minimizar_cambios_formato, kg_objetivo_dia, palets_objetivo_dia,
                    pedidos_maximos_recomendados, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    1,
                    DEFAULT_GENERAL_SETTINGS["horas_turno"],
                    DEFAULT_GENERAL_SETTINGS["numero_turnos"],
                    DEFAULT_GENERAL_SETTINGS["horas_descanso"],
                    DEFAULT_GENERAL_SETTINGS["tipo_campana"],
                    DEFAULT_GENERAL_SETTINGS["tipo_volcado"],
                    json.dumps(DEFAULT_GENERAL_SETTINGS["tipos_volcado_activos"], ensure_ascii=False),
                    DEFAULT_GENERAL_SETTINGS["saturacion_maxima_pct"],
                    DEFAULT_GENERAL_SETTINGS["permitir_horas_extra"],
                    DEFAULT_GENERAL_SETTINGS["permitir_segundo_turno"],
                    DEFAULT_GENERAL_SETTINGS["priorizar_pedidos_reales"],
                    DEFAULT_GENERAL_SETTINGS["permitir_adelantar_produccion"],
                    DEFAULT_GENERAL_SETTINGS["agrupar_pedidos_compatibles"],
                    DEFAULT_GENERAL_SETTINGS["minimizar_cambios_formato"],
                    DEFAULT_GENERAL_SETTINGS["kg_objetivo_dia"],
                    DEFAULT_GENERAL_SETTINGS["palets_objetivo_dia"],
                    DEFAULT_GENERAL_SETTINGS["pedidos_maximos_recomendados"],
                    now,
                ),
            )

    def get_general_settings(self) -> dict:
        self.ensure_defaults()
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM production_general_settings WHERE id = 1").fetchone()
        data = dict(row) if row else {"id": 1, **DEFAULT_GENERAL_SETTINGS}
        data["tipos_volcado_activos"] = self._parse_tipos_volcado_activos(data)
        return data

    def save_general_settings(self, data: dict) -> None:
        self.ensure_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_general_settings (
                    id, horas_turno, numero_turnos, horas_descanso, tipo_campana,
                    tipo_volcado, tipos_volcado_activos, saturacion_maxima_pct, permitir_horas_extra,
                    permitir_segundo_turno, priorizar_pedidos_reales,
                    permitir_adelantar_produccion, agrupar_pedidos_compatibles,
                    minimizar_cambios_formato, kg_objetivo_dia, palets_objetivo_dia,
                    pedidos_maximos_recomendados, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    horas_turno=excluded.horas_turno,
                    numero_turnos=excluded.numero_turnos,
                    horas_descanso=excluded.horas_descanso,
                    tipo_campana=excluded.tipo_campana,
                    tipo_volcado=excluded.tipo_volcado,
                    tipos_volcado_activos=excluded.tipos_volcado_activos,
                    saturacion_maxima_pct=excluded.saturacion_maxima_pct,
                    permitir_horas_extra=excluded.permitir_horas_extra,
                    permitir_segundo_turno=excluded.permitir_segundo_turno,
                    priorizar_pedidos_reales=excluded.priorizar_pedidos_reales,
                    permitir_adelantar_produccion=excluded.permitir_adelantar_produccion,
                    agrupar_pedidos_compatibles=excluded.agrupar_pedidos_compatibles,
                    minimizar_cambios_formato=excluded.minimizar_cambios_formato,
                    kg_objetivo_dia=excluded.kg_objetivo_dia,
                    palets_objetivo_dia=excluded.palets_objetivo_dia,
                    pedidos_maximos_recomendados=excluded.pedidos_maximos_recomendados,
                    updated_at=excluded.updated_at
                """,
                (
                    1,
                    data["horas_turno"],
                    data["numero_turnos"],
                    data["horas_descanso"],
                    data["tipo_campana"],
                    data["tipos_volcado_activos"][0] if data["tipos_volcado_activos"] else DEFAULT_GENERAL_SETTINGS["tipo_volcado"],
                    json.dumps(data["tipos_volcado_activos"], ensure_ascii=False),
                    data["saturacion_maxima_pct"],
                    int(data["permitir_horas_extra"]),
                    int(data["permitir_segundo_turno"]),
                    int(data["priorizar_pedidos_reales"]),
                    int(data["permitir_adelantar_produccion"]),
                    int(data["agrupar_pedidos_compatibles"]),
                    int(data["minimizar_cambios_formato"]),
                    data["kg_objetivo_dia"],
                    data["palets_objetivo_dia"],
                    data["pedidos_maximos_recomendados"],
                    now,
                ),
            )

    def reset_general_defaults(self) -> None:
        self.save_general_settings(DEFAULT_GENERAL_SETTINGS)

    def _parse_tipos_volcado_activos(self, data: dict) -> list[str]:
        raw = data.get("tipos_volcado_activos")
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                    if cleaned:
                        return cleaned
            except (ValueError, TypeError):
                cleaned = [item.strip() for item in str(raw).split(",") if item.strip()]
                if cleaned:
                    return cleaned

        legacy = str(data.get("tipo_volcado", "")).strip()
        return [legacy] if legacy else list(DEFAULT_GENERAL_SETTINGS["tipos_volcado_activos"])

    def ensure_staff_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_staff_summary (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    personal_total INTEGER NOT NULL,
                    personal_directo INTEGER NOT NULL,
                    personal_indirecto INTEGER NOT NULL,
                    horas_por_persona REAL NOT NULL,
                    ausencias_previstas INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_staff_areas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    area TEXT NOT NULL UNIQUE,
                    tipo_personal TEXT NOT NULL,
                    disponible INTEGER NOT NULL,
                    minimo_operativo INTEGER NOT NULL,
                    optimo INTEGER NOT NULL,
                    activo INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_staff_defaults(self) -> None:
        self.ensure_staff_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_staff_summary (
                    id, personal_total, personal_directo, personal_indirecto,
                    horas_por_persona, ausencias_previstas, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    1,
                    DEFAULT_STAFF_SUMMARY["personal_total"],
                    DEFAULT_STAFF_SUMMARY["personal_directo"],
                    DEFAULT_STAFF_SUMMARY["personal_indirecto"],
                    DEFAULT_STAFF_SUMMARY["horas_por_persona"],
                    DEFAULT_STAFF_SUMMARY["ausencias_previstas"],
                    DEFAULT_STAFF_SUMMARY["observaciones"],
                    now,
                ),
            )
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_staff_areas").fetchone()["n"]
            if existing == 0:
                conn.executemany(
                    """
                    INSERT INTO production_staff_areas (
                        area, tipo_personal, disponible, minimo_operativo, optimo, activo, observaciones, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [(*row, now) for row in DEFAULT_STAFF_AREAS],
                )

    def get_staff_summary(self) -> dict:
        self.ensure_staff_defaults()
        with get_connection() as conn:
            row = conn.execute("SELECT * FROM production_staff_summary WHERE id = 1").fetchone()
        return dict(row) if row else {"id": 1, **DEFAULT_STAFF_SUMMARY}

    def save_staff_summary(self, data: dict) -> None:
        self.ensure_staff_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO production_staff_summary (
                    id, personal_total, personal_directo, personal_indirecto,
                    horas_por_persona, ausencias_previstas, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    personal_total=excluded.personal_total,
                    personal_directo=excluded.personal_directo,
                    personal_indirecto=excluded.personal_indirecto,
                    horas_por_persona=excluded.horas_por_persona,
                    ausencias_previstas=excluded.ausencias_previstas,
                    observaciones=excluded.observaciones,
                    updated_at=excluded.updated_at
                """,
                (
                    1,
                    data["personal_total"],
                    data["personal_directo"],
                    data["personal_indirecto"],
                    data["horas_por_persona"],
                    data["ausencias_previstas"],
                    data.get("observaciones", ""),
                    now,
                ),
            )

    def get_staff_areas(self) -> list[dict]:
        self.ensure_staff_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_staff_areas ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def save_staff_areas(self, rows: list[dict]) -> None:
        self.ensure_staff_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_staff_areas")
            conn.executemany(
                """
                INSERT INTO production_staff_areas (
                    area, tipo_personal, disponible, minimo_operativo, optimo, activo, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["area"],
                        row["tipo_personal"],
                        int(row["disponible"]),
                        int(row["minimo_operativo"]),
                        int(row["optimo"]),
                        int(row["activo"]),
                        row.get("observaciones", ""),
                        now,
                    )
                    for row in rows
                ],
            )

    def reset_staff_defaults(self) -> None:
        self.ensure_staff_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_staff_areas")
            conn.executemany(
                """
                INSERT INTO production_staff_areas (
                    area, tipo_personal, disponible, minimo_operativo, optimo, activo, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(*row, now) for row in DEFAULT_STAFF_AREAS],
            )
        self.save_staff_summary(DEFAULT_STAFF_SUMMARY)

    def delete_staff_area(self, area_id: int) -> None:
        self.ensure_staff_schema()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_staff_areas WHERE id = ?", (area_id,))

    def ensure_lines_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    nombre TEXT NOT NULL,
                    tipo_linea TEXT NOT NULL,
                    familia_principal TEXT NOT NULL,
                    numero_maquinas INTEGER NOT NULL,
                    activa INTEGER NOT NULL,
                    capacidad_kg_h_referencia REAL NOT NULL,
                    personal_minimo INTEGER NOT NULL,
                    personal_optimo INTEGER NOT NULL,
                    permite_precalibrado INTEGER NOT NULL,
                    permite_box INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_lines_defaults(self) -> None:
        self.ensure_lines_schema()
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_lines").fetchone()["n"]
            if existing == 0:
                self.save_lines(DEFAULT_PRODUCTION_LINES)

    def get_lines(self) -> list[dict]:
        self.ensure_lines_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_lines ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def save_lines(self, rows: list[dict]) -> None:
        self.ensure_lines_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_lines")
            conn.executemany(
                """
                INSERT INTO production_lines (
                    codigo, nombre, tipo_linea, familia_principal, numero_maquinas, activa,
                    capacidad_kg_h_referencia, personal_minimo, personal_optimo,
                    permite_precalibrado, permite_box, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["codigo"], row["nombre"], row["tipo_linea"], row["familia_principal"],
                        int(row["numero_maquinas"]), int(row["activa"]), float(row["capacidad_kg_h_referencia"]),
                        int(row["personal_minimo"]), int(row["personal_optimo"]), int(row["permite_precalibrado"]),
                        int(row["permite_box"]), row.get("observaciones", ""), now,
                    )
                    for row in rows
                ],
            )

    def reset_lines_defaults(self) -> None:
        self.save_lines(DEFAULT_PRODUCTION_LINES)

    def ensure_packaging_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_packaging_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    descripcion TEXT NOT NULL,
                    familia TEXT NOT NULL,
                    subtipo TEXT NOT NULL,
                    kg_formato REAL NOT NULL,
                    material TEXT NOT NULL,
                    tipo_malla TEXT NOT NULL,
                    requiere_precalibrado INTEGER NOT NULL,
                    compatible_box INTEGER NOT NULL,
                    activo INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_packaging_defaults(self) -> None:
        self.ensure_packaging_schema()
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_packaging_types").fetchone()["n"]
            if existing == 0:
                self.save_packaging_types(DEFAULT_PACKAGING_TYPES)

    def get_packaging_types(self) -> list[dict]:
        self.ensure_packaging_defaults()
        self.ensure_performance_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_packaging_types ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def save_packaging_types(self, rows: list[dict]) -> None:
        self.ensure_packaging_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_packaging_types")
            conn.executemany(
                """
                INSERT INTO production_packaging_types (
                    codigo, descripcion, familia, subtipo, kg_formato, material, tipo_malla,
                    requiere_precalibrado, compatible_box, activo, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["codigo"], row["descripcion"], row["familia"], row["subtipo"], float(row["kg_formato"]),
                        row["material"], row["tipo_malla"], int(row["requiere_precalibrado"]), int(row["compatible_box"]),
                        int(row["activo"]), row.get("observaciones", ""), now,
                    ) for row in rows
                ],
            )

    def reset_packaging_defaults(self) -> None:
        self.save_packaging_types(DEFAULT_PACKAGING_TYPES)

    def delete_packaging_type(self, packaging_id: int) -> None:
        self.ensure_packaging_schema()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_packaging_types WHERE id = ?", (packaging_id,))


    def ensure_performance_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_performance_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    familia TEXT NOT NULL,
                    confeccion_formato TEXT NOT NULL,
                    tipo_linea TEXT NOT NULL,
                    condicion TEXT NOT NULL,
                    oph_referencia REAL NOT NULL,
                    oph_minimo REAL NOT NULL,
                    oph_optimo REAL NOT NULL,
                    kg_h_referencia REAL NOT NULL,
                    factor_precalibrado REAL NOT NULL,
                    factor_destrio_alto REAL NOT NULL,
                    dificultad TEXT NOT NULL,
                    activo INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_performance_defaults(self) -> None:
        self.ensure_performance_schema()
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_performance_rules").fetchone()["n"]
            if existing == 0:
                self.save_performance_rules(DEFAULT_PERFORMANCE_RULES)

    def get_performance_rules(self) -> list[dict]:
        self.ensure_performance_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_performance_rules ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def save_performance_rules(self, rows: list[dict]) -> None:
        self.ensure_performance_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_performance_rules")
            conn.executemany(
                """
                INSERT INTO production_performance_rules (
                    codigo, familia, confeccion_formato, tipo_linea, condicion,
                    oph_referencia, oph_minimo, oph_optimo, kg_h_referencia,
                    factor_precalibrado, factor_destrio_alto, dificultad,
                    activo, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(
                    row["codigo"], row["familia"], row["confeccion_formato"], row["tipo_linea"], row["condicion"],
                    float(row["oph_referencia"]), float(row["oph_minimo"]), float(row["oph_optimo"]), float(row["kg_h_referencia"]),
                    float(row["factor_precalibrado"]), float(row["factor_destrio_alto"]), row["dificultad"],
                    int(row["activo"]), row.get("observaciones", ""), now,
                ) for row in rows],
            )

    def reset_performance_defaults(self) -> None:
        self.save_performance_rules(DEFAULT_PERFORMANCE_RULES)

    def ensure_penalties_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_penalty_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    tipo_penalizacion TEXT NOT NULL,
                    ambito TEXT NOT NULL,
                    minutos_perdida REAL NOT NULL,
                    factor_rendimiento REAL NOT NULL,
                    aplica_por TEXT NOT NULL,
                    umbral TEXT,
                    activa INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_penalties_defaults(self) -> None:
        self.ensure_penalties_schema()
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_penalty_rules").fetchone()["n"]
            if existing == 0:
                self.save_penalty_rules(DEFAULT_PENALTY_RULES)

    def get_penalty_rules(self) -> list[dict]:
        self.ensure_penalties_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_penalty_rules ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def save_penalty_rules(self, rows: list[dict]) -> None:
        self.ensure_penalties_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_penalty_rules")
            conn.executemany(
                """
                INSERT INTO production_penalty_rules (
                    codigo, tipo_penalizacion, ambito, minutos_perdida, factor_rendimiento,
                    aplica_por, umbral, activa, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(
                    row["codigo"], row["tipo_penalizacion"], row["ambito"], float(row["minutos_perdida"]),
                    float(row["factor_rendimiento"]), row["aplica_por"], row.get("umbral", ""),
                    int(row["activa"]), row.get("observaciones", ""), now,
                ) for row in rows],
            )

    def reset_penalty_defaults(self) -> None:
        self.save_penalty_rules(DEFAULT_PENALTY_RULES)

    def ensure_semaphore_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_semaphore_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    tipo_regla TEXT NOT NULL,
                    ambito TEXT NOT NULL,
                    metrica TEXT NOT NULL,
                    operador TEXT NOT NULL,
                    umbral_amarillo REAL NOT NULL,
                    umbral_rojo REAL NOT NULL,
                    accion_sugerida TEXT,
                    activa INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_semaphore_defaults(self) -> None:
        self.ensure_semaphore_schema()
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_semaphore_rules").fetchone()["n"]
            if existing == 0:
                self.save_semaphore_rules(DEFAULT_SEMAPHORE_RULES)

    def get_semaphore_rules(self) -> list[dict]:
        self.ensure_semaphore_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_semaphore_rules ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def save_semaphore_rules(self, rows: list[dict]) -> None:
        self.ensure_semaphore_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_semaphore_rules")
            conn.executemany(
                """
                INSERT INTO production_semaphore_rules (
                    codigo, tipo_regla, ambito, metrica, operador,
                    umbral_amarillo, umbral_rojo, accion_sugerida,
                    activa, observaciones, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["codigo"], row["tipo_regla"], row["ambito"], row["metrica"], row["operador"],
                        float(row["umbral_amarillo"]), float(row["umbral_rojo"]), row.get("accion_sugerida", ""),
                        int(row.get("activa", 1)), row.get("observaciones", ""), now,
                    )
                    for row in rows
                ],
            )

    def reset_semaphore_defaults(self) -> None:
        self.save_semaphore_rules(DEFAULT_SEMAPHORE_RULES)

    def ensure_caliber_factors_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_caliber_performance_factors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    confeccion_familia TEXT NOT NULL,
                    grupo_calibre TEXT NOT NULL,
                    calibres_incluidos TEXT NOT NULL,
                    factor_rendimiento REAL NOT NULL,
                    aplica_a TEXT NOT NULL,
                    activo INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_caliber_factors_defaults(self) -> None:
        self.ensure_caliber_factors_schema()
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_caliber_performance_factors").fetchone()["n"]
            if existing == 0:
                self.save_caliber_performance_factors(DEFAULT_CALIBER_PERFORMANCE_FACTORS)

    def get_caliber_performance_factors(self) -> list[dict]:
        self.ensure_caliber_factors_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_caliber_performance_factors ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def save_caliber_performance_factors(self, rows: list[dict]) -> None:
        self.ensure_caliber_factors_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_caliber_performance_factors")
            conn.executemany(
                """
                INSERT INTO production_caliber_performance_factors (
                    codigo, confeccion_familia, grupo_calibre, calibres_incluidos,
                    factor_rendimiento, aplica_a, activo, observaciones, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        row["codigo"], row["confeccion_familia"], row["grupo_calibre"], row["calibres_incluidos"],
                        float(row["factor_rendimiento"]), row["aplica_a"], int(row["activo"]), row.get("observaciones", ""), now,
                    )
                    for row in rows
                ],
            )

    def reset_caliber_performance_factors_defaults(self) -> None:
        self.save_caliber_performance_factors(DEFAULT_CALIBER_PERFORMANCE_FACTORS)

    def ensure_unloading_priority_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_unloading_priority_rules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    criterio TEXT NOT NULL UNIQUE,
                    descripcion TEXT,
                    peso REAL NOT NULL DEFAULT 1.0,
                    activo INTEGER NOT NULL DEFAULT 1,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_unloading_priority_defaults(self) -> None:
        self.ensure_unloading_priority_schema()
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_unloading_priority_rules").fetchone()["n"]
            if existing == 0:
                self.save_unloading_priority_rules(DEFAULT_UNLOADING_PRIORITY_RULES, replace_existing=True)

    def get_unloading_priority_rules(self) -> list[dict]:
        self.ensure_unloading_priority_defaults()
        with get_connection() as conn:
            rows = conn.execute("SELECT * FROM production_unloading_priority_rules ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def save_unloading_priority_rules(self, rows: list[dict], replace_existing: bool = True) -> None:
        self.ensure_unloading_priority_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            if replace_existing:
                conn.execute("DELETE FROM production_unloading_priority_rules")
            conn.executemany(
                """
                INSERT INTO production_unloading_priority_rules (
                    criterio, descripcion, peso, activo, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(criterio) DO UPDATE SET
                    descripcion=excluded.descripcion,
                    peso=excluded.peso,
                    activo=excluded.activo,
                    observaciones=excluded.observaciones,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        row["criterio"],
                        row.get("descripcion", ""),
                        float(row.get("peso", 1.0)),
                        int(row.get("activo", 1)),
                        row.get("observaciones", ""),
                        now,
                    )
                    for row in rows
                ],
            )
