from __future__ import annotations

from collections import defaultdict
from math import ceil
import logging
import re
import unicodedata

from db.production_settings_repository import ProductionSettingsRepository
from services.planning_service import PlanningService
from services.pedidos_previstos_service import PEDIDOS_PREVISTOS_PATH as PEDIDOS_PREVISTOS_JSON_PATH, cargar_pedidos_previstos_filtrados

logger = logging.getLogger(__name__)


class ProductionCapacityService:
    PEDIDOS_PREVISTOS_PATH = PEDIDOS_PREVISTOS_JSON_PATH
    RESOURCE_USAGE_INFORMATIVE = "informative"
    RESOURCE_USAGE_RESTRICTIVE = "restrictive"
    # Maestro futuro: production_staff_flexibility. En esta fase solo se carga/documenta
    # para diseñar coberturas alternativas posteriores. Cuando se active, deberá cubrir
    # déficits de target_area con sobrantes reales de source_area, consumir esas personas
    # y aplicar efficiency_factor sin sumar esa cobertura a la disponibilidad base.

    def __init__(self) -> None:
        self.planning = PlanningService()
        self.prod_repo = ProductionSettingsRepository()

    def load_capacity_inputs(self, filters: dict, modo_pedidos: str = "10_dias") -> dict:
        pedidos_reales, _kpi = self.planning.load_pedidos_pendientes(filters, modo_pedidos)
        pedidos_previstos = self._load_forecast_orders(filters)
        return {
            "pedidos_reales": pedidos_reales,
            "pedidos_previstos": pedidos_previstos,
            "packaging_mapping": self.prod_repo.get_packaging_mapping(False),
            "base_packaging": self.prod_repo.get_base_packaging(active_only=True),
            "performance_rules": self.prod_repo.get_performance_rules(),
            "caliber_factors": self.prod_repo.get_caliber_performance_factors(),
            "personnel": self.prod_repo.get_staff_summary(),
            "staff_areas": self.prod_repo.get_staff_areas(),
            "flow_staffing": self.prod_repo.get_flow_staffing(active_only=True),
            "lines": self.prod_repo.get_lines(),
            "physical_resources": self.prod_repo.get_physical_resources(),
            "resource_compatibilities": self.prod_repo.get_resource_compatibilities(),
            "resource_feeds": self.prod_repo.get_resource_feeds(),
            "resource_availability": self.prod_repo.get_resource_availability(),
            "productive_families": self.prod_repo.get_productive_families(active_only=True),
            "line_capacity_config": self.prod_repo.get_line_capacity_config(active_only=True),
            "line_required_resources": self.prod_repo.get_line_required_resources(active_only=True),
            "staff_area_equivalences": self.prod_repo.get_staff_area_equivalences(active_only=True),
            "staff_polyvalence": self.prod_repo.get_staff_polyvalence(active_only=True),
            "staff_flexibility": self.prod_repo.get_staff_flexibility(),
            "semaphore_rules": self.prod_repo.get_semaphore_rules(),
            "general_settings": self.prod_repo.get_general_settings(),
        }

    def build_capacity_simulation(self, filters: dict, modo_pedidos: str = "10_dias") -> dict:
        inputs = self.load_capacity_inputs(filters, modo_pedidos)
        inputs["filters"] = filters
        mapped, incidencias = self.map_orders_to_productive_config(inputs["pedidos_reales"], inputs["pedidos_previstos"], inputs)
        line = self.calculate_line_capacity(mapped, inputs)
        staffing = self.calculate_staffing_requirements({"line_rows": line, "inputs": inputs})
        fam = self.calculate_family_capacity(mapped, inputs, staffing["rows"])
        resource_rows, resource_incidencias = self.calculate_physical_resource_capacity(mapped, inputs)
        bottleneck = self.detect_bottleneck(resource_rows)
        personnel_resources = self.calculate_resource_personnel(resource_rows)
        summary = self.calculate_capacity_summary(mapped, fam, line, inputs)
        summary.update({
            "personal_minimo_flujo": staffing["summary"]["personal_minimo_requerido"],
            "personal_optimo_flujo": staffing["summary"]["personal_optimo_requerido"],
            "personal_estimado_flujo": staffing["summary"]["personal_necesario_estimado"],
            "deficit_personal_flujo": staffing["summary"]["deficit_personal"],
        })
        summary.update({
            "recurso_cuello_botella": bottleneck.get("Recurso", "") if bottleneck else "",
            "ocupacion_cuello_botella_pct": bottleneck.get("Ocupación %", 0) if bottleneck else 0,
            "motivo_cuello_botella": bottleneck.get("motivo", "") if bottleneck else "",
            "personal_minimo_recursos": personnel_resources["personal_minimo_recursos"],
            "personal_optimo_recursos": personnel_resources["personal_optimo_recursos"],
            "aviso_personal_recursos": personnel_resources["aviso_tecnico"],
        })
        alerts = self.calculate_capacity_alerts(summary, fam, line, incidencias + resource_incidencias + staffing["incidencias"], resource_rows, bottleneck)
        return {"summary": summary, "family_rows": fam, "line_rows": line, "resource_rows": resource_rows, "staffing_rows": staffing["rows"], "incidencias": alerts, "pedidos": mapped}

    def map_orders_to_productive_config(self, pedidos_reales: list[dict], pedidos_previstos: list[dict], inputs: dict) -> tuple[list[dict], list[dict]]:
        mapping = {str(r.get("codigo_mconfeccion", "")).strip(): r for r in inputs["packaging_mapping"]}
        line_map = {str(r.get("codigo", "")).strip(): r for r in inputs["lines"]}
        factor_index = self._factor_map(inputs["caliber_factors"])
        base_packaging = {str(r.get("codigo", "")).strip(): r for r in inputs.get("base_packaging", [])}
        out: list[dict] = []
        incidencias: list[dict] = []

        for tipo, rows in (("Real", pedidos_reales), ("Previsto", pedidos_previstos)):
            for order in rows:
                kg = float(order.get("Kg pendiente", order.get("kg_estimados", 0)) or 0)
                if tipo == "Previsto":
                    logger.debug(
                        "CAPACIDAD PREVISTO | id=%s | codigo_base=%s | linea=%s | familia=%s | kg=%s",
                        order.get("id_previsto"),
                        order.get("codigo_base_packaging"),
                        order.get("linea_productiva"),
                        order.get("familia_productiva"),
                        order.get("kg_estimados"),
                    )
                if kg <= 0:
                    continue

                productive_conf = None
                fallback_used = False
                if tipo == "Previsto":
                    codigo_base = str(order.get("codigo_base_packaging", "")).strip()
                    if not codigo_base:
                        incidencias.append(self._inc("Previsto sin confección base", order, "Pedido previsto sin codigo_base_packaging", "Completar confección base del pedido"))
                    else:
                        productive_conf = base_packaging.get(codigo_base)
                        if not productive_conf:
                            incidencias.append(self._inc("Confección base inexistente", order, f"No existe confección base {codigo_base}", "Revisar pedido previsto o maestro"))
                            continue

                if productive_conf is None:
                    conf = str(order.get("IdConfeccion", order.get("id_confeccion", ""))).strip()
                    if conf:
                        productive_conf = mapping.get(conf)

                if not productive_conf:
                    productive_conf = self._fallback_packaging(order, inputs.get("base_packaging", []))
                    fallback_used = productive_conf is not None
                    if fallback_used:
                        incidencias.append(self._inc("Fallback confección", order, "Pedido con fallback aproximado grupo/perfil", "Revisar mapeo productivo para eliminar aproximación"))

                if not productive_conf:
                    incidencias.append(self._inc("Sin confección productiva", order, "No existe confección productiva resoluble", "Crear/revisar mapeo o confección base"))
                    continue

                familia = str(productive_conf.get("familia_productiva", "Otros") or "Otros")
                if familia == "Otro":
                    familia = "Otros"
                linea = str(productive_conf.get("linea_productiva", "")).strip()
                line_cfg = line_map.get(linea)
                if not linea or not line_cfg:
                    incidencias.append(self._inc("Línea inexistente", order, f"Línea {linea or 'VACÍA'} no configurada", "Asignar línea válida en maestro"))
                    continue

                if int(line_cfg.get("activa", 0) or 0) != 1:
                    incidencias.append(self._inc("Línea inactiva", order, f"Línea {linea} inactiva", "Activar línea o reasignar confección"))

                numero_maquinas = int(line_cfg.get("numero_maquinas", 0) or 0)
                cap_ref = float(line_cfg.get("capacidad_kg_h_referencia", 0) or 0)
                if numero_maquinas <= 0:
                    incidencias.append(self._inc("Máquinas no configuradas", order, f"Línea {linea} con numero_maquinas=0", "Configurar número de máquinas"))
                if cap_ref <= 0:
                    incidencias.append(self._inc("Sin capacidad configurada", order, f"Línea {linea} con capacidad_kg_h_referencia=0", "Configurar rendimiento base kg/h/persona"))

                main_staff = self._main_productive_staffing_for_line(linea, inputs)
                main_staff_area = str(main_staff.get("area_puesto", "") or "").strip()
                main_staff_min = max(0, int(main_staff.get("minimo", 0) or 0))
                main_staff_opt = max(main_staff_min, int(main_staff.get("optimo", 0) or 0))
                area_availability, _area_type, area_names = self._staff_availability_indexes(inputs)
                main_staff_available, main_staff_match, main_staff_found = self._available_staff_for_area(main_staff_area, area_availability, area_names)
                logger.debug(
                    "CAPACIDAD PERSONAL PRINCIPAL puesto=%s normalizado=%s area_encontrada=%s disponible=%s equivalencia=%s",
                    main_staff_area,
                    self._normalize_staff_name(main_staff_area),
                    main_staff_found or "-",
                    main_staff_available,
                    main_staff_match == "equivalence",
                )
                main_staff_real = main_staff_available
                capacity_issue = str(main_staff.get("_capacity_issue", "") or "")
                if capacity_issue:
                    incidencias.append(self._inc(capacity_issue, order, f"Línea {linea}: {capacity_issue}", "Configurar la línea en Capacidad productiva"))
                elif not main_staff_area:
                    incidencias.append(self._inc("Línea sin puesto productivo principal", order, f"Línea {linea} sin puesto productivo principal", "Configurar puesto productivo principal en Capacidad productiva"))
                elif main_staff_match == "none":
                    incidencias.append(self._inc("Puesto principal sin disponibilidad exacta", order, f"Línea {linea} / {main_staff_area} no existe en maestro Personal", "Configurar disponibilidad exacta del puesto principal en Personal"))
                elif main_staff_available <= 0:
                    incidencias.append(self._inc("Puesto principal sin disponibilidad real", order, f"Línea {linea} / {main_staff_area} con disponible={main_staff_available}", "Revisar disponibilidad real del puesto principal en Personal"))
                if main_staff_opt <= 0:
                    incidencias.append(self._inc("Puesto principal sin óptimo", order, f"Línea {linea} / {main_staff_area} con óptimo=0", "Configurar dotación óptima del puesto productivo principal"))
                if main_staff_real <= 0:
                    main_staff_real = main_staff_min
                capacidad_base_personas = cap_ref * main_staff_real if cap_ref > 0 and main_staff_real > 0 else 0.0
                if capacidad_base_personas <= 0:
                    incidencias.append(self._inc("Sin capacidad configurada", order, f"Línea {linea} sin capacidad válida por persona productiva principal real", "Completar rendimiento kg/h/persona y disponibilidad real o dotación mínima del puesto principal"))
                    continue

                tipo_malla = str(productive_conf.get("tipo_malla", "") or "").strip()
                subtipo_productivo = str(productive_conf.get("subtipo_productivo", "") or "").strip()
                if linea == "MALLAS_TRADICIONAL" and tipo_malla == "Clip-to-clip":
                    tipo_malla = "Tradicional"
                    subtipo_productivo = "Tradicional"
                    incidencias.append(self._inc("Tipo malla corregido", order, "Tipo malla corregido operativamente a Tradicional", "Actualizar Mapeo confecciones para separar nombre comercial y tipo operativo"))

                factor = self._factor_for(order, familia, factor_index)
                capacidad_real = max(0.01, capacidad_base_personas * factor)
                horas = kg / capacidad_real

                personal_min = int(line_cfg.get("personal_minimo", 0) or 0)
                if personal_min <= 0:
                    incidencias.append(self._inc("Personal mínimo no configurado", order, f"Línea {linea} con personal_minimo=0", "Configurar personal mínimo operativo"))

                out.append({
                    "tipo_pedido": tipo,
                    "pedido": order,
                    "kg": kg,
                    "familia": familia,
                    "linea": linea,
                    "rendimiento": capacidad_real,
                    "horas": horas,
                    "capacidad_kg_h": capacidad_real,
                    "rendimiento_base_kg_h_persona": cap_ref,
                    "personas_productivas_principales": main_staff_real,
                    "personas_productivas_principales_optimo": main_staff_opt,
                    "puesto_productivo_principal": main_staff_area,
                    "capacidad_real_kg_h": capacidad_real,
                    "personal_minimo_linea": max(0, personal_min),
                    "personal_optimo_linea": int(line_cfg.get("personal_optimo", 0) or 0),
                    "tipo_malla": tipo_malla,
                    "subtipo_productivo": subtipo_productivo,
                    "fallback_used": fallback_used,
                })
        return out, incidencias

    def calculate_family_capacity(self, mapped: list[dict], inputs: dict, staffing_rows: list[dict] | None = None) -> list[dict]:
        by = defaultdict(lambda: {"kg_real": 0.0, "kg_prev": 0.0, "kg_total": 0.0, "horas": 0.0, "rend_sum": 0.0, "base_sum": 0.0, "main_people_sum": 0.0, "capacity_sum": 0.0, "n": 0, "lineas": set(), "personal": 0})
        for m in mapped:
            d = by[m["familia"]]
            d["kg_total"] += m["kg"]; d["horas"] += m["horas"]; d["rend_sum"] += m["rendimiento"]; d["n"] += 1
            d["base_sum"] += float(m.get("rendimiento_base_kg_h_persona", 0) or 0)
            d["main_people_sum"] += float(m.get("personas_productivas_principales", 0) or 0)
            d["capacity_sum"] += float(m.get("capacidad_real_kg_h", m.get("capacidad_kg_h", 0)) or 0)
            d["lineas"].add(m["linea"])
            if m["tipo_pedido"] == "Real":
                d["kg_real"] += m["kg"]
            else:
                d["kg_prev"] += m["kg"]
            d["personal"] += self._estimate_personnel_for_order(m, inputs)

        staffing_by_family = self._staffing_estimate_by_family(mapped, staffing_rows or []) if staffing_rows is not None else {}
        rows = []
        families = self._productive_family_names(inputs, by.keys())
        for fam in families:
            d = by[fam]
            horas_disp = self._family_hours_available(d["lineas"], inputs)
            occ = (d["horas"] / horas_disp * 100.0) if horas_disp > 0 else 0
            order_personnel = int(d["personal"])
            staffing_personnel = int(staffing_by_family.get(fam, 0)) if staffing_rows is not None else order_personnel
            logger.info(
                "CAPACIDAD FAMILIA\nfamilia=%s\npersonal_estimado_familia=%s\npersonal_estimado_staffing=%s",
                fam,
                order_personnel,
                staffing_personnel,
            )
            rows.append({
                "Familia": fam,
                "Kg reales": round(d["kg_real"], 2),
                "Kg previstos": round(d["kg_prev"], 2),
                "Kg total": round(d["kg_total"], 2),
                "Horas necesarias": round(d["horas"], 2),
                "Horas disponibles": round(horas_disp, 2),
                "Ocupación %": round(occ, 2),
                "Rendimiento medio": round((d["rend_sum"] / d["n"]) if d["n"] else 0, 2),
                "Rendimiento base kg/h/persona": round((d["base_sum"] / d["n"]) if d["n"] else 0, 2),
                "Personas productivas principales": round((d["main_people_sum"] / d["n"]) if d["n"] else 0, 2),
                "Capacidad real kg/h": round((d["capacity_sum"] / d["n"]) if d["n"] else 0, 2),
                "Personal estimado": staffing_personnel,
                "Estado": self._state(occ, inputs["semaphore_rules"], fam),
            })
        return rows


    def _staffing_estimate_by_family(self, mapped: list[dict], staffing_rows: list[dict]) -> dict[str, int]:
        family_lines: dict[str, set[str]] = defaultdict(set)
        for row in mapped:
            family = str(row.get("familia", "") or "").strip()
            line = str(row.get("linea", "") or "").strip()
            if family and line:
                family_lines[family].add(line)

        staffing_by_line: dict[str, int] = defaultdict(int)
        for row in staffing_rows:
            line = str(row.get("Línea productiva", "") or "").strip()
            if not line:
                continue
            staffing_by_line[line] += int(row.get("Necesario estimado", 0) or 0)

        return {family: sum(staffing_by_line[line] for line in lines) for family, lines in family_lines.items()}

    def calculate_line_capacity(self, mapped: list[dict], inputs: dict) -> list[dict]:
        by = defaultdict(lambda: {"kg": 0.0, "horas": 0.0, "pedidos": 0, "formatos": set(), "personal": 0, "base_sum": 0.0, "main_people_sum": 0.0, "capacity_sum": 0.0})
        for m in mapped:
            d = by[m["linea"]]
            d["kg"] += m["kg"]; d["horas"] += m["horas"]; d["pedidos"] += 1
            d["base_sum"] += float(m.get("rendimiento_base_kg_h_persona", 0) or 0)
            d["main_people_sum"] += float(m.get("personas_productivas_principales", 0) or 0)
            d["capacity_sum"] += float(m.get("capacidad_real_kg_h", m.get("capacidad_kg_h", 0)) or 0)
            d["formatos"].add(str(m["pedido"].get("IdConfeccion", m["pedido"].get("id_confeccion", ""))))
            d["personal"] += self._estimate_personnel_for_order(m, inputs)

        rows = []
        for cod, d in by.items():
            hdisp = self._line_hours_available(self._line_cfg(cod, inputs), inputs)
            occ = d["horas"] / hdisp * 100 if hdisp > 0 else 0
            rows.append({
                "Línea productiva": cod,
                "Kg": round(d["kg"], 2),
                "Horas necesarias": round(d["horas"], 2),
                "Horas disponibles línea": round(hdisp, 2),
                "Ocupación %": round(occ, 2),
                "Rendimiento base kg/h/persona": round((d["base_sum"] / d["pedidos"]) if d["pedidos"] else 0, 2),
                "Personas productivas principales": round((d["main_people_sum"] / d["pedidos"]) if d["pedidos"] else 0, 2),
                "Capacidad real kg/h": round((d["capacity_sum"] / d["pedidos"]) if d["pedidos"] else 0, 2),
                "Pedidos": d["pedidos"],
                "Cambios formato estimados": max(0, len(d["formatos"]) - 1),
                "Personal estimado": int(d["personal"]),
                "Estado": self._state(occ, inputs["semaphore_rules"], cod),
            })
        return sorted(rows, key=lambda x: x["Ocupación %"], reverse=True)



    def calculate_staffing_requirements(self, capacity_result: dict) -> dict:
        inputs = capacity_result.get("inputs", {})
        self._current_capacity_inputs = inputs
        line_rows = capacity_result.get("line_rows", [])
        line_occ = {str(r.get("Línea productiva", "")).strip(): float(r.get("Ocupación %", 0) or 0) for r in line_rows}
        used_lines = {line for line, occ in line_occ.items() if line}
        staff_rows = [r for r in inputs.get("flow_staffing", []) if str(r.get("linea_productiva", "")).strip() in used_lines]
        area_availability, area_type, area_names = self._staff_availability_indexes(inputs)
        rows: list[dict] = []
        incidencias: list[dict] = []
        totals = {"min": 0, "opt": 0, "est": 0, "deficit": 0}

        for staff in staff_rows:
            linea = str(staff.get("linea_productiva", "")).strip()
            area = str(staff.get("area_puesto", "")).strip()
            tipo_configurado = str(staff.get("tipo_personal", "")).strip()
            tipo, _ = self._staff_type_for_area(area, tipo_configurado, area_type)
            minimo = max(0, int(staff.get("minimo", 0) or 0))
            optimo = max(minimo, int(staff.get("optimo", 0) or 0))
            ocupacion = float(line_occ.get(linea, 0) or 0)
            escala = int(staff.get("escala_con_ocupacion", 0) or 0) == 1
            obligatorio = int(staff.get("obligatorio", 1) or 0) == 1
            necesario = optimo if escala else minimo
            necesario = max(minimo, necesario)
            disponible, match_kind, matched_area = self._available_staff_for_area(area, area_availability, area_names)
            logger.debug(
                "CAPACIDAD PERSONAL REQUERIDO puesto=%s normalizado=%s area_encontrada=%s disponible=%s equivalencia=%s",
                area,
                self._normalize_staff_name(area),
                matched_area or "-",
                disponible,
                match_kind == "equivalence",
            )
            diferencia = disponible - necesario
            if disponible >= necesario:
                estado = "Verde"
                tag = "tag_green"
            elif disponible >= minimo:
                estado = "Amarillo"
                tag = "tag_yellow"
            else:
                estado = "Rojo" if obligatorio else "Amarillo"
                tag = "tag_red" if obligatorio else "tag_yellow"
            row = {
                "Línea productiva": linea,
                "Área / puesto": area,
                "Tipo personal": tipo,
                "Mínimo": minimo,
                "Óptimo": optimo,
                "Ocupación %": round(ocupacion, 2),
                "Necesario estimado": int(necesario),
                "Disponible": int(disponible),
                "Diferencia": int(diferencia),
                "Estado": estado,
                "__tags__": (tag,),
            }
            rows.append(row)
            totals["min"] += minimo; totals["opt"] += optimo; totals["est"] += int(necesario); totals["deficit"] += max(0, -int(diferencia))
            if match_kind == "none":
                incidencias.append(self._staff_inc("Área sin personal configurado", linea, area, f"No hay disponibilidad real configurada para {area}", "Configurar personal por puesto exacto o equivalencia clara en maestro Personal"))
            if disponible < minimo:
                incidencias.append(self._staff_inc("Falta personal mínimo", linea, area, f"Disponible {disponible} < mínimo {minimo}", "Reforzar dotación mínima del puesto"))
            elif disponible < optimo:
                incidencias.append(self._staff_inc("Falta personal óptimo", linea, area, f"Disponible {disponible} < óptimo {optimo}", "Revisar dotación recomendada para rendimiento normal"))
            if obligatorio and disponible < minimo:
                incidencias.append(self._staff_inc("Dotación obligatoria no cubierta", linea, area, f"Puesto obligatorio {area} no cubre mínimo {minimo}", "Cubrir puesto imprescindible antes de lanzar el flujo"))

        return {
            "rows": rows,
            "incidencias": incidencias,
            "summary": {
                "personal_minimo_requerido": totals["min"],
                "personal_optimo_requerido": totals["opt"],
                "personal_necesario_estimado": totals["est"],
                "deficit_personal": totals["deficit"],
            },
        }

    def calculate_physical_resource_capacity(self, mapped: list[dict], inputs: dict) -> tuple[list[dict], list[dict]]:
        grouped: dict[tuple[str, str], dict] = defaultdict(lambda: {"kg": 0.0, "familia": "", "tipo_malla": ""})
        for m in mapped:
            tipo_malla = str(m.get("tipo_malla", "") or "").strip()
            key = (str(m.get("linea", "") or "").strip(), tipo_malla)
            grouped[key]["kg"] += float(m.get("kg", 0) or 0)
            grouped[key]["familia"] = str(m.get("familia", "") or "").strip()
            grouped[key]["tipo_malla"] = tipo_malla

        resource_rows: list[dict] = []
        incidencias: list[dict] = []
        horas_disponibles = self._resource_hours_available(inputs)
        for (line_code, tipo_malla), data in grouped.items():
            if not line_code or data["kg"] <= 0:
                continue
            productive_mapping = {
                "kg": data["kg"],
                "familia": data["familia"],
                "tipo_malla": tipo_malla,
                "inputs": inputs,
            }
            usage_mode = self._resource_usage_mode(line_code, inputs)
            required = self.resolve_required_resources_for_line(line_code, productive_mapping)
            if usage_mode == self.RESOURCE_USAGE_INFORMATIVE and required:
                incidencias.append({
                    "Tipo incidencia": "Recursos informativos",
                    "Pedido": "-",
                    "Cliente": "-",
                    "Confección": "-",
                    "Línea productiva": line_code,
                    "Motivo": "Recursos físicos mostrados en modo informativo; capacidad tomada de Máquinas / líneas.",
                    "Acción sugerida": "Sin acción requerida mientras la línea agregada esté configurada y disponible",
                })
            resource_rows.extend(self.calculate_resource_capacity_usage(required, data["kg"], horas_disponibles, usage_mode))

        for row in resource_rows:
            for inc in row.get("_incidencias", []):
                incidencias.append({
                    "Tipo incidencia": inc["tipo"],
                    "Pedido": "-",
                    "Cliente": "-",
                    "Confección": "-",
                    "Línea productiva": row.get("Línea productiva", ""),
                    "Motivo": inc["motivo"],
                    "Acción sugerida": inc["accion"],
                })
            row.pop("_incidencias", None)
        return sorted(resource_rows, key=lambda x: (x["Línea productiva"], x["Recurso"])), incidencias

    def resolve_required_resources_for_line(self, line_code: str, productive_mapping: dict) -> list[dict]:
        inputs = productive_mapping.get("inputs", {})
        kg = float(productive_mapping.get("kg", 0) or 0)
        tipo_malla = str(productive_mapping.get("tipo_malla", "") or "").strip()
        resource_index = {str(r.get("codigo", "") or "").strip(): r for r in inputs.get("physical_resources", [])}
        line = str(line_code or "").strip()
        configured_rows = [
            row for row in inputs.get("line_required_resources", [])
            if str(row.get("linea_productiva", "") or "").strip() == line
            and int(row.get("activo", 1) or 0) == 1
        ]
        configured_rows.sort(key=lambda r: (int(r.get("orden", 0) or 0), str(r.get("recurso_codigo", "") or "")))
        if not configured_rows:
            return [{
                "codigo": line,
                "tipo_recurso": "No configurado",
                "familia_operativa": "",
                "capacidad_kg_h": 0,
                "numero_unidades": 0,
                "personal_minimo": 0,
                "personal_optimo": 0,
                "activo": 0,
                "linea_productiva": line,
                "kg_asignados": 0.0,
                "_incidencias": [{"tipo": "Línea sin recursos requeridos configurados", "motivo": f"Línea {line or 'VACÍA'} sin recursos requeridos activos en production_line_required_resources", "accion": "Configurar recursos requeridos por línea en Capacidad productiva"}],
                "_solo_incidencia": True,
            }]

        split_codes = []
        fixed_codes = []
        rows_by_code: dict[str, dict] = {}
        compatibility_rules_found = False
        for cfg in configured_rows:
            code = str(cfg.get("recurso_codigo", "") or "").strip()
            if not code:
                continue
            row = dict(resource_index.get(code, {}))
            incidencias = []
            if not row:
                row = {"codigo": code, "tipo_recurso": "No configurado", "familia_operativa": "", "capacidad_kg_h": 0, "numero_unidades": 0, "personal_minimo": 0, "personal_optimo": 0, "activo": 0}
                incidencias.append({"tipo": "Recurso físico no configurado", "motivo": f"Recurso {code} no existe en production_physical_resources", "accion": "Configurar recurso físico o ajustar Recursos requeridos por línea"})
            elif int(row.get("activo", 0) or 0) != 1:
                incidencias.append({"tipo": "Recurso inactivo", "motivo": f"Recurso {code} inactivo", "accion": "Activar recurso o reasignar carga"})

            include = True
            if str(row.get("tipo_recurso", "")).strip().lower() == "pesadora" or code.startswith("PESADORA_"):
                if self._resource_has_compatibility_rule(code, "tipo_malla", tipo_malla, inputs):
                    compatibility_rules_found = True
                if self._is_resource_compatible(code, "tipo_malla", tipo_malla, inputs):
                    pass
                else:
                    incidencias.append({"tipo": "Recurso no compatible", "motivo": f"{code} no compatible con tipo_malla={tipo_malla or 'VACÍO'}", "accion": "Revisar compatibilidades de recursos"})
                    include = False

            availability_issue = self._resource_availability_issue(code, inputs)
            if availability_issue:
                incidencias.append(availability_issue)
            if int(cfg.get("reparte_kg", 0) or 0) == 1:
                split_codes.append(code)
            else:
                fixed_codes.append(code)
            rows_by_code[code] = {"row": row, "incidencias": incidencias, "include": include, "config": cfg}

        if tipo_malla and split_codes and not any(rows_by_code[c].get("include") for c in split_codes) and not compatibility_rules_found:
            fallback_code = f"{line}:tipo_malla"
            fallback_row = {"codigo": fallback_code, "tipo_recurso": "Compatibilidad", "familia_operativa": "", "capacidad_kg_h": 0, "numero_unidades": 0, "personal_minimo": 0, "personal_optimo": 0, "activo": 0}
            rows_by_code[fallback_code] = {"row": fallback_row, "incidencias": [{"tipo": "Tipo malla sin compatibilidad", "motivo": f"tipo_malla={tipo_malla} no tiene ninguna compatibilidad definida", "accion": "Definir compatibilidades en Recursos y flujos"}], "include": False, "config": {}}

        out: list[dict] = []
        active_split = [code for code in split_codes if rows_by_code.get(code, {}).get("include") and int(rows_by_code[code]["row"].get("activo", 0) or 0) == 1]
        split_kg = kg / len(active_split) if active_split else 0.0
        for code in fixed_codes + split_codes:
            payload = rows_by_code.get(code)
            if not payload or not payload.get("include"):
                continue
            row = dict(payload["row"])
            assigned_kg = split_kg if code in split_codes else kg
            out.append({**row, "linea_productiva": line, "kg_asignados": assigned_kg, "_incidencias": list(payload["incidencias"])})
        for code, payload in rows_by_code.items():
            if payload.get("include"):
                continue
            for inc in payload.get("incidencias", []):
                out.append({**payload["row"], "linea_productiva": line, "kg_asignados": 0.0, "_incidencias": [inc], "_solo_incidencia": True})
        return out

    def calculate_resource_capacity_usage(self, resource_rows: list[dict], kg: float, horas_utiles_dia: float, usage_mode: str | None = None) -> list[dict]:
        out: list[dict] = []
        mode = self._normalize_resource_usage_mode(usage_mode)
        mode_label = "Informativo" if mode == self.RESOURCE_USAGE_INFORMATIVE else "Restrictivo"
        for resource in resource_rows:
            capacidad_kg_h = float(resource.get("capacidad_kg_h", 0) or 0)
            numero_unidades = int(resource.get("numero_unidades", 0) or 0)
            capacidad_total = capacidad_kg_h * numero_unidades if numero_unidades > 0 else 0.0
            assigned_kg = float(resource.get("kg_asignados", kg) or 0)
            incidencias = list(resource.get("_incidencias", []))
            if mode == self.RESOURCE_USAGE_RESTRICTIVE and capacidad_kg_h <= 0 and not resource.get("_solo_incidencia"):
                incidencias.append({"tipo": "Recurso sin capacidad", "motivo": f"Recurso {resource.get('codigo', '')} sin capacidad kg/h configurada", "accion": "Configurar capacidad_kg_h del recurso"})
            if mode == self.RESOURCE_USAGE_INFORMATIVE:
                horas = 0.0
                ocupacion = 0.0
                state_incidencias = [inc for inc in incidencias if inc.get("tipo") not in {"Recurso no compatible"}]
                estado = "Incidencia" if state_incidencias else "Informativo"
            else:
                horas = assigned_kg / capacidad_total if capacidad_total > 0 else 0.0
                ocupacion = horas / horas_utiles_dia * 100 if horas_utiles_dia > 0 else 0.0
                estado = "Incidencia" if incidencias else ("Rojo" if ocupacion >= 100 else "Amarillo" if ocupacion >= 85 else "Verde")
            out.append({
                "Recurso": resource.get("codigo", ""),
                "Tipo recurso": resource.get("tipo_recurso", ""),
                "Línea productiva": resource.get("linea_productiva", ""),
                "Modo uso": mode_label,
                "Kg asignados": round(assigned_kg, 2),
                "Capacidad kg/h": round(capacidad_total, 2),
                "Horas necesarias": round(horas, 2),
                "Horas disponibles": round(horas_utiles_dia, 2),
                "Ocupación %": round(ocupacion, 2),
                "Personal mínimo": int(resource.get("personal_minimo", 0) or 0),
                "Personal óptimo": int(resource.get("personal_optimo", 0) or 0),
                "Estado": estado,
                "_incidencias": incidencias,
            })
        return out

    def detect_bottleneck(self, resource_usage_rows: list[dict]) -> dict | None:
        candidates = [r for r in resource_usage_rows if str(r.get("Modo uso", "")).strip().lower() == "restrictivo" and float(r.get("Kg asignados", 0) or 0) > 0]
        if not candidates:
            return None
        bottleneck = max(candidates, key=lambda r: float(r.get("Ocupación %", 0) or 0))
        row = dict(bottleneck)
        row["motivo"] = f"{row.get('Recurso', '')} al {float(row.get('Ocupación %', 0) or 0):.2f}%"
        return row

    def calculate_resource_personnel(self, resource_usage_rows: list[dict]) -> dict:
        return {
            "personal_minimo_recursos": sum(int(r.get("Personal mínimo", 0) or 0) for r in resource_usage_rows if str(r.get("Modo uso", "")).strip().lower() == "restrictivo" and float(r.get("Kg asignados", 0) or 0) > 0),
            "personal_optimo_recursos": sum(int(r.get("Personal óptimo", 0) or 0) for r in resource_usage_rows if str(r.get("Modo uso", "")).strip().lower() == "restrictivo" and float(r.get("Kg asignados", 0) or 0) > 0),
            "aviso_tecnico": "Suma simple solo sobre recursos restrictivos; recursos informativos no penalizan la capacidad agregada de línea.",
        }

    def calculate_capacity_summary(self, mapped: list[dict], family_rows: list[dict], line_rows: list[dict], inputs: dict) -> dict:
        kg_real = sum(m["kg"] for m in mapped if m["tipo_pedido"] == "Real")
        kg_prev = sum(m["kg"] for m in mapped if m["tipo_pedido"] == "Previsto")
        horas = sum(m["horas"] for m in mapped)
        hdisp = sum(float(r.get("Horas disponibles línea", 0) or 0) for r in line_rows)
        occ = horas / hdisp * 100 if hdisp > 0 else 0
        turnos_equivalentes = horas / hdisp if hdisp > 0 else 0
        per = inputs["personnel"]
        return {"Kg reales pendientes": round(kg_real, 2), "Kg previstos": round(kg_prev, 2), "Kg total simulación": round(kg_real + kg_prev, 2), "Horas necesarias estimadas": round(horas, 2), "Horas disponibles": round(hdisp, 2), "Ocupación %": round(occ, 2), "jornadas_equivalentes": round(turnos_equivalentes, 2), "turnos_equivalentes": round(turnos_equivalentes, 2), "Personal disponible total": int(per.get("personal_total", 0) or 0), "Personal directo disponible": int(per.get("personal_directo", 0) or 0), "Personal soporte disponible": int(per.get("personal_soporte", 0) or 0), "Personal indirecto disponible": int(per.get("personal_indirecto", 0) or 0), "Estado capacidad": self._state(occ, inputs["semaphore_rules"], "General")}

    def calculate_capacity_alerts(self, summary: dict, family_rows: list[dict], line_rows: list[dict], incidencias: list[dict], resource_rows: list[dict] | None = None, bottleneck: dict | None = None) -> list[dict]:
        out = list(incidencias)
        for row in family_rows:
            if row["Ocupación %"] >= 100:
                out.append({"Tipo incidencia": "Capacidad excedida", "Pedido": "-", "Cliente": "-", "Confección": "-", "Línea productiva": row["Familia"], "Motivo": f"Ocupación {row['Ocupación %']}%", "Acción sugerida": "Reducir carga o ampliar capacidad"})
        for row in line_rows:
            if row["Ocupación %"] >= 100:
                out.append({"Tipo incidencia": "Línea saturada", "Pedido": "-", "Cliente": "-", "Confección": "-", "Línea productiva": row["Línea productiva"], "Motivo": f"Ocupación {row['Ocupación %']}%", "Acción sugerida": "Mover carga entre líneas"})
        if bottleneck:
            occ = float(bottleneck.get("Ocupación %", 0) or 0)
            if occ >= 100:
                out.append({"Tipo incidencia": "Cuello de botella > 100%", "Pedido": "-", "Cliente": "-", "Confección": "-", "Línea productiva": bottleneck.get("Línea productiva", ""), "Motivo": bottleneck.get("motivo", f"Ocupación {occ:.2f}%"), "Acción sugerida": "Reducir kg asignados o ampliar capacidad del recurso"})
            elif occ >= 85:
                out.append({"Tipo incidencia": "Cuello de botella > 85%", "Pedido": "-", "Cliente": "-", "Confección": "-", "Línea productiva": bottleneck.get("Línea productiva", ""), "Motivo": bottleneck.get("motivo", f"Ocupación {occ:.2f}%"), "Acción sugerida": "Vigilar recurso y preparar alternativa"})
        personal_min = int(summary.get("personal_minimo_recursos", 0) or 0)
        personal_directo = int(summary.get("Personal directo disponible", 0) or 0)
        if personal_min > personal_directo:
            out.append({"Tipo incidencia": "Falta personal mínimo por recursos", "Pedido": "-", "Cliente": "-", "Confección": "-", "Línea productiva": "Recursos", "Motivo": f"Personal mínimo recursos {personal_min} > personal directo disponible {personal_directo}", "Acción sugerida": "Revisar turnos, ausencias o asignación de recursos"})
        return out




    def _main_productive_staffing_for_line(self, line_code: str, inputs: dict) -> dict:
        line = str(line_code or "").strip()
        if not line:
            return {}
        capacity_cfg = self._line_capacity_cfg(line, inputs)
        expected_area = str(capacity_cfg.get("puesto_productivo_principal", "") or "").strip() if capacity_cfg else ""
        if not capacity_cfg:
            return {"_capacity_issue": "Línea sin configuración de capacidad"}
        if not expected_area:
            return {"_capacity_issue": "Línea sin puesto productivo principal"}
        expected_norm = self._normalize_staff_name(expected_area)
        for row in inputs.get("flow_staffing", []):
            if str(row.get("linea_productiva", "") or "").strip() != line:
                continue
            if int(row.get("activo", 1) or 0) != 1:
                continue
            if self._normalize_staff_name(str(row.get("area_puesto", "") or "")) == expected_norm:
                return row
        return {"area_puesto": expected_area, "minimo": 0, "optimo": 0, "_capacity_issue": "Puesto principal no existe en dotación flujos"}

    def _staff_availability_indexes(self, inputs: dict) -> tuple[dict[str, int], dict[str, str], dict[str, str]]:
        area_availability: dict[str, int] = {}
        area_type: dict[str, str] = {}
        area_names: dict[str, str] = {}
        for row in inputs.get("staff_areas", []):
            if int(row.get("activo", 1) or 0) != 1:
                continue
            available = int(row.get("disponible", 0) or 0)
            raw_area = str(row.get("area", ""))
            norm_area = self._normalize_staff_name(raw_area)
            tipo_personal = str(row.get("tipo_personal", "")).strip()
            if norm_area:
                # Si existen filas duplicadas del mismo puesto normalizado, conservar la
                # mayor disponibilidad para no duplicar personas por variantes de nombre.
                area_availability[norm_area] = max(area_availability.get(norm_area, 0), available)
                area_names.setdefault(norm_area, raw_area.strip() or norm_area)
                if tipo_personal:
                    area_type[norm_area] = tipo_personal
        return area_availability, area_type, area_names

    def _staff_type_for_area(self, area: str, configured_type: str, area_type: dict[str, str]) -> tuple[str, str]:
        area_norm = self._normalize_staff_name(area)
        if area_norm in area_type:
            return area_type[area_norm], "area"
        for equivalent_norm in self._staff_equivalent_names(area_norm, getattr(self, "_current_capacity_inputs", None)):
            if equivalent_norm != area_norm and equivalent_norm in area_type:
                return area_type[equivalent_norm], "equivalence"
        # tipo_personal clasifica/resume el puesto requerido, pero no asigna
        # disponibilidad si no existe área real en el maestro Personal.
        return configured_type, "flow_staffing"

    def _available_staff_for_area(self, area: str, area_availability: dict[str, int], area_names: dict[str, str] | None = None) -> tuple[int, str, str]:
        area_names = area_names or {}
        area_norm = self._normalize_staff_name(area)
        if area_norm in area_availability:
            return area_availability[area_norm], "area", area_names.get(area_norm, area_norm)
        equivalent_matches = [
            norm for norm in self._staff_equivalent_names(area_norm, getattr(self, "_current_capacity_inputs", None))
            if norm != area_norm and norm in area_availability
        ]
        if equivalent_matches:
            available = sum(area_availability[norm] for norm in equivalent_matches)
            matched = " + ".join(area_names.get(norm, norm) for norm in equivalent_matches)
            return available, "equivalence", matched
        return 0, "none", ""

    def _staff_equivalent_names(self, area_norm: str, inputs: dict | None = None) -> tuple[str, ...]:
        if not area_norm:
            return ()
        if inputs is None:
            return (area_norm,)
        equivalents = [area_norm]
        for row in inputs.get("staff_area_equivalences", []):
            if int(row.get("activa", 1) or 0) != 1:
                continue
            required_norm = self._normalize_staff_name(str(row.get("area_requerida", "") or ""))
            if required_norm != area_norm:
                continue
            personal_norm = self._normalize_staff_name(str(row.get("area_personal", "") or ""))
            if personal_norm and personal_norm not in equivalents:
                equivalents.append(personal_norm)
        return tuple(equivalents)

    def _normalize_staff_name(self, value: str) -> str:
        text = unicodedata.normalize("NFKD", str(value or ""))
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.lower().replace("/", " ")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        tokens = text.split()
        deduped_tokens = list(dict.fromkeys(tokens))
        return " ".join(deduped_tokens).strip()

    def _staff_inc(self, tipo: str, linea: str, area: str, motivo: str, accion: str) -> dict:
        return {"Tipo incidencia": tipo, "Pedido": "-", "Cliente": "-", "Confección": area, "Línea productiva": linea, "Motivo": motivo, "Acción sugerida": accion}

    def _resource_hours_available(self, inputs: dict) -> float:
        gs = inputs["general_settings"]
        horas_utiles_dia = self._usable_hours_day(inputs)
        turnos = int(gs.get("numero_turnos", 1) or 1)
        return max(0.0, horas_utiles_dia * max(1, turnos))

    def _resource_has_compatibility_rule(self, recurso_codigo: str, compatible_con: str, valor: str, inputs: dict) -> bool:
        if not valor:
            return False
        for row in inputs.get("resource_compatibilities", []):
            if str(row.get("recurso_codigo", "") or "").strip() != recurso_codigo:
                continue
            if str(row.get("compatible_con", "") or "").strip() != compatible_con:
                continue
            if str(row.get("valor", "") or "").strip().lower() == str(valor).strip().lower():
                return True
        return False

    def _is_resource_compatible(self, recurso_codigo: str, compatible_con: str, valor: str, inputs: dict) -> bool:
        if not valor:
            return False
        for row in inputs.get("resource_compatibilities", []):
            if str(row.get("recurso_codigo", "") or "").strip() != recurso_codigo:
                continue
            if str(row.get("compatible_con", "") or "").strip() != compatible_con:
                continue
            if str(row.get("valor", "") or "").strip().lower() != str(valor).strip().lower():
                continue
            return int(row.get("activo", 0) or 0) == 1
        return False

    def _resource_availability_issue(self, recurso_codigo: str, inputs: dict) -> dict | None:
        context_values = set()
        filters = inputs.get("filters", {})
        for key in ("cultivo", "grupo_varietal", "var_coop", "campana"):
            value = filters.get(key, []) if isinstance(filters, dict) else []
            values = value if isinstance(value, list) else [value]
            context_values.update(str(v).strip().upper() for v in values if str(v).strip())
        if not context_values:
            return None
        for row in inputs.get("resource_availability", []):
            if str(row.get("recurso_codigo", "") or "").strip() != recurso_codigo:
                continue
            contexto = str(row.get("contexto", "") or "").strip().upper()
            if contexto in context_values and int(row.get("disponible", 1) or 0) != 1:
                motivo = str(row.get("motivo", "") or "").strip() or f"No disponible en contexto {contexto}"
                return {"tipo": "Recurso no disponible por contexto", "motivo": f"{recurso_codigo}: {motivo}", "accion": "Revisar disponibilidad del recurso o el contexto de planificación"}
        return None


    def _productive_family_names(self, inputs: dict, observed: object) -> list[str]:
        families = [str(r.get("codigo", "") or "").strip() for r in inputs.get("productive_families", []) if int(r.get("activa", 1) or 0) == 1 and str(r.get("codigo", "") or "").strip()]
        for fam in observed:
            if fam and fam not in families:
                families.append(str(fam))
        return families

    def _line_capacity_cfg(self, line_code: str, inputs: dict) -> dict:
        target = str(line_code or "").strip()
        for row in inputs.get("line_capacity_config", []):
            if str(row.get("linea_productiva", "") or "").strip() == target and int(row.get("activa", 1) or 0) == 1:
                return row
        return {}

    def _normalize_resource_usage_mode(self, mode: str | None) -> str:
        value = str(mode or "").strip().lower()
        if value in {self.RESOURCE_USAGE_INFORMATIVE, "informativo"}:
            return self.RESOURCE_USAGE_INFORMATIVE
        if value in {self.RESOURCE_USAGE_RESTRICTIVE, "restrictivo"}:
            return self.RESOURCE_USAGE_RESTRICTIVE
        return self.RESOURCE_USAGE_RESTRICTIVE

    def _resource_usage_mode(self, line_code: str, inputs: dict) -> str:
        cfg = self._line_capacity_cfg(line_code, inputs)
        configured = cfg.get("modo_uso_recursos", "") if cfg else ""
        if str(configured or "").strip():
            return self._normalize_resource_usage_mode(str(configured))
        return self.RESOURCE_USAGE_RESTRICTIVE

    def _line_has_valid_aggregate_capacity(self, cfg: dict) -> bool:
        if not cfg or int(cfg.get("activa", 0) or 0) != 1:
            return False
        numero_maquinas = int(cfg.get("numero_maquinas", 0) or 0)
        cap_ref = float(cfg.get("capacidad_kg_h_referencia", 0) or 0)
        return numero_maquinas > 0 and cap_ref > 0

    def _load_forecast_orders(self, filters: dict) -> list[dict]:
        campana_actual = self._single_forecast_context_value(filters, "campana")
        cultivo_actual = self._single_forecast_context_value(filters, "cultivo")
        empresa_actual = self._single_forecast_context_value(filters, "empresa")
        logger.debug(
            "CAPACIDAD PREVISTOS CONTEXTO | campaña=%r | cultivo=%r | empresa=%r",
            campana_actual,
            cultivo_actual,
            empresa_actual,
        )
        return cargar_pedidos_previstos_filtrados(
            filters,
            respetar_incluir=True,
            cultivo_actual=cultivo_actual,
            campana_actual=campana_actual,
            empresa_actual=empresa_actual,
        )

    @staticmethod
    def _single_forecast_context_value(filters: dict | None, key: str) -> str:
        if not isinstance(filters, dict):
            return ""
        raw = filters.get(key, [])
        values = raw if isinstance(raw, (list, tuple, set)) else [raw]
        selected = []
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                selected.append(text)
        if len(selected) != 1:
            return ""
        value = selected[0]
        if value.upper() == "TODOS":
            return ""
        return value

    def _line_cfg(self, code: str, inputs: dict) -> dict:
        return next((r for r in inputs["lines"] if str(r.get("codigo", "")).strip() == code), {})

    def _usable_hours_day(self, inputs: dict) -> float:
        gs = inputs["general_settings"]
        return float(gs.get("horas_utiles_dia", gs.get("horas_turno", 7.5)) or 7.5)

    def _line_hours_available(self, cfg: dict, inputs: dict) -> float:
        if not cfg or int(cfg.get("activa", 0) or 0) != 1:
            return 0.0
        num_maquinas = int(cfg.get("numero_maquinas", 0) or 0)
        if num_maquinas <= 0:
            return 0.0
        gs = inputs["general_settings"]
        horas_utiles_dia = self._usable_hours_day(inputs)
        turnos = int(gs.get("numero_turnos", 1) or 1)
        return max(0.0, horas_utiles_dia * num_maquinas * max(1, turnos))

    def _family_hours_available(self, line_codes: set[str], inputs: dict) -> float:
        return sum(self._line_hours_available(self._line_cfg(code, inputs), inputs) for code in line_codes)

    def _factor_map(self, rows: list[dict]) -> list[dict]:
        return [r for r in rows if int(r.get("activo", 1) or 0) == 1]

    def _factor_for(self, order: dict, familia: str, factors: list[dict]) -> float:
        calibre = str(order.get("Calibre", order.get("calibre", ""))).strip()
        for r in factors:
            if familia.lower() not in str(r.get("confeccion_familia", "")).lower():
                continue
            calibres = {c.strip() for c in str(r.get("calibres_incluidos", "")).split(",") if c.strip()}
            if calibre in calibres:
                return max(0.1, float(r.get("factor_rendimiento", 1) or 1))
        return 1.0

    def _estimate_personnel_for_order(self, mapped_order: dict, inputs: dict) -> int:
        cfg = self._line_cfg(mapped_order["linea"], inputs)
        horas = float(mapped_order.get("horas", 0) or 0)
        horas_utiles_dia = max(0.1, self._usable_hours_day(inputs))
        personal_min = int(cfg.get("personal_minimo", 0) or 0)
        personal_opt = int(cfg.get("personal_optimo", 0) or 0)
        if personal_opt <= 0:
            return max(0, personal_min)
        estimado = ceil(horas * personal_opt / horas_utiles_dia)
        return max(max(0, personal_min), int(estimado))

    def _fallback_packaging(self, order: dict, base_rows: list[dict]) -> dict | None:
        grp = str(order.get("grupo_confeccion", "")).strip().lower()
        profile = str(order.get("perfil_confeccion", "")).strip().lower()
        for r in base_rows:
            if int(r.get("activo", 1) or 0) != 1:
                continue
            rg = str(r.get("grupo_confeccion", "")).strip().lower()
            rp = str(r.get("perfil_confeccion", "")).strip().lower()
            if grp and profile and grp == rg and profile == rp:
                return r
        for r in base_rows:
            if int(r.get("activo", 1) or 0) != 1:
                continue
            rg = str(r.get("grupo_confeccion", "")).strip().lower()
            if grp and grp == rg:
                return r
        return None

    def _state(self, occ: float, rules: list[dict], ambito: str) -> str:
        yellow, red = 85.0, 100.0
        for r in rules:
            if str(r.get("metrica", "")) == "ocupacion_pct" and str(r.get("ambito", "")).lower() in {"general", ambito.lower()}:
                yellow = float(r.get("umbral_amarillo", yellow) or yellow)
                red = float(r.get("umbral_rojo", red) or red)
                break
        return "Rojo" if occ >= red else "Amarillo" if occ >= yellow else "Verde"

    def _inc(self, tipo: str, order: dict, motivo: str, accion: str) -> dict:
        return {"Tipo incidencia": tipo, "Pedido": order.get("IdPedidoLora", order.get("id_previsto", "")), "Cliente": order.get("Cliente", order.get("cliente", "")), "Confección": order.get("IdConfeccion", order.get("grupo_confeccion", "")), "Línea productiva": "", "Motivo": motivo, "Acción sugerida": accion}
