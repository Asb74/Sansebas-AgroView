import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from services.comercial_service import ComercialService
from widgets.screen_header import ScreenHeader


class RankingClienteSettingsScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, service: ComercialService, on_back) -> None:
        super().__init__(master, padding=10)
        self.service = service
        self.on_back = on_back
        self.vars: dict[str, tk.StringVar] = {}
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        header = ScreenHeader(self, title="Clientes", subtitle="Configuración ranking clientes", on_back=self.on_back)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        fields = [
            ("PesoPrioridadKg", "Peso prioridad kg"), ("PesoPrioridadMargenTotal", "Peso prioridad margen total"),
            ("PesoPrioridadFacturacion", "Peso prioridad facturación"),
            ("UmbralCritica", "Umbral CRÍTICA"), ("UmbralMuyAlta", "Umbral MUY ALTA"),
            ("UmbralAlta", "Umbral ALTA"), ("UmbralMedia", "Umbral MEDIA"),
            ("MargenBuenoEurKg", "Margen bueno €/kg"), ("MargenAceptableEurKg", "Margen aceptable €/kg"),
            ("CumplimientoBuenoPct", "Cumplimiento bueno %"), ("CumplimientoAceptablePct", "Cumplimiento aceptable %"),
            ("CoberturaForfaitMinPct", "Cobertura forfait mínima %"),
            ("ReclamacionesAltasPor100kKg", "Reclamaciones altas / 100.000 kg"),
            ("ReclamadoAltoEurKg", "Reclamado alto €/kg"),
        ]
        for i, (key, label) in enumerate(fields, start=1):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="0")
            self.vars[key] = var
            ttk.Entry(self, textvariable=var, width=20).grid(row=i, column=1, sticky="w", padx=8)

        ttk.Button(self, text="Guardar", command=self._save).grid(row=len(fields)+2, column=0, pady=(10, 0), sticky="w")
        ttk.Button(self, text="Restaurar valores por defecto", command=self._reset).grid(row=len(fields)+2, column=1, pady=(10, 0), sticky="w")

    def _load(self) -> None:
        data = self.service.get_ranking_cliente_settings()
        for k, v in self.vars.items():
            v.set(str(data.get(k, "0")))

    def _save(self) -> None:
        try:
            data: dict[str, Any] = {}
            for k, v in self.vars.items():
                num = float(v.get())
                if num < 0:
                    raise ValueError("No se permiten valores negativos")
                data[k] = num
            pesos = data["PesoPrioridadKg"] + data["PesoPrioridadMargenTotal"] + data["PesoPrioridadFacturacion"]
            if abs(pesos - 100.0) > 0.001:
                messagebox.showwarning("Validación", "Los pesos de prioridad deben sumar 100.", parent=self)
                return
            self.service.update_ranking_cliente_settings(data)
            self.service.clear_cache()
            messagebox.showinfo("Configuración", "Configuración guardada", parent=self)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)

    def _reset(self) -> None:
        self.service.reset_ranking_cliente_settings()
        self.service.clear_cache()
        self._load()
        messagebox.showinfo("Configuración", "Valores restaurados", parent=self)
