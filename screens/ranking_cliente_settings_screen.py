import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from services.comercial_service import ComercialService


class RankingClienteSettingsScreen(ttk.Frame):
    def __init__(self, master: tk.Misc, service: ComercialService, on_back) -> None:
        super().__init__(master, padding=10)
        self.service = service
        self.on_back = on_back
        self.vars: dict[str, tk.StringVar] = {}
        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        ttk.Label(self, text="Configuración ranking clientes", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        fields = [
            ("PesoRentabilidad", "Peso rentabilidad"), ("PesoCumplimiento", "Peso cumplimiento precio"),
            ("PesoVolumen", "Peso volumen"), ("PesoReclamaciones", "Peso reclamaciones"),
            ("MargenBuenoEurKg", "Margen bueno €/kg"), ("MargenAceptableEurKg", "Margen aceptable €/kg"),
            ("CumplimientoBuenoPct", "Cumplimiento bueno %"), ("CumplimientoAceptablePct", "Cumplimiento aceptable %"),
            ("CoberturaForfaitMinPct", "Cobertura forfait mínima %"),
            ("ReclamacionesAltasPor100kKg", "Reclamaciones altas / 100.000 kg"),
            ("ReclamadoAltoEurKg", "Reclamado alto €/kg"), ("PenalizacionReclamacionesMax", "Penalización máxima reclamaciones"),
            ("PenalizarCoberturaParcial", "Penalizar cobertura parcial (0/1)"), ("PesoCobertura", "Peso cobertura"),
        ]
        for i, (key, label) in enumerate(fields, start=1):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="w", pady=2)
            var = tk.StringVar(value="0")
            self.vars[key] = var
            ttk.Entry(self, textvariable=var, width=20).grid(row=i, column=1, sticky="w", padx=8)

        ttk.Button(self, text="Guardar", command=self._save).grid(row=len(fields)+2, column=0, pady=(10, 0), sticky="w")
        ttk.Button(self, text="Restaurar valores por defecto", command=self._reset).grid(row=len(fields)+2, column=1, pady=(10, 0), sticky="w")
        ttk.Button(self, text="Volver", command=self.on_back).grid(row=len(fields)+3, column=0, pady=(8, 0), sticky="w")

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
                data[k] = int(num) if k == "PenalizarCoberturaParcial" else num
            pesos = data["PesoRentabilidad"] + data["PesoCumplimiento"] + data["PesoVolumen"] + data["PesoReclamaciones"]
            if abs(pesos - 100.0) > 0.001:
                messagebox.showwarning("Validación", "Los pesos deben sumar 100.", parent=self)
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
