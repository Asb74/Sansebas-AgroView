from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3

from config import DB_DIR, DB_PEDIDOS
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




DEFAULT_BASE_PACKAGING = [
    {"codigo": "MALLA_1KG_TRAD", "descripcion": "Malla 1 kg tradicional", "grupo_confeccion": "MALLAS", "perfil_confeccion": "MALLA", "familia_productiva": "Malla", "subtipo_productivo": "Tradicional", "kg_formato": 1.0, "tipo_malla": "Tradicional", "linea_productiva": "MALLAS_TRADICIONAL", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_2KG_TRAD", "descripcion": "Malla 2 kg tradicional", "grupo_confeccion": "MALLAS", "perfil_confeccion": "MALLA", "familia_productiva": "Malla", "subtipo_productivo": "Tradicional", "kg_formato": 2.0, "tipo_malla": "Tradicional", "linea_productiva": "MALLAS_TRADICIONAL", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_2KG_GIRSAC", "descripcion": "Malla 2 kg girsac", "grupo_confeccion": "MALLAS", "perfil_confeccion": "MALLA", "familia_productiva": "Malla", "subtipo_productivo": "Girsac", "kg_formato": 2.0, "tipo_malla": "Girsac", "linea_productiva": "MALLAS_GIRSAC", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_2KG_CLIP", "descripcion": "Malla 2 kg clip-to-clip", "grupo_confeccion": "MALLAS", "perfil_confeccion": "MALLA", "familia_productiva": "Malla", "subtipo_productivo": "Clip-to-clip", "kg_formato": 2.0, "tipo_malla": "Clip-to-clip", "linea_productiva": "MALLAS_CLIP", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_3KG_GIRSAC", "descripcion": "Malla 3 kg girsac", "grupo_confeccion": "MALLAS", "perfil_confeccion": "MALLA", "familia_productiva": "Malla", "subtipo_productivo": "Girsac", "kg_formato": 3.0, "tipo_malla": "Girsac", "linea_productiva": "MALLAS_GIRSAC", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_4KG_GIRSAC", "descripcion": "Malla 4 kg girsac", "grupo_confeccion": "MALLAS", "perfil_confeccion": "MALLA", "familia_productiva": "Malla", "subtipo_productivo": "Girsac", "kg_formato": 4.0, "tipo_malla": "Girsac", "linea_productiva": "MALLAS_GIRSAC", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "MALLA_4KG_TRAD", "descripcion": "Malla 4 kg tradicional", "grupo_confeccion": "MALLAS", "perfil_confeccion": "MALLA", "familia_productiva": "Malla", "subtipo_productivo": "Tradicional", "kg_formato": 4.0, "tipo_malla": "Tradicional", "linea_productiva": "MALLAS_TRADICIONAL", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "ENCAJADO_5KG", "descripcion": "Encajado 5 kg", "grupo_confeccion": "ENCAJADO", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Encajado", "subtipo_productivo": "Caja", "kg_formato": 5.0, "tipo_malla": "No aplica", "linea_productiva": "ENCAJADO", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "ENCAJADO_10KG", "descripcion": "Encajado 10 kg", "grupo_confeccion": "ENCAJADO", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Encajado", "subtipo_productivo": "Caja", "kg_formato": 10.0, "tipo_malla": "No aplica", "linea_productiva": "ENCAJADO", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "ENCAJADO_15KG", "descripcion": "Encajado 15 kg", "grupo_confeccion": "ENCAJADO", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Encajado", "subtipo_productivo": "Caja", "kg_formato": 15.0, "tipo_malla": "No aplica", "linea_productiva": "ENCAJADO", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "ENCAJADO_20KG", "descripcion": "Encajado 20 kg", "grupo_confeccion": "ENCAJADO", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Encajado", "subtipo_productivo": "Caja", "kg_formato": 20.0, "tipo_malla": "No aplica", "linea_productiva": "ENCAJADO", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "ALVEOLO_4KG", "descripcion": "Alvéolo 4 kg", "grupo_confeccion": "ALVEOLOS", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Encajado", "subtipo_productivo": "Alvéolo", "kg_formato": 4.0, "tipo_malla": "No aplica", "linea_productiva": "ENCAJADO", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "ALVEOLO_8KG", "descripcion": "Alvéolo 8 kg", "grupo_confeccion": "ALVEOLOS", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Encajado", "subtipo_productivo": "Alvéolo", "kg_formato": 8.0, "tipo_malla": "No aplica", "linea_productiva": "ENCAJADO", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "GRANEL_10KG", "descripcion": "Granel 10 kg", "grupo_confeccion": "GRANEL", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Granel", "subtipo_productivo": "Granel", "kg_formato": 10.0, "tipo_malla": "No aplica", "linea_productiva": "GRANEL_MANUAL", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "GRANEL_15KG", "descripcion": "Granel 15 kg", "grupo_confeccion": "GRANEL", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Granel", "subtipo_productivo": "Granel", "kg_formato": 15.0, "tipo_malla": "No aplica", "linea_productiva": "GRANEL_MANUAL", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
    {"codigo": "GRANELERA", "descripcion": "Granelera", "grupo_confeccion": "GRANELERA", "perfil_confeccion": "EXIGENTE", "familia_productiva": "Granelera", "subtipo_productivo": "Granelera", "kg_formato": 0.0, "tipo_malla": "No aplica", "linea_productiva": "GRANELERA", "requiere_precalibrado": 0, "compatible_box": 0, "activo": 1, "observaciones": ""},
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


DEFAULT_PHYSICAL_RESOURCES = [
    ("COMPACTA","Compacta","Alimentación","Entrada fruta",7000.0,"Recurso",1,1,2,1,"Alimentación principal; no siempre puede alimentar todas las pesadoras."),
    ("CALIBRADOR_PRINCIPAL","Calibrador principal","Calibrador","Clasificación",15000.0,"Recurso",1,1,2,1,""),
    ("AWETTA","Calibrador Awetta","Calibrador auxiliar","Clasificación",4000.0,"Recurso",1,1,2,1,"Segundo calibrador pequeño. Disponible para cítricos/mandarinas solo si no está ocupado por caqui/fruta de hueso."),
    ("TOLVA","Tolva","Alimentación","Entrada fruta",4000.0,"Recurso",1,1,1,1,""),
    ("PESADORA_1","Pesadora 1","Pesadora","Mallas",300.0,"Recurso",1,1,1,1,"Solo Girsac según configuración actual."),
    ("PESADORA_2","Pesadora 2","Pesadora","Mallas",300.0,"Recurso",1,1,1,1,"Dos brazos Girsac."),
    ("PESADORA_3","Pesadora 3","Pesadora","Mallas",300.0,"Recurso",1,1,1,1,"Compatible Girsac y tradicional."),
    ("PESADORA_4","Pesadora 4","Pesadora","Mallas",300.0,"Recurso",1,1,1,1,"Compatible Girsac y tradicional."),
]
DEFAULT_RESOURCE_COMPATIBILITIES = [("PESADORA_1","tipo_malla","Girsac",1,""),("PESADORA_2","tipo_malla","Girsac",1,""),("PESADORA_3","tipo_malla","Girsac",1,""),("PESADORA_3","tipo_malla","Tradicional",1,""),("PESADORA_4","tipo_malla","Girsac",1,""),("PESADORA_4","tipo_malla","Tradicional",1,"")]
DEFAULT_RESOURCE_FEEDS = [("COMPACTA","CALIBRADOR_PRINCIPAL",1,0,1,""),("CALIBRADOR_PRINCIPAL","PESADORA_1",4,0,1,""),("CALIBRADOR_PRINCIPAL","PESADORA_2",4,0,1,""),("CALIBRADOR_PRINCIPAL","PESADORA_3",4,0,1,""),("CALIBRADOR_PRINCIPAL","PESADORA_4",4,0,1,""),("COMPACTA","AWETTA",1,0,1,"Awetta puede alimentarse desde compacta cuando está disponible.")]
DEFAULT_RESOURCE_AVAILABILITY = [("AWETTA","CITRICOS",1,"Libre para apoyo si no hay otros cultivos.",1,""),("AWETTA","MANDARINAS",1,"Libre para apoyo si no hay otros cultivos.",1,""),("AWETTA","CAQUI",0,"Ocupada por caqui / no disponible para apoyo cítricos.",1,""),("AWETTA","FRUTA_HUESO",0,"Ocupada por fruta de hueso.",1,"")]


class ProductionSettingsRepository:
    def __init__(self) -> None:
        self.ensure_defaults()
        self.ensure_staff_defaults()
        self.ensure_lines_defaults()
        self.ensure_packaging_defaults()
        self.ensure_base_packaging_defaults()
        self.ensure_performance_defaults()
        self.ensure_penalties_defaults()
        self.ensure_semaphore_defaults()
        self.ensure_caliber_factors_defaults()
        self.ensure_unloading_priority_defaults()
        self.ensure_physical_resources_defaults()
        self.ensure_resource_compatibilities_defaults()
        self.ensure_resource_feeds_defaults()
        self.ensure_resource_availability_defaults()

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
        self.ensure_base_packaging_defaults()
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

    def ensure_base_packaging_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_base_packaging (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    descripcion TEXT NOT NULL,
                    grupo_confeccion TEXT NOT NULL,
                    perfil_confeccion TEXT NOT NULL,
                    familia_productiva TEXT NOT NULL,
                    subtipo_productivo TEXT NOT NULL,
                    kg_formato REAL NOT NULL,
                    tipo_malla TEXT NOT NULL,
                    linea_productiva TEXT NOT NULL,
                    requiere_precalibrado INTEGER NOT NULL,
                    compatible_box INTEGER NOT NULL,
                    activo INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_base_packaging_defaults(self) -> None:
        self.ensure_base_packaging_schema()
        with get_connection() as conn:
            existing = conn.execute("SELECT COUNT(*) AS n FROM production_base_packaging").fetchone()["n"]
            if existing == 0:
                self.save_base_packaging(DEFAULT_BASE_PACKAGING)

    def get_base_packaging(self, active_only: bool = False) -> list[dict]:
        self.ensure_base_packaging_defaults()
        sql = "SELECT * FROM production_base_packaging"
        if active_only:
            sql += " WHERE activo = 1"
        sql += " ORDER BY id"
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    def save_base_packaging(self, rows: list[dict]) -> None:
        self.ensure_base_packaging_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_base_packaging")
            conn.executemany(
                """
                INSERT INTO production_base_packaging (
                    codigo, descripcion, grupo_confeccion, perfil_confeccion,
                    familia_productiva, subtipo_productivo, kg_formato, tipo_malla,
                    linea_productiva, requiere_precalibrado, compatible_box,
                    activo, observaciones, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [(
                    row["codigo"], row["descripcion"], row["grupo_confeccion"], row["perfil_confeccion"],
                    row["familia_productiva"], row["subtipo_productivo"], float(row["kg_formato"]), row["tipo_malla"],
                    row["linea_productiva"], int(row.get("requiere_precalibrado", 0)), int(row.get("compatible_box", 0)),
                    int(row.get("activo", 1)), row.get("observaciones", ""), now,
                ) for row in rows]
            )

    def reset_base_packaging_defaults(self) -> None:
        self.save_base_packaging(DEFAULT_BASE_PACKAGING)

    def delete_packaging_type(self, packaging_id: int) -> None:
        self.ensure_packaging_schema()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_packaging_types WHERE id = ?", (packaging_id,))

    def ensure_packaging_mapping_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_packaging_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo_mconfeccion TEXT NOT NULL UNIQUE,
                    nombre_mconfeccion TEXT,
                    descripcion_corta TEXT,
                    grupo_origen TEXT,
                    neto_origen REAL,
                    npiezas_origen REAL,
                    activa_origen TEXT,
                    familia_productiva TEXT NOT NULL,
                    subtipo_productivo TEXT NOT NULL,
                    kg_formato REAL NOT NULL,
                    tipo_malla TEXT NOT NULL,
                    linea_productiva TEXT,
                    requiere_precalibrado INTEGER NOT NULL,
                    compatible_box INTEGER NOT NULL,
                    activo_produccion INTEGER NOT NULL,
                    confianza_autodeteccion TEXT,
                    revisar INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def load_mconfecciones_from_dbpedidos(self) -> list[dict]:
        db_path = Path(DB_DIR) / DB_PEDIDOS
        if not db_path.exists():
            return []
        with sqlite3.connect(db_path.as_posix()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT CODIGO,NOMBRE,DESCRIPCORTA,NETO,ACTIVA,GRUPO,NPIEZAS FROM MConfecciones').fetchall()
        return [dict(row) for row in rows]

    def autofill_packaging_mapping_from_mconfecciones(self, overwrite: bool = False) -> dict:
        self.ensure_packaging_mapping_schema()
        source_rows = self.load_mconfecciones_from_dbpedidos()
        existing = {row["codigo_mconfeccion"]: dict(row) for row in self.get_packaging_mapping(False)}
        created = 0
        updated = 0
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for src in source_rows:
                codigo = str(src.get("CODIGO", "")).strip()
                if not codigo:
                    continue
                payload = self._build_mapping_row(src)
                payload["updated_at"] = now
                if codigo not in existing:
                    created += 1
                    conn.execute("""INSERT INTO production_packaging_mapping (
                        codigo_mconfeccion,nombre_mconfeccion,descripcion_corta,grupo_origen,neto_origen,npiezas_origen,activa_origen,familia_productiva,subtipo_productivo,kg_formato,tipo_malla,linea_productiva,requiere_precalibrado,compatible_box,activo_produccion,confianza_autodeteccion,revisar,observaciones,updated_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(payload[k] for k in payload))
                elif overwrite:
                    updated += 1
                    conn.execute("""UPDATE production_packaging_mapping SET
                        nombre_mconfeccion=?,descripcion_corta=?,grupo_origen=?,neto_origen=?,npiezas_origen=?,activa_origen=?,familia_productiva=?,subtipo_productivo=?,kg_formato=?,tipo_malla=?,linea_productiva=?,requiere_precalibrado=?,compatible_box=?,activo_produccion=?,confianza_autodeteccion=?,revisar=?,observaciones=?,updated_at=?
                        WHERE codigo_mconfeccion=?""",
                        tuple(payload[k] for k in payload if k != "codigo_mconfeccion") + (codigo,))
        return {"source_total": len(source_rows), "created": created, "updated": updated}

    def get_packaging_mapping(self, show_only_review: bool = False) -> list[dict]:
        self.ensure_packaging_mapping_schema()
        sql = "SELECT * FROM production_packaging_mapping"
        if show_only_review:
            sql += " WHERE revisar = 1"
        sql += " ORDER BY codigo_mconfeccion"
        with get_connection() as conn:
            rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]

    def save_packaging_mapping(self, rows: list[dict]) -> None:
        self.ensure_packaging_mapping_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for row in rows:
                conn.execute("""INSERT INTO production_packaging_mapping (
                    codigo_mconfeccion,nombre_mconfeccion,descripcion_corta,grupo_origen,neto_origen,npiezas_origen,activa_origen,familia_productiva,subtipo_productivo,kg_formato,tipo_malla,linea_productiva,requiere_precalibrado,compatible_box,activo_produccion,confianza_autodeteccion,revisar,observaciones,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(codigo_mconfeccion) DO UPDATE SET
                    nombre_mconfeccion=excluded.nombre_mconfeccion,descripcion_corta=excluded.descripcion_corta,grupo_origen=excluded.grupo_origen,neto_origen=excluded.neto_origen,npiezas_origen=excluded.npiezas_origen,activa_origen=excluded.activa_origen,familia_productiva=excluded.familia_productiva,subtipo_productivo=excluded.subtipo_productivo,kg_formato=excluded.kg_formato,tipo_malla=excluded.tipo_malla,linea_productiva=excluded.linea_productiva,requiere_precalibrado=excluded.requiere_precalibrado,compatible_box=excluded.compatible_box,activo_produccion=excluded.activo_produccion,confianza_autodeteccion=excluded.confianza_autodeteccion,revisar=excluded.revisar,observaciones=excluded.observaciones,updated_at=excluded.updated_at""",
                (row["codigo_mconfeccion"], row.get("nombre_mconfeccion", ""), row.get("descripcion_corta", ""), row.get("grupo_origen", ""), float(row.get("neto_origen", 0) or 0), float(row.get("npiezas_origen", 0) or 0), row.get("activa_origen", ""), row["familia_productiva"], row["subtipo_productivo"], float(row.get("kg_formato", 0) or 0), row["tipo_malla"], row.get("linea_productiva", ""), int(row.get("requiere_precalibrado", 0)), int(row.get("compatible_box", 0)), int(row.get("activo_produccion", 1)), row.get("confianza_autodeteccion", "Media"), int(row.get("revisar", 0)), row.get("observaciones", ""), now))

    def reset_packaging_mapping_autodetect(self) -> None:
        self.autofill_packaging_mapping_from_mconfecciones(overwrite=True)

    def _build_mapping_row(self, src: dict) -> dict:
        grupo = str(src.get("GRUPO") or "")
        nombre = str(src.get("NOMBRE") or "")
        desc = str(src.get("DESCRIPCORTA") or "")
        texto = f"{nombre} {desc} {grupo}".upper()
        familia = "Otro"
        if "ENCAJADO" in grupo.upper() or "ALVEOLOS" in grupo.upper(): familia = "Encajado"
        elif "GRANEL" in grupo.upper(): familia = "Granel"
        elif "MALLA" in grupo.upper() or "MALLAS" in grupo.upper(): familia = "Malla"
        subtipo = "Otro"
        if "GIRS" in texto: subtipo = "Girsac"
        elif "FLOW" in texto: subtipo = "Flowpack"
        elif "CLIP" in texto: subtipo = "Clip-to-clip"
        elif "GRANEL" in texto: subtipo = "Granel"
        elif "ENCAJADO" in texto: subtipo = "Caja"
        elif "ALV" in texto: subtipo = "Alvéolo"
        elif familia == "Malla": subtipo = "Tradicional"
        kg = float(src.get("NETO") or 0)
        npiezas = float(src.get("NPIEZAS") or 0)
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*KG", texto)
        if match: kg = float(match.group(1).replace(",", "."))
        elif familia == "Malla" and npiezas > 0 and kg > 0: kg = kg / npiezas
        elif familia not in ("Encajado", "Granel"): kg = 0.0
        revisar = 1 if kg == 0 or subtipo == "Otro" or familia == "Otro" else 0
        tipo_malla = "No aplica" if familia != "Malla" else ("Tradicional" if subtipo == "Tradicional" else subtipo if subtipo in ("Girsac", "Clip-to-clip", "Flowpack") else "Tradicional")
        linea = {"Tradicional": "MALLAS_TRADICIONAL", "Clip-to-clip": "MALLAS_CLIP", "Girsac": "MALLAS_GIRSAC"}.get(subtipo, "ENCAJADO" if familia == "Encajado" else "GRANEL_MANUAL" if familia == "Granel" else "GRANELERA" if familia == "Granelera" else "OTRO")
        activa = str(src.get("ACTIVA") or "").upper()
        activo_produccion = 1 if activa not in ("N",) else 0
        if activa not in ("S", "N"): revisar = 1
        confianza = "Alta" if revisar == 0 else ("Media" if familia != "Otro" else "Baja")
        return {"codigo_mconfeccion": str(src.get("CODIGO", "")).strip(), "nombre_mconfeccion": nombre, "descripcion_corta": desc, "grupo_origen": grupo, "neto_origen": float(src.get("NETO") or 0), "npiezas_origen": npiezas, "activa_origen": src.get("ACTIVA", ""), "familia_productiva": familia, "subtipo_productivo": subtipo, "kg_formato": kg, "tipo_malla": tipo_malla, "linea_productiva": linea, "requiere_precalibrado": 1 if "PRECALIBRADO" in texto else 0, "compatible_box": 1 if ("BOX" in texto or familia in ("Granel", "Granelera")) else 0, "activo_produccion": activo_produccion, "confianza_autodeteccion": confianza, "revisar": revisar, "observaciones": ""}


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
        self.ensure_physical_resources_defaults()
        self.ensure_resource_compatibilities_defaults()
        self.ensure_resource_feeds_defaults()
        self.ensure_resource_availability_defaults()
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

    def ensure_physical_resources_schema(self) -> None:
        with get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS production_physical_resources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    codigo TEXT NOT NULL UNIQUE,
                    nombre TEXT NOT NULL,
                    tipo_recurso TEXT NOT NULL,
                    familia_operativa TEXT NOT NULL,
                    capacidad_kg_h REAL NOT NULL,
                    capacidad_por TEXT NOT NULL,
                    numero_unidades INTEGER NOT NULL,
                    personal_minimo INTEGER NOT NULL,
                    personal_optimo INTEGER NOT NULL,
                    activo INTEGER NOT NULL,
                    observaciones TEXT,
                    updated_at TEXT
                )
                """
            )

    def ensure_physical_resources_defaults(self) -> None:
        self.ensure_physical_resources_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for row in DEFAULT_PHYSICAL_RESOURCES:
                conn.execute("INSERT INTO production_physical_resources (codigo,nombre,tipo_recurso,familia_operativa,capacidad_kg_h,capacidad_por,numero_unidades,personal_minimo,personal_optimo,activo,observaciones,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(codigo) DO NOTHING", (*row, now))

    def get_physical_resources(self) -> list[dict]:
        self.ensure_physical_resources_defaults()
        with get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM production_physical_resources ORDER BY id").fetchall()]

    def save_physical_resources(self, rows: list[dict]) -> None:
        self.ensure_physical_resources_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_physical_resources")
            for row in rows:
                conn.execute("INSERT INTO production_physical_resources (codigo,nombre,tipo_recurso,familia_operativa,capacidad_kg_h,capacidad_por,numero_unidades,personal_minimo,personal_optimo,activo,observaciones,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (row["codigo"], row["nombre"], row["tipo_recurso"], row["familia_operativa"], float(row.get("capacidad_kg_h", 0)), row.get("capacidad_por", "Recurso"), int(row.get("numero_unidades", 1)), int(row.get("personal_minimo", 0)), int(row.get("personal_optimo", 0)), int(row.get("activo", 1)), row.get("observaciones", ""), now))

    def ensure_resource_compatibilities_schema(self) -> None:
        with get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS production_resource_compatibilities (id INTEGER PRIMARY KEY AUTOINCREMENT,recurso_codigo TEXT NOT NULL,compatible_con TEXT NOT NULL,valor TEXT NOT NULL,activo INTEGER NOT NULL,observaciones TEXT,updated_at TEXT, UNIQUE(recurso_codigo, compatible_con, valor))")

    def ensure_resource_compatibilities_defaults(self) -> None:
        self.ensure_resource_compatibilities_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for row in DEFAULT_RESOURCE_COMPATIBILITIES:
                conn.execute("INSERT INTO production_resource_compatibilities (recurso_codigo,compatible_con,valor,activo,observaciones,updated_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(recurso_codigo, compatible_con, valor) DO NOTHING", (*row, now))

    def get_resource_compatibilities(self) -> list[dict]:
        self.ensure_resource_compatibilities_defaults()
        with get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM production_resource_compatibilities ORDER BY id").fetchall()]

    def save_resource_compatibilities(self, rows: list[dict]) -> None:
        self.ensure_resource_compatibilities_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_resource_compatibilities")
            for row in rows:
                conn.execute("INSERT INTO production_resource_compatibilities (recurso_codigo,compatible_con,valor,activo,observaciones,updated_at) VALUES (?, ?, ?, ?, ?, ?)", (row["recurso_codigo"], row["compatible_con"], row["valor"], int(row.get("activo", 1)), row.get("observaciones", ""), now))

    def ensure_resource_feeds_schema(self) -> None:
        with get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS production_resource_feeds (id INTEGER PRIMARY KEY AUTOINCREMENT,origen_codigo TEXT NOT NULL,destino_codigo TEXT NOT NULL,max_destinos_simultaneos INTEGER NOT NULL,requiere_precalibrado INTEGER NOT NULL,activo INTEGER NOT NULL,observaciones TEXT,updated_at TEXT, UNIQUE(origen_codigo, destino_codigo))")

    def ensure_resource_feeds_defaults(self) -> None:
        self.ensure_resource_feeds_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for row in DEFAULT_RESOURCE_FEEDS:
                conn.execute("INSERT INTO production_resource_feeds (origen_codigo,destino_codigo,max_destinos_simultaneos,requiere_precalibrado,activo,observaciones,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(origen_codigo, destino_codigo) DO NOTHING", (*row, now))

    def get_resource_feeds(self) -> list[dict]:
        self.ensure_resource_feeds_defaults()
        with get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM production_resource_feeds ORDER BY id").fetchall()]

    def save_resource_feeds(self, rows: list[dict]) -> None:
        self.ensure_resource_feeds_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_resource_feeds")
            for row in rows:
                conn.execute("INSERT INTO production_resource_feeds (origen_codigo,destino_codigo,max_destinos_simultaneos,requiere_precalibrado,activo,observaciones,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (row["origen_codigo"], row["destino_codigo"], int(row.get("max_destinos_simultaneos", 1)), int(row.get("requiere_precalibrado", 0)), int(row.get("activo", 1)), row.get("observaciones", ""), now))

    def ensure_resource_availability_schema(self) -> None:
        with get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS production_resource_availability (id INTEGER PRIMARY KEY AUTOINCREMENT,recurso_codigo TEXT NOT NULL,contexto TEXT NOT NULL,disponible INTEGER NOT NULL,motivo TEXT,prioridad INTEGER NOT NULL,observaciones TEXT,updated_at TEXT, UNIQUE(recurso_codigo, contexto))")

    def ensure_resource_availability_defaults(self) -> None:
        self.ensure_resource_availability_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            for row in DEFAULT_RESOURCE_AVAILABILITY:
                conn.execute("INSERT INTO production_resource_availability (recurso_codigo,contexto,disponible,motivo,prioridad,observaciones,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(recurso_codigo, contexto) DO NOTHING", (*row, now))

    def get_resource_availability(self) -> list[dict]:
        self.ensure_resource_availability_defaults()
        with get_connection() as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM production_resource_availability ORDER BY id").fetchall()]

    def save_resource_availability(self, rows: list[dict]) -> None:
        self.ensure_resource_availability_schema()
        now = datetime.utcnow().isoformat()
        with get_connection() as conn:
            conn.execute("DELETE FROM production_resource_availability")
            for row in rows:
                conn.execute("INSERT INTO production_resource_availability (recurso_codigo,contexto,disponible,motivo,prioridad,observaciones,updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)", (row["recurso_codigo"], row["contexto"], int(row.get("disponible", 1)), row.get("motivo", ""), int(row.get("prioridad", 1)), row.get("observaciones", ""), now))
