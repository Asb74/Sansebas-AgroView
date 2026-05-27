from __future__ import annotations

from collections import defaultdict
from math import ceil
from pathlib import Path
import json

from db.production_settings_repository import ProductionSettingsRepository
from services.planning_service import PlanningService


class ProductionCapacityService:
    PEDIDOS_PREVISTOS_PATH = Path("runtime_config/pedidos_previstos.json")
    FAMILIES = ["Malla", "Encajado", "Granel", "Granelera", "Otros"]

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
            "lines": self.prod_repo.get_lines(),
            "semaphore_rules": self.prod_repo.get_semaphore_rules(),
            "general_settings": self.prod_repo.get_general_settings(),
        }

    def build_capacity_simulation(self, filters: dict, modo_pedidos: str = "10_dias") -> dict:
        inputs = self.load_capacity_inputs(filters, modo_pedidos)
        mapped, incidencias = self.map_orders_to_productive_config(inputs["pedidos_reales"], inputs["pedidos_previstos"], inputs)
        fam = self.calculate_family_capacity(mapped, inputs)
        line = self.calculate_line_capacity(mapped, inputs)
        summary = self.calculate_capacity_summary(mapped, fam, line, inputs)
        alerts = self.calculate_capacity_alerts(summary, fam, line, incidencias)
        return {"summary": summary, "family_rows": fam, "line_rows": line, "incidencias": alerts, "pedidos": mapped}

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
                    incidencias.append(self._inc("Sin capacidad configurada", order, f"Línea {linea} con capacidad_kg_h_referencia=0", "Configurar capacidad kg/h"))

                capacidad_total = numero_maquinas * cap_ref if numero_maquinas > 0 and cap_ref > 0 else 0.0
                if capacidad_total <= 0:
                    incidencias.append(self._inc("Sin capacidad configurada", order, f"Línea {linea} sin capacidad productiva válida", "Completar maestro de líneas"))
                    continue

                factor = self._factor_for(order, familia, factor_index)
                capacidad_real = max(0.01, capacidad_total * factor)
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
                    "personal_minimo_linea": max(0, personal_min),
                    "personal_optimo_linea": int(line_cfg.get("personal_optimo", 0) or 0),
                    "fallback_used": fallback_used,
                })
        return out, incidencias

    def calculate_family_capacity(self, mapped: list[dict], inputs: dict) -> list[dict]:
        by = defaultdict(lambda: {"kg_real": 0.0, "kg_prev": 0.0, "kg_total": 0.0, "horas": 0.0, "rend_sum": 0.0, "n": 0, "lineas": set(), "personal": 0})
        for m in mapped:
            d = by[m["familia"]]
            d["kg_total"] += m["kg"]; d["horas"] += m["horas"]; d["rend_sum"] += m["rendimiento"]; d["n"] += 1
            d["lineas"].add(m["linea"])
            if m["tipo_pedido"] == "Real":
                d["kg_real"] += m["kg"]
            else:
                d["kg_prev"] += m["kg"]
            d["personal"] += self._estimate_personnel_for_order(m, inputs)

        rows = []
        for fam in self.FAMILIES:
            d = by[fam]
            horas_disp = self._family_hours_available(d["lineas"], inputs)
            occ = (d["horas"] / horas_disp * 100.0) if horas_disp > 0 else 0
            rows.append({
                "Familia": fam,
                "Kg reales": round(d["kg_real"], 2),
                "Kg previstos": round(d["kg_prev"], 2),
                "Kg total": round(d["kg_total"], 2),
                "Horas necesarias": round(d["horas"], 2),
                "Horas disponibles": round(horas_disp, 2),
                "Ocupación %": round(occ, 2),
                "Rendimiento medio": round((d["rend_sum"] / d["n"]) if d["n"] else 0, 2),
                "Personal estimado": int(d["personal"]),
                "Estado": self._state(occ, inputs["semaphore_rules"], fam),
            })
        return rows

    def calculate_line_capacity(self, mapped: list[dict], inputs: dict) -> list[dict]:
        by = defaultdict(lambda: {"kg": 0.0, "horas": 0.0, "pedidos": 0, "formatos": set(), "personal": 0})
        for m in mapped:
            d = by[m["linea"]]
            d["kg"] += m["kg"]; d["horas"] += m["horas"]; d["pedidos"] += 1
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
                "Pedidos": d["pedidos"],
                "Cambios formato estimados": max(0, len(d["formatos"]) - 1),
                "Personal estimado": int(d["personal"]),
                "Estado": self._state(occ, inputs["semaphore_rules"], cod),
            })
        return sorted(rows, key=lambda x: x["Ocupación %"], reverse=True)

    def calculate_capacity_summary(self, mapped: list[dict], family_rows: list[dict], line_rows: list[dict], inputs: dict) -> dict:
        kg_real = sum(m["kg"] for m in mapped if m["tipo_pedido"] == "Real")
        kg_prev = sum(m["kg"] for m in mapped if m["tipo_pedido"] == "Previsto")
        horas = sum(m["horas"] for m in mapped)
        hdisp = sum(float(r.get("Horas disponibles línea", 0) or 0) for r in line_rows)
        occ = horas / hdisp * 100 if hdisp > 0 else 0
        per = inputs["personnel"]
        return {"Kg reales pendientes": round(kg_real, 2), "Kg previstos": round(kg_prev, 2), "Kg total simulación": round(kg_real + kg_prev, 2), "Horas necesarias estimadas": round(horas, 2), "Horas disponibles": round(hdisp, 2), "Ocupación %": round(occ, 2), "Personal disponible total": int(per.get("personal_total", 0) or 0), "Personal directo disponible": int(per.get("personal_directo", 0) or 0), "Personal indirecto disponible": int(per.get("personal_indirecto", 0) or 0), "Estado capacidad": self._state(occ, inputs["semaphore_rules"], "General")}

    def calculate_capacity_alerts(self, summary: dict, family_rows: list[dict], line_rows: list[dict], incidencias: list[dict]) -> list[dict]:
        out = list(incidencias)
        for row in family_rows:
            if row["Ocupación %"] >= 100:
                out.append({"Tipo incidencia": "Capacidad excedida", "Pedido": "-", "Cliente": "-", "Confección": "-", "Línea productiva": row["Familia"], "Motivo": f"Ocupación {row['Ocupación %']}%", "Acción sugerida": "Reducir carga o ampliar capacidad"})
        for row in line_rows:
            if row["Ocupación %"] >= 100:
                out.append({"Tipo incidencia": "Línea saturada", "Pedido": "-", "Cliente": "-", "Confección": "-", "Línea productiva": row["Línea productiva"], "Motivo": f"Ocupación {row['Ocupación %']}%", "Acción sugerida": "Mover carga entre líneas"})
        return out

    def _load_forecast_orders(self, filters: dict) -> list[dict]:
        if not self.PEDIDOS_PREVISTOS_PATH.exists():
            return []
        payload = json.loads(self.PEDIDOS_PREVISTOS_PATH.read_text(encoding="utf-8"))
        if not payload.get("incluir_en_simulacion", True):
            return []
        return [r for r in payload.get("pedidos", []) if str(r.get("estado", "")).upper() != "DESCARTADO"]

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
