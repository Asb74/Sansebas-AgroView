# Auditoría de disponibilidad operativa en capacidad productiva

## Alcance auditado

Se revisó el uso actual de los maestros de disponibilidad operativa, compatibilidades, recursos físicos y líneas productivas dentro de `ProductionCapacityService`, sus repositorios, modelos implícitos en SQLite y pantallas de mantenimiento.

## Diagnóstico resumido

| Maestro / tabla | ¿Se carga? | ¿Se usa en `ProductionCapacityService`? | Uso real actual |
| --- | --- | --- | --- |
| `resource_operational_availability` | No encontrado | No | No existe lectura ni consulta con ese nombre en el código auditado. |
| `production_resource_availability` / clave `resource_availability` | Sí | Parcialmente | Solo genera incidencias por contexto cuando coincide con filtros; no excluye recursos ni modifica kg/h, unidades, horas o asignación. |
| `production_resource_compatibilities` / clave `resource_compatibilities` | Sí | Sí | Filtra compatibilidad de pesadoras por `tipo_malla`; los recursos no compatibles se muestran como incidencia sin kg asignados. |
| `production_physical_resources` / clave `physical_resources` | Sí | Sí | Aporta `activo`, `capacidad_kg_h`, `numero_unidades`, personal mínimo/óptimo y datos descriptivos para el cálculo de recursos físicos. |
| `production_line_capacity_config` / clave `line_capacity_config` | Sí | Sí | Define el puesto principal, el modo informativo/restrictivo de recursos y si la línea participa como activa en configuración de capacidad. |
| `production_line_required_resources` / clave `line_required_resources` | Sí | Sí | Vincula línea productiva con recursos requeridos y reparte kg cuando aplica. |

## Campos usados

### Disponibilidad operativa (`production_resource_availability`)

Campos leídos actualmente:

- `recurso_codigo`: identifica el recurso físico al que aplica la regla.
- `contexto`: se compara contra valores de filtros (`cultivo`, `grupo_varietal`, `var_coop`, `campana`) normalizados a mayúsculas.
- `disponible`: solo si es distinto de `1` se genera una incidencia.
- `motivo`: se usa en el texto de la incidencia cuando existe.

### Compatibilidades (`production_resource_compatibilities`)

Campos leídos actualmente:

- `recurso_codigo`.
- `compatible_con`.
- `valor`.
- `activo`.

El uso efectivo está limitado a pesadoras (`tipo_recurso == "pesadora"` o código que empieza por `PESADORA_`) y a la dimensión `tipo_malla`.

### Recursos físicos (`production_physical_resources`)

Campos usados por capacidad:

- `codigo`.
- `tipo_recurso`.
- `familia_operativa`.
- `capacidad_kg_h`.
- `numero_unidades`.
- `personal_minimo`.
- `personal_optimo`.
- `activo`.

### Líneas productivas y configuración de capacidad

Campos usados por capacidad:

- `production_line_capacity_config.linea_productiva`.
- `production_line_capacity_config.familia_productiva`.
- `production_line_capacity_config.puesto_productivo_principal`.
- `production_line_capacity_config.modo_uso_recursos`.
- `production_line_capacity_config.usar_capacidad_agregada`.
- `production_line_capacity_config.activa`.
- `production_line_required_resources.linea_productiva`.
- `production_line_required_resources.recurso_codigo`.
- `production_line_required_resources.reparte_kg`.
- `production_line_required_resources.orden`.
- `production_line_required_resources.activo`.

## Campos ignorados o sin impacto de cálculo

### Disponibilidad operativa

- `prioridad`: se guarda y se muestra, pero no se usa para resolver conflictos, ordenar reglas ni decidir qué regla prevalece.
- `observaciones`: se guarda y se muestra, pero no participa en cálculo ni incidencias.
- `updated_at`: solo auditoría técnica de persistencia.
- Disponibilidades con `disponible = 1`: no alteran el cálculo; equivalen a no tener bloqueo.
- Disponibilidades sin coincidencia exacta entre `contexto` y filtros: no alteran el cálculo.

## Impacto real sobre capacidad

La disponibilidad operativa no modifica la capacidad efectiva. En concreto:

1. No cambia `capacidad_kg_h`.
2. No cambia `numero_unidades`.
3. No cambia `kg_asignados`.
4. No cambia `horas_disponibles`.
5. No elimina recursos de la lista de recursos requeridos.
6. No impide el cálculo en modo restrictivo.
7. Sí puede cambiar el `Estado` de la fila a `Incidencia`, porque la incidencia queda asociada al recurso.
8. Sí aparece como incidencia agregada en el resultado final.

Por tanto, su efecto actual es informativo/alerta, no restrictivo.

## Recursos mostrados que deberían excluirse si la disponibilidad fuera restrictiva

Actualmente se siguen mostrando y pueden conservar kg asignados los recursos que cumplan simultáneamente:

1. Están configurados como requeridos para una línea activa.
2. Existen en `production_physical_resources`.
3. Superan el filtro de compatibilidad, o no están sujetos a compatibilidad de pesadora.
4. Tienen una fila en `production_resource_availability` con el mismo `recurso_codigo`.
5. El `contexto` de esa fila coincide con algún filtro activo de `cultivo`, `grupo_varietal`, `var_coop` o `campana`.
6. `disponible != 1`.

En ese caso el recurso aparece con incidencia `Recurso no disponible por contexto`, pero no se excluye ni se descuenta de capacidad.

## Logs temporales añadidos

Se añadieron logs con prefijo `[CAPACITY AUDIT]` para observar, sin modificar comportamiento, si la disponibilidad operativa se está aplicando a cálculo o solo a incidencias.

Formato:

```text
[CAPACITY AUDIT] recurso=... contexto=... disponible=... usado_en_calculo=True/False
```

Criterio actual del log:

- `usado_en_calculo=False` cuando una regla de disponibilidad se lee y genera una incidencia, porque hoy no filtra ni recalcula capacidad.
- `usado_en_calculo=False` también cuando la fila pasa a cálculo de uso de recursos, para dejar explícito que la disponibilidad no se aplica al cálculo numérico de horas/capacidad.
