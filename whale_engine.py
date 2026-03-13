# =============================================================
# WHALE TRACKER — setup_console.py
# Consola interactiva para configurar tickers y parámetros.
# Corre esto UNA VEZ antes de lanzar el tracker.
# Guarda todo en config.py automáticamente.
# =============================================================
# CÓMO USARLO:
#   python setup_console.py
# =============================================================

import json
import os
import sys
from datetime import datetime

# Colores para Windows (colorama) con fallback si no está instalado
try:
    from colorama import init, Fore, Back, Style
    init(autoreset=True)
    C_TITLE   = Fore.CYAN + Style.BRIGHT
    C_OK      = Fore.GREEN + Style.BRIGHT
    C_WARN    = Fore.YELLOW + Style.BRIGHT
    C_ERR     = Fore.RED + Style.BRIGHT
    C_DIM     = Fore.WHITE + Style.DIM
    C_BOLD    = Style.BRIGHT
    C_RESET   = Style.RESET_ALL
    C_WHALE   = Fore.CYAN + Style.BRIGHT
    C_SCORE   = Fore.GREEN
    C_HEADER  = Fore.BLUE + Style.BRIGHT
except ImportError:
    C_TITLE = C_OK = C_WARN = C_ERR = C_DIM = C_BOLD = C_RESET = C_WHALE = C_SCORE = C_HEADER = ""

# =============================================================
# TICKERS SUGERIDOS POR CATEGORÍA
# =============================================================
SUGGESTED = {
    "🏦 Bancos ARG (ADR)": {
        "GGAL": "Grupo Financiero Galicia",
        "BBAR": "BBVA Argentina",
        "BMA":  "Banco Macro",
        "SUPV": "Supervielle",
    },
    "⚡ Energía ARG (ADR)": {
        "YPF":  "YPF S.A.",
        "PAM":  "Pampa Energía",
        "CEPU": "Central Puerto",
        "TGS":  "Transportadora Gas Sur",
    },
    "🏗 Otros ARG (ADR)": {
        "LOMA": "Loma Negra",
        "IRS":  "IRSA",
        "CRESY":"Cresud",
        "CAAP": "Corporación América Airports",
    },
    "💻 Tech / Global": {
        "GLOB": "Globant",
        "MELI": "MercadoLibre",
        "AAPL": "Apple",
        "TSLA": "Tesla",
        "SPY":  "S&P 500 ETF",
        "QQQ":  "Nasdaq ETF",
    },
}

TIMEFRAMES = {
    "1":  ("1m",  "1 minuto   — Scalping extremo"),
    "2":  ("5m",  "5 minutos  — Scalping / day trading"),
    "3":  ("15m", "15 minutos — Day trading"),
    "4":  ("1h",  "1 hora     — Swing trading (RECOMENDADO para SMC)"),
    "5":  ("4h",  "4 horas    — Swing / posicional"),
    "6":  ("1d",  "Diario     — Posicional / largo plazo"),
}

PERIODS = {
    "1": ("5d",  "5 días"),
    "2": ("1mo", "1 mes"),
    "3": ("3mo", "3 meses  (RECOMENDADO)"),
    "4": ("6mo", "6 meses"),
    "5": ("1y",  "1 año"),
}

# =============================================================
# HELPERS DE DISPLAY
# =============================================================

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def header():
    print(C_WHALE + """
╔══════════════════════════════════════════════════════════╗
║         🐋  WHALE TRACKER — Setup Console  🐋           ║
║     Configurá tus activos sin tocar ningún archivo       ║
╚══════════════════════════════════════════════════════════╝""" + C_RESET)

def divider(title=""):
    if title:
        print(C_DIM + f"\n{'─' * 20} {title} {'─' * 20}" + C_RESET)
    else:
        print(C_DIM + "─" * 58 + C_RESET)

def ok(msg):    print(C_OK   + f"  ✓  {msg}" + C_RESET)
def warn(msg):  print(C_WARN + f"  ⚠  {msg}" + C_RESET)
def err(msg):   print(C_ERR  + f"  ✗  {msg}" + C_RESET)
def info(msg):  print(C_DIM  + f"     {msg}" + C_RESET)

def score_bar(score, total=13):
    filled = int((score / total) * 20)
    bar = "█" * filled + "░" * (20 - filled)
    pct = int(score / total * 100)
    if pct >= 75: color = C_OK
    elif pct >= 50: color = C_WARN
    else: color = C_DIM
    return color + f"[{bar}] {pct}%" + C_RESET

def input_prompt(msg):
    return input(C_BOLD + f"\n  › {msg}: " + C_RESET).strip()

def wait():
    input(C_DIM + "\n  Presioná ENTER para continuar..." + C_RESET)

# =============================================================
# ESTADO DE LA SESIÓN
# =============================================================
session = {
    "tickers":          [],
    "timeframe":        "1h",
    "period":           "3mo",
    "signal_threshold": 8,
    "warn_threshold":   6,
    "update_interval":  60,
    "sound":            False,
    "log_file":         True,
    "dashboard_port":   8050,
    "dashboard_candles": 120,
}

# Cargar config existente si hay
def load_existing():
    if os.path.exists("config.py"):
        try:
            # Leer tickers de la config existente
            with open("config.py", "r") as f:
                content = f.read()
            # Buscar línea TICKERS en el archivo guardado por nosotros
            if "# WHALE_TRACKER_CONFIG_JSON" in content:
                start = content.find("# WHALE_TRACKER_CONFIG_JSON\n# ") + len("# WHALE_TRACKER_CONFIG_JSON\n# ")
                end   = content.find("\n", start)
                data  = json.loads(content[start:end])
                session.update(data)
                return True
        except Exception:
            pass
    return False

# =============================================================
# MENÚ PRINCIPAL
# =============================================================
def main_menu():
    while True:
        clear()
        header()

        # Status actual
        divider("Configuración actual")
        if session["tickers"]:
            print(C_BOLD + f"\n  Tickers ({len(session['tickers'])}/10):" + C_RESET)
            for i, t in enumerate(session["tickers"], 1):
                print(f"    {C_SCORE}{i:2}. {t:<8}{C_RESET}")
        else:
            warn("Sin tickers configurados todavía")

        print(f"\n  Timeframe  : {C_BOLD}{session['timeframe']}{C_RESET}")
        print(f"  Período    : {C_BOLD}{session['period']}{C_RESET}")
        print(f"  Score señal: {C_BOLD}{session['signal_threshold']}/13{C_RESET}  {score_bar(session['signal_threshold'])}")
        print(f"  Actualizar : cada {C_BOLD}{session['update_interval']}s{C_RESET}")

        divider("Opciones")
        print(f"""
  {C_TITLE}1{C_RESET}  Agregar tickers (sugeridos o personalizados)
  {C_TITLE}2{C_RESET}  Quitar tickers
  {C_TITLE}3{C_RESET}  Cambiar timeframe
  {C_TITLE}4{C_RESET}  Cambiar período de datos
  {C_TITLE}5{C_RESET}  Ajustar parámetros del engine
  {C_TITLE}6{C_RESET}  Ajustar alertas y dashboard
  {C_TITLE}7{C_RESET}  Ver lista completa de tickers sugeridos
  {C_OK}G{C_RESET}  💾 Guardar y generar config.py
  {C_ERR}Q{C_RESET}  Salir
""")
        choice = input_prompt("Elegí una opción").upper()

        if   choice == "1": menu_add_tickers()
        elif choice == "2": menu_remove_tickers()
        elif choice == "3": menu_timeframe()
        elif choice == "4": menu_period()
        elif choice == "5": menu_engine_params()
        elif choice == "6": menu_alerts()
        elif choice == "7": menu_browse_tickers()
        elif choice == "G": save_config()
        elif choice == "Q":
            print(C_DIM + "\n  Hasta luego 🐋\n" + C_RESET)
            sys.exit(0)

# =============================================================
# MENÚ: AGREGAR TICKERS
# =============================================================
def menu_add_tickers():
    while True:
        clear()
        header()
        divider("Agregar tickers")

        slots = 10 - len(session["tickers"])
        print(f"\n  Tenés {C_BOLD}{len(session['tickers'])}{C_RESET} ticker(s) · Podés agregar {C_WARN}{slots} más{C_RESET}")

        if session["tickers"]:
            print(f"\n  Actuales: {C_OK}" + "  ".join(session["tickers"]) + C_RESET)

        print(f"""
  {C_TITLE}1{C_RESET}  Elegir de lista sugerida por categoría
  {C_TITLE}2{C_RESET}  Escribir ticker manualmente
  {C_TITLE}3{C_RESET}  Agregar todos los bancos ARG (GGAL BBAR BMA SUPV)
  {C_TITLE}4{C_RESET}  Agregar pack energía ARG  (YPF PAM CEPU TGS)
  {C_TITLE}V{C_RESET}  Volver al menú principal
""")
        choice = input_prompt("Opción").upper()

        if choice == "1":
            add_from_list()
        elif choice == "2":
            add_manual()
        elif choice == "3":
            add_pack(["GGAL", "BBAR", "BMA", "SUPV"])
        elif choice == "4":
            add_pack(["YPF", "PAM", "CEPU", "TGS"])
        elif choice == "V":
            break

def add_from_list():
    clear()
    header()
    divider("Tickers sugeridos")
    all_tickers = {}
    idx = 1
    for category, tickers in SUGGESTED.items():
        print(f"\n  {C_HEADER}{category}{C_RESET}")
        for ticker, name in tickers.items():
            status = C_OK + "✓" if ticker in session["tickers"] else C_DIM + " "
            print(f"  {status}{C_RESET} {C_TITLE}{idx:2}. {ticker:<8}{C_RESET} {C_DIM}{name}{C_RESET}")
            all_tickers[str(idx)] = ticker
            idx += 1

    print(f"\n  {C_DIM}Escribí los números separados por coma. Ej: 1,3,5{C_RESET}")
    raw = input_prompt("Números a agregar (o ENTER para cancelar)")
    if not raw:
        return
    for n in raw.split(","):
        t = all_tickers.get(n.strip())
        if t:
            add_ticker(t)

def add_manual():
    raw = input_prompt("Escribí el ticker (ej: GGAL, YPF, MELI — podés poner varios separados por coma)")
    if not raw:
        return
    for t in raw.upper().replace(" ", "").split(","):
        if t:
            add_ticker(t)
    wait()

def add_pack(tickers):
    for t in tickers:
        add_ticker(t)
    wait()

def add_ticker(ticker):
    ticker = ticker.upper().strip()
    if len(session["tickers"]) >= 10:
        warn(f"Límite de 10 tickers alcanzado. No se agregó {ticker}")
        return
    if ticker in session["tickers"]:
        warn(f"{ticker} ya está en la lista")
        return
    session["tickers"].append(ticker)
    ok(f"{ticker} agregado")

# =============================================================
# MENÚ: QUITAR TICKERS
# =============================================================
def menu_remove_tickers():
    if not session["tickers"]:
        warn("No hay tickers para quitar")
        wait()
        return

    clear()
    header()
    divider("Quitar tickers")

    print()
    for i, t in enumerate(session["tickers"], 1):
        print(f"  {C_TITLE}{i}{C_RESET}. {t}")

    print(f"\n  {C_WARN}T{C_RESET}  Quitar TODOS")
    print(f"  {C_DIM}V{C_RESET}  Volver")

    raw = input_prompt("Número(s) a quitar (ej: 1,3) o T para todos").upper()

    if raw == "T":
        session["tickers"] = []
        ok("Lista vaciada")
    elif raw and raw != "V":
        to_remove = []
        for n in raw.split(","):
            try:
                idx = int(n.strip()) - 1
                if 0 <= idx < len(session["tickers"]):
                    to_remove.append(session["tickers"][idx])
            except ValueError:
                pass
        for t in to_remove:
            session["tickers"].remove(t)
            ok(f"{t} eliminado")
    wait()

# =============================================================
# MENÚ: TIMEFRAME
# =============================================================
def menu_timeframe():
    clear()
    header()
    divider("Timeframe de análisis")

    print(f"\n  Actual: {C_BOLD}{session['timeframe']}{C_RESET}\n")
    for key, (tf, desc) in TIMEFRAMES.items():
        marker = C_OK + "▶ " if tf == session["timeframe"] else "  "
        print(f"  {marker}{C_TITLE}{key}{C_RESET}  {tf:<6} {C_DIM}{desc}{C_RESET}")

    print()
    info("Para SMC institucional, 1h es el timeframe más efectivo")
    info("Scalping en 1m o 5m requiere reaccionar en segundos")

    choice = input_prompt("Elegí (1-6) o ENTER para mantener actual")
    if choice in TIMEFRAMES:
        session["timeframe"] = TIMEFRAMES[choice][0]
        ok(f"Timeframe configurado: {session['timeframe']}")
        wait()

# =============================================================
# MENÚ: PERÍODO
# =============================================================
def menu_period():
    clear()
    header()
    divider("Período de datos históricos")

    print(f"\n  Actual: {C_BOLD}{session['period']}{C_RESET}\n")
    for key, (p, desc) in PERIODS.items():
        marker = C_OK + "▶ " if p == session["period"] else "  "
        print(f"  {marker}{C_TITLE}{key}{C_RESET}  {p:<6} {C_DIM}{desc}{C_RESET}")

    print()
    info("Más datos = mejor cálculo de OBs y zonas. 3mo es el balance ideal.")

    choice = input_prompt("Elegí (1-5) o ENTER para mantener actual")
    if choice in PERIODS:
        session["period"] = PERIODS[choice][0]
        ok(f"Período configurado: {session['period']}")
        wait()

# =============================================================
# MENÚ: PARÁMETROS DEL ENGINE
# =============================================================
def menu_engine_params():
    clear()
    header()
    divider("Parámetros del engine")

    print(f"""
  {C_DIM}Score mínimo para señal ACTIVA (actual: {C_BOLD}{session['signal_threshold']}/13{C_DIM}){C_RESET}
  {C_DIM}  8/13 = equilibrio (recomendado){C_RESET}
  {C_DIM}  6/13 = más señales, más falsas{C_RESET}
  {C_DIM}  10/13 = muy selectivo, pocas señales pero de alta calidad{C_RESET}
""")
    raw = input_prompt(f"Score mínimo (6-12) [actual: {session['signal_threshold']}]")
    try:
        v = int(raw)
        if 6 <= v <= 12:
            session["signal_threshold"] = v
            session["warn_threshold"]   = max(4, v - 2)
            ok(f"Score mínimo: {v}/13  |  Advertencia: {session['warn_threshold']}/13")
        else:
            err("Valor fuera de rango (6-12)")
    except ValueError:
        info("Sin cambios")

    print(f"""
  {C_DIM}Intervalo de actualización (actual: cada {C_BOLD}{session['update_interval']}s{C_DIM}){C_RESET}
  {C_DIM}  Mínimo recomendado: 60s (límite de yfinance){C_RESET}
  {C_DIM}  30s funciona pero puede dar errores de rate limit{C_RESET}
""")
    raw = input_prompt(f"Segundos entre updates (30-300) [actual: {session['update_interval']}]")
    try:
        v = int(raw)
        if 30 <= v <= 300:
            session["update_interval"] = v
            ok(f"Actualización cada {v}s")
            if v < 60:
                warn("Menos de 60s puede causar errores de rate limit con yfinance")
        else:
            err("Valor fuera de rango (30-300)")
    except ValueError:
        info("Sin cambios")

    wait()

# =============================================================
# MENÚ: ALERTAS Y DASHBOARD
# =============================================================
def menu_alerts():
    clear()
    header()
    divider("Alertas y dashboard")

    print(f"""
  {C_TITLE}1{C_RESET}  Sonido al detectar señal    [{C_OK + "ON" if session["sound"] else C_DIM + "OFF"}{C_RESET}]
  {C_TITLE}2{C_RESET}  Guardar log en CSV          [{C_OK + "ON" if session["log_file"] else C_DIM + "OFF"}{C_RESET}]
  {C_TITLE}3{C_RESET}  Puerto dashboard             [{C_BOLD}{session["dashboard_port"]}{C_RESET}]
  {C_TITLE}4{C_RESET}  Velas en gráfico             [{C_BOLD}{session["dashboard_candles"]}{C_RESET}]
  {C_DIM}V{C_RESET}  Volver
""")
    choice = input_prompt("Opción").upper()

    if choice == "1":
        session["sound"] = not session["sound"]
        ok(f"Sonido {'activado' if session['sound'] else 'desactivado'}")
    elif choice == "2":
        session["log_file"] = not session["log_file"]
        ok(f"Log CSV {'activado' if session['log_file'] else 'desactivado'}")
    elif choice == "3":
        raw = input_prompt("Puerto (ej: 8050)")
        try:
            session["dashboard_port"] = int(raw)
            ok(f"Puerto: {session['dashboard_port']}")
        except ValueError:
            err("Puerto inválido")
    elif choice == "4":
        raw = input_prompt("Cantidad de velas (50-500)")
        try:
            v = int(raw)
            if 50 <= v <= 500:
                session["dashboard_candles"] = v
                ok(f"Velas en gráfico: {v}")
        except ValueError:
            err("Valor inválido")

    if choice != "V":
        wait()

# =============================================================
# MENÚ: BROWSE TICKERS
# =============================================================
def menu_browse_tickers():
    clear()
    header()
    divider("Todos los tickers sugeridos")
    for category, tickers in SUGGESTED.items():
        print(f"\n  {C_HEADER}{category}{C_RESET}")
        for ticker, name in tickers.items():
            status = C_OK + "  ✓ EN LISTA" if ticker in session["tickers"] else ""
            print(f"    {C_TITLE}{ticker:<8}{C_RESET} {C_DIM}{name}{C_RESET}{status}")
    print()
    info("Para agregar cualquier otro ticker que no esté acá,")
    info("usá la opción 'Escribir ticker manualmente' en el menú anterior.")
    wait()

# =============================================================
# GUARDAR CONFIG.PY
# =============================================================
def save_config():
    if not session["tickers"]:
        err("Agregá al menos 1 ticker antes de guardar")
        wait()
        return

    clear()
    header()
    divider("Guardando configuración")

    # Serializar sesión para poder recargarla
    session_json = json.dumps(session)

    # Generar el contenido de config.py
    tickers_str = "\n".join([f'    "{t}",' for t in session["tickers"]])
    timestamp   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    config_content = f'''# =============================================================
# WHALE TRACKER — config.py
# Generado automáticamente por setup_console.py
# Última actualización: {timestamp}
# NO editar manualmente — usar: python setup_console.py
# =============================================================
# WHALE_TRACKER_CONFIG_JSON
# {session_json}

TICKERS = [
{tickers_str}
]

TIMEFRAME = "{session["timeframe"]}"

PERIOD = "{session["period"]}"

ENGINE = {{
    "cvd_length":        20,
    "vol_length":        20,
    "vol_multiplier":    1.5,
    "ob_length":         5,
    "ob_mitigation":     0.5,
    "fvg_min_pct":       0.2,
    "sweep_lookback":    20,
    "sweep_wick_ratio":  2.0,
    "swing_length":      5,
    "signal_threshold":  {session["signal_threshold"]},
    "warn_threshold":    {session["warn_threshold"]},
}}

UPDATE_INTERVAL = {session["update_interval"]}

ALERTS = {{
    "sound":    {str(session["sound"])},
    "console":  True,
    "log_file": {str(session["log_file"])},
}}

DASHBOARD = {{
    "auto_open":        True,
    "port":             {session["dashboard_port"]},
    "theme":            "dark",
    "candles":          {session["dashboard_candles"]},
}}
'''

    try:
        with open("config.py", "w", encoding="utf-8") as f:
            f.write(config_content)

        print()
        ok("config.py guardado exitosamente")
        print()
        print(f"  {C_BOLD}Resumen:{C_RESET}")
        print(f"  Tickers   : {C_OK}{', '.join(session['tickers'])}{C_RESET}")
        print(f"  Timeframe : {C_BOLD}{session['timeframe']}{C_RESET}")
        print(f"  Período   : {C_BOLD}{session['period']}{C_RESET}")
        print(f"  Señal en  : {C_BOLD}{session['signal_threshold']}/13 puntos{C_RESET}")
        print()
        info("Próximo paso: correr main.py para iniciar el tracker")
        info("  python main.py")
        print()

    except Exception as e:
        err(f"Error al guardar: {e}")

    wait()

# =============================================================
# PUNTO DE ENTRADA
# =============================================================
if __name__ == "__main__":
    clear()
    # Intentar cargar config existente
    if load_existing():
        print(C_OK + "\n  ✓ Configuración anterior cargada" + C_RESET)
        import time
        time.sleep(1)
    main_menu()
