from __future__ import annotations

PRODUCTION_MASTER_EXCEL_CONFIGS = {
    "semaphore_rules": {
        "key": "semaphore_rules",
        "sheet_name": "Reglas semaforo",
        "default_filename": "reglas_semaforo.xlsx",
        "columns": ["id", "codigo", "tipo_regla", "ambito", "metrica", "operador", "umbral_amarillo", "umbral_rojo", "accion_sugerida", "activa", "observaciones"],
        "required_columns": ["codigo", "tipo_regla", "ambito", "metrica", "operador", "umbral_amarillo", "umbral_rojo", "activa"],
        "numeric_columns": ["umbral_amarillo", "umbral_rojo"],
        "boolean_columns": ["activa"],
        "unique_key": "codigo",
        "allow_insert": True,
        "allow_update": True,
        "delete_missing_default": False,
    },
    "penalty_rules": {
        "key": "penalty_rules", "sheet_name": "Penalizaciones", "default_filename": "penalizaciones.xlsx",
        "columns": ["id", "codigo", "tipo_penalizacion", "ambito", "aplica_por", "minutos_penalizacion", "activa", "observaciones"],
        "required_columns": ["codigo", "tipo_penalizacion", "ambito", "aplica_por", "minutos_penalizacion", "activa"],
        "numeric_columns": ["minutos_penalizacion"], "boolean_columns": ["activa"], "unique_key": "codigo", "allow_insert": True, "allow_update": True, "delete_missing_default": False,
    },
    "performance_rules": {
        "key": "performance_rules", "sheet_name": "Rendimientos", "default_filename": "rendimientos.xlsx",
        "columns": ["id", "codigo", "familia", "linea_tipo", "condicion", "oph", "kg_hora", "dificultad", "activa", "observaciones"],
        "required_columns": ["codigo", "familia", "linea_tipo", "oph", "kg_hora", "activa"],
        "numeric_columns": ["oph", "kg_hora"], "boolean_columns": ["activa"], "unique_key": "codigo", "allow_insert": True, "allow_update": True, "delete_missing_default": False,
    },
    "caliber_factors": {
        "key": "caliber_factors", "sheet_name": "Factores calibre", "default_filename": "factores_calibre.xlsx",
        "columns": ["id", "codigo", "familia", "grupo_calibre", "factor", "aplica_a", "activo", "observaciones"],
        "required_columns": ["codigo", "familia", "grupo_calibre", "factor", "aplica_a", "activo"],
        "numeric_columns": ["factor"], "boolean_columns": ["activo"], "unique_key": "codigo", "allow_insert": True, "allow_update": True, "delete_missing_default": False,
    },
    "lines": {
        "key": "lines", "sheet_name": "Maquinas lineas", "default_filename": "maquinas_lineas.xlsx",
        "columns": ["id", "codigo", "nombre", "tipo", "familia", "capacidad_hora", "activa", "observaciones"],
        "required_columns": ["codigo", "nombre", "tipo", "capacidad_hora", "activa"],
        "numeric_columns": ["capacidad_hora"], "boolean_columns": ["activa"], "unique_key": "codigo", "allow_insert": True, "allow_update": True, "delete_missing_default": False,
    },
    "packaging_types": {
        "key": "packaging_types", "sheet_name": "Confecciones", "default_filename": "confecciones.xlsx",
        "columns": ["id", "codigo", "descripcion", "familia", "subtipo", "kg_formato", "material", "tipo_malla", "requiere_precalibrado", "compatible_box", "activo", "observaciones"],
        "required_columns": ["codigo", "descripcion", "familia", "subtipo", "kg_formato", "activo"],
        "numeric_columns": ["kg_formato"], "boolean_columns": ["requiere_precalibrado", "compatible_box", "activo"], "unique_key": "codigo", "allow_insert": True, "allow_update": True, "delete_missing_default": False,
    },
    "packaging_mapping": {
        "key": "packaging_mapping", "sheet_name": "Mapeo confecciones", "default_filename": "mapeo_confecciones.xlsx",
        "columns": ["codigo_mconfeccion", "nombre_mconfeccion", "descripcion_corta", "grupo_origen", "neto_origen", "npiezas_origen", "activa_origen", "familia_productiva", "subtipo_productivo", "kg_formato", "tipo_malla", "linea_productiva", "requiere_precalibrado", "compatible_box", "activo_produccion", "confianza_autodeteccion", "revisar", "observaciones"],
        "required_columns": ["codigo_mconfeccion", "familia_productiva", "subtipo_productivo", "kg_formato", "tipo_malla", "activo_produccion"],
        "numeric_columns": ["kg_formato", "neto_origen", "npiezas_origen"], "boolean_columns": ["activa_origen", "requiere_precalibrado", "compatible_box", "activo_produccion", "revisar"], "unique_key": "codigo_mconfeccion", "allow_insert": True, "allow_update": True, "delete_missing_default": False,
    },
    "staff_areas": {
        "key": "staff_areas", "sheet_name": "Personal", "default_filename": "personal.xlsx",
        "columns": ["id", "area", "tipo_personal", "disponible", "minimo_operativo", "optimo", "activo", "observaciones"],
        "required_columns": ["area", "tipo_personal", "disponible", "minimo_operativo", "optimo", "activo"],
        "numeric_columns": ["disponible", "minimo_operativo", "optimo"], "boolean_columns": ["activo"], "unique_key": "area", "allow_insert": True, "allow_update": True, "delete_missing_default": False,
    },
}
