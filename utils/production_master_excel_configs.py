from __future__ import annotations

PRODUCTION_MASTER_EXCEL_CONFIGS = {
    "personal": {
        "key": "personal",
        "sheet_name": "Areas personal",
        "default_filename": "personal.xlsx",
        "columns": ["id", "area", "tipo_personal", "Directo", "Soporte", "Indirecto", "disponible", "minimo_operativo", "optimo", "activo", "observaciones"],
        "required_columns": ["area", "disponible", "minimo_operativo", "optimo", "activo"],
        "numeric_columns": ["disponible", "minimo_operativo", "optimo"],
        "boolean_columns": ["activo"],
        "unique_key": "area",
        "delete_missing_default": False,
        "extra_sheets": {
            "Resumen personal": {
                "columns": ["personal_total", "personal_directo", "personal_soporte", "personal_indirecto", "horas_por_persona", "ausencias_previstas", "observaciones"],
                "required_columns": ["horas_por_persona", "ausencias_previstas"],
                "numeric_columns": ["personal_total", "personal_directo", "personal_soporte", "personal_indirecto", "horas_por_persona", "ausencias_previstas"],
                "boolean_columns": [],
                "unique_key": "personal_total",
            }
        },
    },
    "flow_staffing": {
        "key": "flow_staffing", "sheet_name": "Dotacion flujos", "default_filename": "dotacion_flujos.xlsx",
        "columns": ["id", "linea_productiva", "area_puesto", "tipo_personal", "minimo", "optimo", "escala_con_ocupacion", "factor_ocupacion", "obligatorio", "activo", "observaciones"],
        "required_columns": ["linea_productiva", "area_puesto", "tipo_personal", "minimo", "optimo", "escala_con_ocupacion", "factor_ocupacion", "obligatorio", "activo"],
        "numeric_columns": ["minimo", "optimo", "factor_ocupacion"], "boolean_columns": ["escala_con_ocupacion", "obligatorio", "activo"], "unique_key": "linea_productiva|area_puesto", "delete_missing_default": False,
    },
    "packaging_types": {
        "key": "packaging_types", "sheet_name": "Confecciones", "default_filename": "confecciones.xlsx",
        "columns": ["id", "codigo", "descripcion", "familia", "subtipo", "kg_formato", "material", "tipo_malla", "requiere_precalibrado", "compatible_box", "activo", "observaciones"],
        "required_columns": ["codigo", "descripcion", "familia", "subtipo", "kg_formato", "activo"],
        "numeric_columns": ["kg_formato"], "boolean_columns": ["requiere_precalibrado", "compatible_box", "activo"], "unique_key": "codigo", "delete_missing_default": False,
    },

    "base_packaging": {
        "key": "base_packaging", "sheet_name": "Confecciones base", "default_filename": "confecciones_base.xlsx",
        "columns": ["id", "codigo", "descripcion", "grupo_confeccion", "perfil_confeccion", "familia_productiva", "subtipo_productivo", "kg_formato", "tipo_malla", "linea_productiva", "requiere_precalibrado", "compatible_box", "activo", "observaciones"],
        "required_columns": ["codigo", "descripcion", "grupo_confeccion", "perfil_confeccion", "familia_productiva", "subtipo_productivo", "kg_formato", "tipo_malla", "linea_productiva", "activo"],
        "numeric_columns": ["kg_formato"], "boolean_columns": ["requiere_precalibrado", "compatible_box", "activo"], "unique_key": "codigo", "delete_missing_default": False,
    },
    "lines": {
        "key": "lines", "sheet_name": "Maquinas lineas", "default_filename": "maquinas_lineas.xlsx",
        "columns": ["id", "codigo", "nombre", "tipo_linea", "familia_principal", "numero_maquinas", "activa", "capacidad_kg_h_referencia", "personal_minimo", "personal_optimo", "permite_precalibrado", "permite_box", "observaciones"],
        "required_columns": ["codigo", "nombre", "tipo_linea", "numero_maquinas", "capacidad_kg_h_referencia", "personal_minimo", "personal_optimo", "activa"],
        "numeric_columns": ["numero_maquinas", "capacidad_kg_h_referencia", "personal_minimo", "personal_optimo"], "boolean_columns": ["activa", "permite_precalibrado", "permite_box"], "unique_key": "codigo", "delete_missing_default": False,
    },
    "packaging_mapping": {
        "key": "packaging_mapping", "sheet_name": "Mapeo confecciones", "default_filename": "mapeo_confecciones.xlsx",
        "columns": ["codigo_mconfeccion", "nombre_mconfeccion", "descripcion_corta", "grupo_origen", "neto_origen", "npiezas_origen", "activa_origen", "familia_productiva", "subtipo_productivo", "kg_formato", "tipo_malla", "linea_productiva", "requiere_precalibrado", "compatible_box", "activo_produccion", "confianza_autodeteccion", "revisar", "observaciones"],
        "required_columns": ["codigo_mconfeccion", "familia_productiva", "subtipo_productivo", "kg_formato", "tipo_malla", "activo_produccion"],
        "numeric_columns": ["kg_formato", "neto_origen", "npiezas_origen"], "boolean_columns": ["activa_origen", "requiere_precalibrado", "compatible_box", "activo_produccion", "revisar"], "unique_key": "codigo_mconfeccion", "delete_missing_default": False,
    },
    "performance_rules": {
        "key": "performance_rules", "sheet_name": "Rendimientos", "default_filename": "rendimientos.xlsx",
        "columns": ["id", "codigo", "familia", "confeccion_formato", "tipo_linea", "condicion", "oph_referencia", "oph_minimo", "oph_optimo", "kg_h_referencia", "factor_precalibrado", "factor_destrio_alto", "dificultad", "activo", "observaciones"],
        "required_columns": ["codigo", "familia", "confeccion_formato", "tipo_linea", "condicion", "oph_referencia", "oph_minimo", "oph_optimo", "kg_h_referencia", "dificultad", "activo"],
        "numeric_columns": ["oph_referencia", "oph_minimo", "oph_optimo", "kg_h_referencia", "factor_precalibrado", "factor_destrio_alto"], "boolean_columns": ["activo"], "unique_key": "codigo", "delete_missing_default": False,
    },
    "penalty_rules": {
        "key": "penalty_rules", "sheet_name": "Penalizaciones", "default_filename": "penalizaciones.xlsx",
        "columns": ["id", "codigo", "tipo_penalizacion", "ambito", "minutos_perdida", "factor_rendimiento", "aplica_por", "umbral", "activa", "observaciones"],
        "required_columns": ["codigo", "tipo_penalizacion", "ambito", "minutos_perdida", "factor_rendimiento", "aplica_por", "umbral", "activa"],
        "numeric_columns": ["minutos_perdida", "factor_rendimiento", "umbral"], "boolean_columns": ["activa"], "unique_key": "codigo", "delete_missing_default": False,
    },
    "semaphore_rules": {
        "key": "semaphore_rules", "sheet_name": "Reglas semaforo", "default_filename": "reglas_semaforo.xlsx",
        "columns": ["id", "codigo", "tipo_regla", "ambito", "metrica", "operador", "umbral_amarillo", "umbral_rojo", "accion_sugerida", "activa", "observaciones"],
        "required_columns": ["codigo", "tipo_regla", "ambito", "metrica", "operador", "umbral_amarillo", "umbral_rojo", "activa"],
        "numeric_columns": ["umbral_amarillo", "umbral_rojo"], "boolean_columns": ["activa"], "unique_key": "codigo", "delete_missing_default": False,
    },
    "physical_resources": {
        "key": "physical_resources", "sheet_name": "Recursos fisicos", "default_filename": "recursos_fisicos.xlsx",
        "columns": ["id", "codigo", "nombre", "tipo_recurso", "familia_operativa", "capacidad_kg_h", "capacidad_por", "numero_unidades", "personal_minimo", "personal_optimo", "activo", "observaciones"],
        "required_columns": ["codigo", "nombre", "tipo_recurso", "familia_operativa", "capacidad_kg_h", "activo"],
        "numeric_columns": ["capacidad_kg_h", "numero_unidades", "personal_minimo", "personal_optimo"], "boolean_columns": ["activo"], "unique_key": "codigo", "delete_missing_default": False,
    },
    "resource_compatibilities": {
        "key": "resource_compatibilities", "sheet_name": "Compatibilidades", "default_filename": "compatibilidades_recursos.xlsx",
        "columns": ["id", "recurso_codigo", "compatible_con", "valor", "activo", "observaciones"],
        "required_columns": ["recurso_codigo", "compatible_con", "valor", "activo"],
        "numeric_columns": [], "boolean_columns": ["activo"], "unique_key": "recurso_codigo|compatible_con|valor", "delete_missing_default": False,
    },
    "resource_feeds": {
        "key": "resource_feeds", "sheet_name": "Alimentacion", "default_filename": "alimentacion_recursos.xlsx",
        "columns": ["id", "origen_codigo", "destino_codigo", "max_destinos_simultaneos", "requiere_precalibrado", "activo", "observaciones"],
        "required_columns": ["origen_codigo", "destino_codigo", "max_destinos_simultaneos", "activo"],
        "numeric_columns": ["max_destinos_simultaneos"], "boolean_columns": ["requiere_precalibrado", "activo"], "unique_key": "origen_codigo|destino_codigo", "delete_missing_default": False,
    },
    "resource_availability": {
        "key": "resource_availability", "sheet_name": "Disponibilidad", "default_filename": "disponibilidad_recursos.xlsx",
        "columns": ["id", "recurso_codigo", "contexto", "disponible", "motivo", "prioridad", "observaciones"],
        "required_columns": ["recurso_codigo", "contexto", "disponible", "prioridad"],
        "numeric_columns": ["prioridad"], "boolean_columns": ["disponible"], "unique_key": "recurso_codigo|contexto", "delete_missing_default": False,
    },
    "resources_flows": {
        "key": "resources_flows", "sheet_name": "Recursos físicos", "default_filename": "recursos_flujos.xlsx",
        "composite_sheets": ["Recursos físicos", "Compatibilidades", "Alimentación", "Disponibilidad"],
    },
    "caliber_factors": {
        "key": "caliber_factors", "sheet_name": "Factores calibre", "default_filename": "factores_calibre.xlsx",
        "columns": ["id", "codigo", "confeccion_familia", "grupo_calibre", "calibres_incluidos", "factor_rendimiento", "aplica_a", "activo", "observaciones"],
        "required_columns": ["codigo", "confeccion_familia", "grupo_calibre", "calibres_incluidos", "factor_rendimiento", "aplica_a", "activo"],
        "numeric_columns": ["factor_rendimiento"], "boolean_columns": ["activo"], "unique_key": "codigo", "delete_missing_default": False,
    },
}
