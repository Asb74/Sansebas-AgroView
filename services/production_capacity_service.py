from __future__ import annotations

from collections import defaultdict
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
        summary = self.calculate_capacity_summary(mapped, fam, inputs)
        alerts = self.calculate_capacity_alerts(summary, fam, line, incidencias)
        return {"summary": summary, "family_rows": fam, "line_rows": line, "incidencias": alerts, "pedidos": mapped}

    def map_orders_to_productive_config(self, pedidos_reales: list[dict], pedidos_previstos: list[dict], inputs: dict) -> tuple[list[dict], list[dict]]:
        mapping = {str(r.get("codigo_mconfeccion", "")).strip(): r for r in inputs["packaging_mapping"]}
        line_map = {str(r.get("codigo", "")).strip(): r for r in inputs["lines"]}
        perf = self._perf_map(inputs["performance_rules"])
        factor_index = self._factor_map(inputs["caliber_factors"])
        out: list[dict] = []
        incidencias: list[dict] = []
        for tipo, rows in (("Real", pedidos_reales), ("Previsto", pedidos_previstos)):
            for order in rows:
                kg = float(order.get("Kg pendiente", order.get("kg_estimados", 0)) or 0)
                if kg <= 0:
                    continue
                conf = str(order.get("IdConfeccion", order.get("id_confeccion", ""))).strip()
                m = mapping.get(conf)
                if not m:
                    incidencias.append(self._inc("Sin mapeo productivo", order, "No existe production_packaging_mapping", "Crear/revisar mapeo"))
                    continue
                familia = str(m.get("familia_productiva", "Otros") or "Otros")
                if familia == "Otro":
                    familia = "Otros"
                linea = str(m.get("linea_productiva", "")).strip()
                if linea not in line_map:
                    incidencias.append(self._inc("Línea inexistente", order, f"Línea {linea} no configurada", "Asignar línea válida"))
                perf_base = perf.get((familia, line_map.get(linea, {}).get("tipo_linea", familia)), 0.0)
                if perf_base <= 0:
                    incidencias.append(self._inc("Sin rendimiento", order, f"Sin rendimiento familia={familia}", "Configurar production_performance_rules"))
                    perf_base = 1.0
                factor = self._factor_for(order, familia, factor_index)
                rendimiento = max(0.01, perf_base * factor)
                out.append({"tipo_pedido": tipo, "pedido": order, "kg": kg, "familia": familia, "linea": linea or "SIN_LINEA", "rendimiento": rendimiento, "horas": kg / rendimiento})
        return out, incidencias

    def calculate_family_capacity(self, mapped: list[dict], inputs: dict) -> list[dict]:
        by = defaultdict(lambda: {"kg_real": 0.0, "kg_prev": 0.0, "kg_total": 0.0, "horas": 0.0, "rend_sum": 0.0, "n": 0})
        for m in mapped:
            d = by[m["familia"]]
            d["kg_total"] += m["kg"]; d["horas"] += m["horas"]; d["rend_sum"] += m["rendimiento"]; d["n"] += 1
            if m["tipo_pedido"] == "Real": d["kg_real"] += m["kg"]
            else: d["kg_prev"] += m["kg"]
        horas_disp = self._hours_available(inputs)
        rows = []
        for fam in self.FAMILIES:
            d = by[fam]
            occ = (d["horas"] / horas_disp * 100.0) if horas_disp > 0 else 0
            rows.append({"Familia": fam, "Kg reales": round(d["kg_real"], 2), "Kg previstos": round(d["kg_prev"], 2), "Kg total": round(d["kg_total"], 2), "Horas necesarias": round(d["horas"], 2), "Horas disponibles": round(horas_disp, 2), "Ocupación %": round(occ, 2), "Rendimiento medio": round((d["rend_sum"] / d["n"]) if d["n"] else 0, 2), "Personal estimado": round((d["horas"] / max(horas_disp,1e-9)) * float(inputs["personnel"].get("personal_directo", 0) or 0), 1), "Estado": self._state(occ, inputs["semaphore_rules"], fam)})
        return rows

    def calculate_line_capacity(self, mapped: list[dict], inputs: dict) -> list[dict]:
        line_cfg = {str(r.get("codigo", "")): r for r in inputs["lines"]}
        by = defaultdict(lambda: {"kg":0.0,"horas":0.0,"pedidos":0,"formatos":set()})
        for m in mapped:
            d = by[m["linea"]]; d["kg"] += m["kg"]; d["horas"] += m["horas"]; d["pedidos"] += 1
            d["formatos"].add(str(m["pedido"].get("IdConfeccion", "")))
        rows=[]
        for cod, d in by.items():
            cfg = line_cfg.get(cod, {})
            hdisp = self._line_hours_available(cfg, inputs)
            occ = d["horas"]/hdisp*100 if hdisp>0 else 0
            rows.append({"Línea productiva": cod, "Kg": round(d["kg"],2), "Horas necesarias": round(d["horas"],2), "Horas disponibles línea": round(hdisp,2), "Ocupación %": round(occ,2), "Pedidos": d["pedidos"], "Cambios formato estimados": max(0,len(d["formatos"])-1), "Estado": self._state(occ, inputs["semaphore_rules"], cod)})
        return sorted(rows, key=lambda x: x["Ocupación %"], reverse=True)

    def calculate_capacity_summary(self, mapped: list[dict], family_rows: list[dict], inputs: dict) -> dict:
        kg_real = sum(m["kg"] for m in mapped if m["tipo_pedido"] == "Real")
        kg_prev = sum(m["kg"] for m in mapped if m["tipo_pedido"] == "Previsto")
        horas = sum(m["horas"] for m in mapped)
        hdisp = self._hours_available(inputs)
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
        rows = [r for r in payload.get("pedidos", []) if str(r.get("estado", "")).upper() != "DESCARTADO"]
        return rows

    def _hours_available(self, inputs: dict) -> float:
        per = inputs["personnel"]; gs = inputs["general_settings"]
        return max(0.1, float(per.get("personal_directo", 0) or 0) * float(per.get("horas_por_persona", gs.get("horas_turno", 8)) or 0))

    def _line_hours_available(self, cfg: dict, inputs: dict) -> float:
        if int(cfg.get("activa", 0) or 0) == 0:
            return 0.1
        gs = inputs["general_settings"]
        return max(0.1, float(gs.get("horas_turno", 8) or 8) * int(gs.get("numero_turnos", 1) or 1) * max(1, int(cfg.get("numero_maquinas", 1) or 1)))

    def _perf_map(self, rows: list[dict]) -> dict:
        out = {}
        for r in rows:
            if int(r.get("activo", 1) or 0) != 1: continue
            fam = str(r.get("familia", "")).strip(); tipo = str(r.get("tipo_linea", "")).strip()
            kg_h = float(r.get("kg_h_referencia", 0) or 0)
            if kg_h <= 0: kg_h = float(r.get("oph_referencia", 0) or 0) * 8
            out[(fam, tipo)] = kg_h
        return out

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

    def _state(self, occ: float, rules: list[dict], ambito: str) -> str:
        yellow, red = 85.0, 100.0
        for r in rules:
            if str(r.get("metrica", "")) == "ocupacion_pct" and str(r.get("ambito", "")).lower() in {"general", ambito.lower()}:
                yellow = float(r.get("umbral_amarillo", yellow) or yellow); red = float(r.get("umbral_rojo", red) or red); break
        return "Rojo" if occ >= red else "Amarillo" if occ >= yellow else "Verde"

    def _inc(self, tipo: str, order: dict, motivo: str, accion: str) -> dict:
        return {"Tipo incidencia": tipo, "Pedido": order.get("IdPedidoLora", order.get("id_previsto", "")), "Cliente": order.get("Cliente", order.get("cliente", "")), "Confección": order.get("IdConfeccion", order.get("grupo_confeccion", "")), "Línea productiva": "", "Motivo": motivo, "Acción sugerida": accion}
