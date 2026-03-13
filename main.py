# =============================================================
# WHALE TRACKER — main.py
# Loop principal: monitorea todos los tickers en paralelo
# y muestra la tabla en consola actualizándose en tiempo real.
# =============================================================
# CÓMO USAR:
#   1. python setup_console.py   ← configurar tickers (una vez)
#   2. python main.py            ← iniciar el tracker
#   3. Ctrl+C para detener
# =============================================================

import time
import os
import sys
import csv
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# Colores
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    CY  = Fore.CYAN + Style.BRIGHT
    GN  = Fore.GREEN + Style.BRIGHT
    YW  = Fore.YELLOW + Style.BRIGHT
    RD  = Fore.RED + Style.BRIGHT
    DM  = Style.DIM
    BL  = Fore.BLUE + Style.BRIGHT
    MG  = Fore.MAGENTA + Style.BRIGHT
    RST = Style.RESET_ALL
    WH  = Style.BRIGHT
except ImportError:
    CY = GN = YW = RD = DM = BL = MG = RST = WH = ""

# Importar módulos propios
try:
    from config import TICKERS, TIMEFRAME, PERIOD, ENGINE, UPDATE_INTERVAL, ALERTS
except ImportError:
    print("\n  ⚠ No encontré config.py")
    print("  Corré primero: python setup_console.py\n")
    sys.exit(1)

try:
    from whale_engine import WhaleEngine
except ImportError:
    print("\n  ⚠ No encontré whale_engine.py")
    print("  Asegurate de tener todos los archivos en la misma carpeta.\n")
    sys.exit(1)

# =============================================================
# ESTADO GLOBAL
# =============================================================

# Un engine por ticker, persistente entre ciclos
engines: dict[str, WhaleEngine] = {}
results: dict[str, dict]        = {}
errors:  dict[str, str]         = {}
lock = threading.Lock()

# Historial de señales para el log
signal_history: list[dict] = []

# =============================================================
# HELPERS DE DISPLAY
# =============================================================

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def color_score(score: int, total: int = 13) -> str:
    pct = score / total
    if pct >= 0.75: return GN + f"{score:>2}/{total}" + RST
    if pct >= 0.50: return YW + f"{score:>2}/{total}" + RST
    if pct >= 0.30: return CY + f"{score:>2}/{total}" + RST
    return DM + f"{score:>2}/{total}" + RST

def color_status(status: str, emoji: str, label: str) -> str:
    if status == "ENTRY":   return GN  + f"{emoji} {label:<16}" + RST
    if status == "SETUP":   return YW  + f"{emoji} {label:<16}" + RST
    if status == "WATCH":   return CY  + f"{emoji} {label:<16}" + RST
    return DM + f"{emoji} {label:<16}" + RST

def mini_bar(score: int, total: int = 13, width: int = 10) -> str:
    filled = int(score / total * width)
    bar    = "█" * filled + "░" * (width - filled)
    if score / total >= 0.75: return GN  + bar + RST
    if score / total >= 0.50: return YW  + bar + RST
    if score / total >= 0.30: return CY  + bar + RST
    return DM + bar + RST

def score_detail(s: dict) -> str:
    """Línea compacta con detalle de cada módulo."""
    def flag(val, label):
        v = int(val) if isinstance(val, (bool, int, float)) else 0
        return (GN + f"{label}✓" + RST) if v > 0 else (DM + f"{label}·" + RST)
    return (
        flag(s.get("cvd_div"),    "CVD ")  +
        flag(s.get("high_vol"),   "VOL ")  +
        flag(s.get("in_ob"),      "OB ")   +
        flag(s.get("in_fvg"),     "FVG ")  +
        flag(s.get("sweep"),      "SWP ")  +
        flag(s.get("mss"),        "MSS")
    )

# =============================================================
# ANÁLISIS DE UN TICKER (corre en thread separado)
# =============================================================

def analyze_ticker(ticker: str) -> tuple[str, dict | None, str | None]:
    """Corre el engine para un ticker. Retorna (ticker, result, error)."""
    try:
        engine = engines[ticker]
        result = engine.run()
        return ticker, result, None
    except Exception as e:
        return ticker, None, str(e)

# =============================================================
# GUARDAR SEÑAL EN CSV
# =============================================================

def log_signal(ticker: str, result: dict):
    """Guarda señales ENTRY y SETUP en signals_log.csv"""
    if not ALERTS.get("log_file", True):
        return
    if result["status"] not in ("ENTRY", "SETUP"):
        return

    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker":    ticker,
        "status":    result["label"],
        "score":     result["total"],
        "price":     result["price"],
        "cvd_div":   result.get("cvd_div", 0),
        "in_ob":     result.get("in_ob", 0),
        "in_fvg":    result.get("in_fvg", 0),
        "sweep":     result.get("sweep", 0),
        "mss":       result.get("mss", 0),
        "range_pct": result.get("range_pct", 0),
    }

    file_exists = os.path.exists("signals_log.csv")
    with open("signals_log.csv", "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    signal_history.append(row)

# =============================================================
# PANTALLA PRINCIPAL
# =============================================================

def render_screen(cycle: int, elapsed: float, next_update: int):
    """Dibuja toda la pantalla en consola."""
    clear()
    now = datetime.now().strftime("%H:%M:%S")

    # ── HEADER ──────────────────────────────────────────────
    print(CY + """
╔══════════════════════════════════════════════════════════════════════════════╗
║              🐋  WHALE TRACKER  —  SMC Confluence Engine                    ║
╚══════════════════════════════════════════════════════════════════════════════╝""" + RST)

    print(f"  {DM}Ciclo {cycle}  ·  {now}  ·  TF: {TIMEFRAME}  ·  "
          f"Próxima actualización en {next_update}s  ·  Ctrl+C para salir{RST}\n")

    # ── TABLA DE TICKERS ────────────────────────────────────
    header = (
        f"  {WH}{'TICKER':<8}  {'SCORE':>5}  {'BAR':<12}  "
        f"{'STATUS':<22}  {'PRECIO':>8}  {'RANGE%':>7}  SEÑALES{RST}"
    )
    print(header)
    print(DM + "  " + "─" * 76 + RST)

    # Ordenar por score descendente
    sorted_tickers = sorted(
        TICKERS,
        key=lambda t: results.get(t, {}).get("total", -1),
        reverse=True
    )

    entry_count = 0
    setup_count = 0

    for ticker in sorted_tickers:
        result = results.get(ticker)
        error  = errors.get(ticker)

        if error:
            print(f"  {DM}{ticker:<8}  {'—':>5}  {'—':<12}  "
                  f"{'ERROR':<22}  {str(error)[:20]}{RST}")
            continue

        if not result:
            print(f"  {DM}{ticker:<8}  {'—':>5}  {'':12}  "
                  f"{'⏳ Cargando...':<22}{RST}")
            continue

        score_str  = color_score(result["total"])
        bar_str    = mini_bar(result["total"])
        status_str = color_status(result["status"], result["emoji"], result["label"])
        detail_str = score_detail(result)
        price_str  = f"${result['price']:>7.2f}"
        range_str  = f"{result['range_pct']:>5.1f}%"

        print(f"  {WH}{ticker:<8}{RST}  {score_str}  {bar_str}  "
              f"{status_str}  {price_str}  {range_str}  {detail_str}")

        if result["status"] == "ENTRY": entry_count += 1
        if result["status"] == "SETUP": setup_count += 1

    print(DM + "  " + "─" * 76 + RST)

    # ── RESUMEN ─────────────────────────────────────────────
    total_ok = sum(1 for t in TICKERS if results.get(t))
    print(f"\n  Monitoreando {WH}{total_ok}/{len(TICKERS)}{RST} tickers  ·  "
          f"{GN}{entry_count} ENTRY{RST}  ·  "
          f"{YW}{setup_count} SETUP{RST}  ·  "
          f"Actualizado hace {DM}{elapsed:.0f}s{RST}\n")

    # ── ALERTAS RECIENTES ───────────────────────────────────
    recent = [s for s in signal_history[-5:] if s["status"] in ("WHALE ENTRY", "SETUP")]
    if recent:
        print(DM + "  ── Señales recientes " + "─" * 55 + RST)
        for s in reversed(recent):
            col = GN if "ENTRY" in s["status"] else YW
            print(f"  {col}{s['timestamp']}  {s['ticker']:<8}  "
                  f"{s['status']:<16}  Score {s['score']}/13  "
                  f"${s['price']}{RST}")
        print()

    # ── DETALLE DE SEÑALES ACTIVAS ───────────────────────────
    active = [(t, results[t]) for t in sorted_tickers
              if results.get(t) and results[t]["status"] in ("ENTRY", "SETUP")]

    if active:
        print(DM + "  ── Detalle señales activas " + "─" * 49 + RST)
        for ticker, r in active:
            col = GN if r["status"] == "ENTRY" else YW
            ob_info = ""
            if r.get("in_ob"):
                top = r.get("ob_bull_top", 0)
                bot = r.get("ob_bull_bot", 0)
                if top and bot and top == top:  # not nan
                    ob_info = f"  OB: ${bot:.2f}–${top:.2f}"

            print(f"\n  {col}{'▶ ' + ticker + ' — ' + r['label']}{RST}")
            print(f"    Score    : {r['total']}/13 ({r['pct']}%)")
            print(f"    Precio   : ${r['price']}{ob_info}")
            print(f"    OF       : CVD={r.get('cvd_div',0)}pt  "
                  f"Vol={r.get('high_vol',0)}pt  "
                  f"Abs={r.get('absorption',0)}pt")
            print(f"    SMC      : OB={r.get('in_ob',0)}pt  "
                  f"FVG={r.get('in_fvg',0)}pt  "
                  f"Disc={r.get('discount',0)}pt")
            print(f"    Sweep    : {r.get('sweep',0)}pt  "
                  f"MSS: {r.get('mss',0)}pt")

            if r["status"] == "ENTRY":
                print(f"    {GN}→ Buscá entry en M5 con SL bajo el OB{RST}")
            else:
                missing = 8 - r["total"]
                print(f"    {YW}→ Faltan ~{missing} puntos para señal completa{RST}")
        print()

    # ── LEYENDA ─────────────────────────────────────────────
    print(DM +
          "  CVD=Order Flow  OB=Order Block  FVG=Imbalance  "
          "SWP=Stop Hunt  MSS=Estructura" + RST)

# =============================================================
# LOOP PRINCIPAL
# =============================================================

def main():
    print(CY + "\n  🐋 Whale Tracker iniciando...\n" + RST)

    # Verificar tickers
    if not TICKERS:
        print(RD + "  ✗ Sin tickers configurados. Corré: python setup_console.py\n" + RST)
        sys.exit(1)

    print(f"  Tickers  : {WH}{', '.join(TICKERS)}{RST}")
    print(f"  Timeframe: {WH}{TIMEFRAME}{RST}")
    print(f"  Período  : {WH}{PERIOD}{RST}")
    print(f"  Señal en : {WH}{ENGINE.get('signal_threshold', 8)}/13 pts{RST}")
    print(f"  Update   : cada {WH}{UPDATE_INTERVAL}s{RST}")
    print(f"\n  {DM}Cargando datos iniciales...{RST}\n")

    # Inicializar un engine por ticker
    for ticker in TICKERS:
        engines[ticker] = WhaleEngine(
            ticker    = ticker,
            timeframe = TIMEFRAME,
            period    = PERIOD,
            params    = ENGINE,
        )

    cycle       = 0
    last_update = 0

    try:
        while True:
            now = time.time()

            # ── Actualizar cuando toca ──────────────────────
            if now - last_update >= UPDATE_INTERVAL or cycle == 0:
                cycle      += 1
                last_update = now

                # Correr todos los engines en paralelo (threads)
                with ThreadPoolExecutor(max_workers=min(len(TICKERS), 5)) as executor:
                    futures = {
                        executor.submit(analyze_ticker, t): t
                        for t in TICKERS
                    }
                    for future in as_completed(futures):
                        ticker, result, error = future.result()
                        with lock:
                            if result:
                                # ¿Señal nueva?
                                prev_status = results.get(ticker, {}).get("status", "")
                                results[ticker] = result
                                errors.pop(ticker, None)
                                # Log si es señal nueva
                                if (result["status"] in ("ENTRY", "SETUP") and
                                        result["status"] != prev_status):
                                    log_signal(ticker, result)
                                    # Sonido en Windows
                                    if ALERTS.get("sound") and result["status"] == "ENTRY":
                                        try:
                                            import winsound
                                            winsound.Beep(800, 400)
                                            winsound.Beep(1000, 300)
                                        except Exception:
                                            print("\a", end="", flush=True)
                            else:
                                errors[ticker] = error or "Error desconocido"

            # ── Renderizar pantalla ─────────────────────────
            elapsed     = time.time() - last_update
            next_update = max(0, int(UPDATE_INTERVAL - elapsed))
            render_screen(cycle, elapsed, next_update)

            # Esperar 5s antes de refrescar la pantalla
            time.sleep(5)

    except KeyboardInterrupt:
        clear()
        print(CY + "\n  🐋 Whale Tracker detenido.\n" + RST)

        if signal_history:
            print(f"  {WH}Señales registradas en esta sesión:{RST}")
            for s in signal_history[-10:]:
                col = GN if "ENTRY" in s["status"] else YW
                print(f"  {col}{s['timestamp']}  {s['ticker']:<8}  "
                      f"{s['status']:<16}  Score {s['score']}/13{RST}")
            if ALERTS.get("log_file"):
                print(f"\n  {DM}Historial completo guardado en: signals_log.csv{RST}")

        print()
        sys.exit(0)

# =============================================================
# PUNTO DE ENTRADA
# =============================================================

if __name__ == "__main__":
    main()
