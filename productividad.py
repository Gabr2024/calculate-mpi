"""
Calculadora MPI para Map Editors
--------------------------------
Calcula el MPI diario (el dato que se comparte en la junta MDI) a partir de:
  - el workflow
  - las tareas hechas
  - las horas productivas

Cada workflow tiene su propia meta por hora productiva:
  - Baseline (mínimo)  -> tabla WORKFLOWS, primer número
  - Efficiency target  -> tabla WORKFLOWS, segundo número

Métrica actual = Tareas ÷ Horas productivas
MPI            = Métrica actual ÷ Métrica planeada (Baseline)
  1 = en la métrica planeada · >1 = arriba · <1 = debajo

ACTUALIZACIÓN CADA Q: cuando cambien las métricas, edita PERIODO_METAS
y la tabla WORKFLOWS. Es lo único que hay que tocar.

Uso:
    python productividad.py
    python productividad.py "95 tareas en 6 horas"

Solo usa la biblioteca estándar de Python (3.8 o más nuevo). No hay que instalar nada.
"""

import re
import sys

# ===================== ACTUALIZAR CADA Q =====================
# Periodo de las métricas cargadas. Se muestra en la página para que
# todos sepan con qué metas se está calculando.
PERIODO_METAS = "Q1-26"

# Metas por hora productiva: "Workflow": (Baseline, Efficiency target)
# Para cambiar una meta o agregar un workflow, edita solo esta tabla.
WORKFLOWS = {
    "Auto Endorse": (36, 40),
    "Exceptions": (28, 31),
    "Features / FedEx Place": (23, 26),
    "Map Edits - DiDi - Atlas": (23, 25),
    "Map Edits - FedEx": (18, 20),
    "Map Feedback Amazon - Motive": (4, 4),
    "Map Feedback DiDi": (6, 6),
    "Map Feedback PC 4-7": (2, 2),
    "Map Feedback Smart-Tag": (5, 6),
    "Map Jobs": (23, 25),
    "Moderation - DiDi - Map Creator": (40, 45),
    "Moderation - Map Edits": (21, 23),
    "PAF": (34, 38),
    "Places": (22, 25),
    "Speed Limit": (3, 3),
}
# ==============================================================

# Metas por defecto si no se elige workflow
META_HORA = 18   # mínimo
IDEAL_HORA = 20  # ideal

# Palabras que se reconocen en la frase
KW_TAREAS = r"(?:tareas?|tasks?|edits?|ediciones?|edici[oó]n)"
KW_HORAS = r"(?:h|hr|hrs|horas?|hours?)"
NUM = r"(\d+(?:[.,]\d+)?(?::\d{1,2})?)"

LINEA = "─" * 44


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def a_numero(texto):
    """Convierte '8.75', '8,75' o '8:45' a float. Devuelve None si no se puede."""
    if texto is None:
        return None
    texto = str(texto).strip()
    hm = re.fullmatch(r"(\d+):(\d{1,2})", texto)
    if hm:
        return int(hm.group(1)) + int(hm.group(2)) / 60
    try:
        return float(texto.replace(",", "."))
    except ValueError:
        return None


def redondear(x, decimales=2):
    """Redondeo 'normal' (0.5 sube), no el redondeo bancario de round()."""
    factor = 10 ** decimales
    return int(x * factor + (0.5 if x >= 0 else -0.5)) / factor


def bonito(x):
    """142.0 -> '142', 8.25 -> '8.25', 0.8333 -> '0.83'."""
    v = redondear(x)
    return str(int(v)) if v == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")


def exacto(x):
    """Número sin redondear para mostrar la operación: 15.8333…, 108, 0.5."""
    if abs(x - round(x)) < 1e-9:
        return str(int(round(x)))
    corto = f"{x:.4f}"
    if abs(float(corto) - x) > 1e-9:
        return corto + "…"              # tiene más decimales
    return corto.rstrip("0").rstrip(".")


def redondeo(x, texto):
    """' → 87.96' solo cuando el redondeo cambia el número."""
    return f" → {texto}" if abs(x - round(x, 2)) > 1e-9 else ""


def falto_sobro(d):
    """Explica una diferencia en palabras."""
    if d < 0:
        return f"te faltaron {bonito(-d)} tareas"
    if d > 0:
        return f"hiciste {bonito(d)} tareas de más"
    return "lo cumpliste exacto"


# ---------------------------------------------------------------------------
# Lectura de la frase
# ---------------------------------------------------------------------------
def leer_frase(frase):
    """Extrae tareas y horas de una frase libre, por ejemplo '95 tareas en 6 horas'."""
    s = frase.lower()
    resultado = {"tareas": None, "horas": None}

    if m := re.search(rf"{NUM}\s*{KW_TAREAS}", s):
        resultado["tareas"] = a_numero(m.group(1))
    if m := re.search(rf"{NUM}\s*{KW_HORAS}\b", s):
        resultado["horas"] = a_numero(m.group(1))
    elif m := re.search(r"\d+:\d{1,2}", s):
        resultado["horas"] = a_numero(m.group(0))

    # Respaldo: "95 en 6" -> primer número = tareas, segundo = horas
    if resultado["tareas"] is None or resultado["horas"] is None:
        numeros = [a_numero(n) for n in re.findall(r"\d+(?:[.,]\d+)?(?::\d{1,2})?", s)]
        resto = [n for n in numeros if n not in (resultado["tareas"], resultado["horas"])]
        if resultado["tareas"] is None and resto:
            resultado["tareas"] = resto.pop(0)
        if resultado["horas"] is None and resto:
            resultado["horas"] = resto.pop(0)
    return resultado


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------
def metas_de(workflow=None):
    """Devuelve (meta_por_hora, ideal_por_hora) del workflow, o 18/20 si no hay."""
    if workflow and workflow in WORKFLOWS:
        return WORKFLOWS[workflow]
    return META_HORA, IDEAL_HORA


def calcular(tareas, horas, workflow=None):
    """
    tareas   = tareas hechas (None = solo planeación: cuántas tareas se esperan)
    horas    = horas productivas
    workflow = nombre de la tabla WORKFLOWS (define la métrica planeada e ideal)

    Métrica actual = tareas ÷ horas
    MPI            = métrica actual ÷ métrica planeada
      1  = exactamente en la métrica planeada
      >1 = arriba de la métrica planeada
      <1 = debajo de la métrica planeada
    Devuelve el texto del resultado.
    """
    if horas is None or horas <= 0:
        raise ValueError("Las horas productivas deben ser mayores a 0.")
    planeada, ideal = metas_de(workflow)
    h = bonito(horas)
    tareas_plan = horas * planeada
    tareas_ideal = horas * ideal

    lineas = []
    if workflow:
        lineas += [f"Workflow: {workflow}  (métricas {PERIODO_METAS})", ""]

    ops = ["", LINEA, "CÓMO SE CALCULÓ"]

    # ---------- Solo planeación (sin tareas) ----------
    if tareas is None:
        lineas += [
            "TUS DATOS",
            f"Horas productivas: {h}",
            "",
            "TU MÉTRICA",
            f"Métrica planeada: {bonito(planeada)} tareas por hora",
            f"Métrica ideal:    {bonito(ideal)} tareas por hora",
            "",
            f"PLANEACIÓN PARA {h} HORAS",
            f"Para un MPI de 1 (métrica planeada): {bonito(tareas_plan)} tareas",
            f"Para la métrica ideal:               {bonito(tareas_ideal)} tareas",
            "",
            "Escribe tus tareas hechas para ver tu MPI.",
        ]
        ops += [
            f"Tareas para MPI 1 = {exacto(horas)} horas × {exacto(planeada)} = {exacto(tareas_plan)}",
            f"Tareas para ideal = {exacto(horas)} horas × {exacto(ideal)} = {exacto(tareas_ideal)}",
        ]
        return "\n".join(lineas + ops)

    # ---------- Cálculo del MPI ----------
    actual = tareas / horas                 # métrica actual
    mpi_exacto = actual / planeada
    mpi = redondear(mpi_exacto)
    mpi_ideal_exacto = actual / ideal
    mpi_ideal = redondear(mpi_ideal_exacto)
    dif_plan = redondear(tareas - tareas_plan)
    dif_ideal = redondear(tareas - tareas_ideal)

    if mpi > 1:
        posicion = "Estás ARRIBA de la métrica planeada."
    elif mpi == 1:
        posicion = "Estás EXACTAMENTE en la métrica planeada."
    else:
        posicion = "Estás DEBAJO de la métrica planeada."

    lineas += [
        "TUS DATOS",
        f"Tareas hechas: {bonito(tareas)}",
        f"Horas productivas: {h}",
        "",
        "TU MÉTRICA (tareas por hora)",
        f"Métrica actual:   {bonito(actual)}   ← la tuya ({bonito(tareas)} ÷ {h})",
        f"Métrica planeada: {bonito(planeada)}",
        f"Métrica ideal:    {bonito(ideal)}",
        "",
        "TU MPI",
        f"MPI: {mpi:.2f}   ← este es el que se reporta",
        "  (1 = en la planeada · más de 1 = arriba · menos de 1 = debajo)",
        f"  {posicion}",
        f"MPI contra la métrica ideal: {mpi_ideal:.2f}",
        "",
        f"TAREAS EN {h} HORAS",
        f"Para un MPI de 1: {bonito(tareas_plan)} tareas → {falto_sobro(dif_plan)}",
        f"Para el ideal:    {bonito(tareas_ideal)} tareas → {falto_sobro(dif_ideal)}",
        "",
    ]

    if mpi_ideal >= 1:
        lineas.append("✅ Estás en la métrica ideal o arriba.")
    elif mpi >= 1:
        lineas.append("🟡 Cumpliste la métrica planeada, pero no la ideal.")
    else:
        lineas.append("❌ Estás debajo de la métrica planeada.")

    ops += [
        f"Métrica actual = {exacto(tareas)} tareas ÷ {exacto(horas)} horas = {exacto(actual)}"
        + redondeo(actual, bonito(actual)),
        f"MPI            = {exacto(actual)} ÷ {exacto(planeada)} = {exacto(mpi_exacto)}"
        + redondeo(mpi_exacto, f"{mpi:.2f}"),
        f"MPI ideal      = {exacto(actual)} ÷ {exacto(ideal)} = {exacto(mpi_ideal_exacto)}"
        + redondeo(mpi_ideal_exacto, f"{mpi_ideal:.2f}"),
        f"Tareas MPI 1   = {exacto(horas)} horas × {exacto(planeada)} = {exacto(tareas_plan)}",
        f"Tareas ideal   = {exacto(horas)} horas × {exacto(ideal)} = {exacto(tareas_ideal)}",
        f"Dif. MPI 1     = {exacto(tareas)} − {exacto(tareas_plan)} = {exacto(tareas - tareas_plan)}",
        f"Dif. ideal     = {exacto(tareas)} − {exacto(tareas_ideal)} = {exacto(tareas - tareas_ideal)}",
        "(→ = número redondeado a 2 decimales)",
    ]
    return "\n".join(lineas + ops)


# ---------------------------------------------------------------------------
# Interfaz de consola
# ---------------------------------------------------------------------------
def preguntar_numero(mensaje):
    while True:
        v = a_numero(input(mensaje).strip())
        if v is not None and v >= 0:
            return v
        print("  Valor no válido, intenta de nuevo.")


def preguntar_workflow():
    nombres = list(WORKFLOWS)
    print("Workflow:")
    for i, n in enumerate(nombres, 1):
        m, t = WORKFLOWS[n]
        print(f"  {i:2}) {n}  (mín {m}/h · ideal {t}/h)")
    while True:
        r = input("Número de workflow: ").strip()
        if r.isdigit() and 1 <= int(r) <= len(nombres):
            return nombres[int(r) - 1]
        print("  Número no válido.")


def una_vuelta(frase=None):
    workflow = preguntar_workflow()
    if frase is None:
        frase = input("\nEscribe tu frase (ej: '95 tareas en 6 horas')\n"
                      "o deja vacío para capturar dato por dato: ").strip()
    datos = leer_frase(frase) if frase else {"tareas": None, "horas": None}
    if datos["tareas"] is None:
        datos["tareas"] = preguntar_numero("Tareas hechas: ")
    if datos["horas"] is None:
        datos["horas"] = preguntar_numero("Horas productivas (ej: 6 o 6:30): ")
    try:
        texto = calcular(datos["tareas"], datos["horas"], workflow)
    except ValueError as e:
        print(f"\nERROR: {e}")
        return
    print("\n" + "=" * 50)
    print(texto)
    print("=" * 50)


def main():
    print(f"=== Calculadora MPI (metas {PERIODO_METAS}) ===\n")
    if len(sys.argv) > 1:  # frase pasada como argumento
        una_vuelta(" ".join(sys.argv[1:]))
        return
    while True:
        una_vuelta()
        if input("\n¿Otro cálculo? (s/n) [s]: ").strip().lower() in ("n", "no"):
            break
        print()


if __name__ == "__main__":
    main()