# =============================================================
# WHALE TRACKER — whale_engine.py
# Motor de cálculo: descarga datos y calcula todos los
# indicadores SMC + Order Flow automáticamente.
# =============================================================

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime

# =============================================================
# CLASE PRINCIPAL DEL ENGINE
# =============================================================

class WhaleEngine:
    """
    Descarga datos de yfinance y calcula:
      - CVD (Cumulative Volume Delta) y divergencias
      - Order Blocks alcistas y bajistas
      - FVG (Fair Value Gaps / Imbalances)
      - Stop Hunts (barridas de liquidez)
      - MSS (Market Structure Shifts)
      - Score de confluencia total (0-13)
    """

    def __init__(self, ticker: str, timeframe: str, period: str, params: dict):
        self.ticker    = ticker.upper()
        self.timeframe = timeframe
        self.period    = period
        self.params    = params
        self.df        = None       # DataFrame con datos + indicadores
        self.signals   = {}         # Señales de la última vela
        self.score     = 0          # Score total
        self.status    = "WAITING"  # WAITING / WATCH / SETUP / ENTRY
        self.last_update = None

    # ----------------------------------------------------------
    # DESCARGA DE DATOS
    # ----------------------------------------------------------

    def fetch(self) -> bool:
        """Descarga datos OHLCV de yfinance. Retorna True si ok."""
        try:
            ticker_obj = yf.Ticker(self.ticker)
            df = ticker_obj.history(
                period=self.period,
                interval=self.timeframe,
                auto_adjust=True,
                prepost=False,
            )
            if df.empty or len(df) < 30:
                return False

            df.index = pd.to_datetime(df.index)
            df.columns = [c.lower() for c in df.columns]
            df = df[["open", "high", "low", "close", "volume"]].copy()
            df.dropna(inplace=True)
            self.df = df
            self.last_update = datetime.now()
            return True

        except Exception as e:
            print(f"  [ERROR] {self.ticker} fetch: {e}")
            return False

    # ----------------------------------------------------------
    # MÓDULO 1: ORDER FLOW — CVD
    # ----------------------------------------------------------

    def calc_cvd(self):
        """
        CVD = Cumulative Volume Delta
        Aproximación: velas alcistas suman volumen, bajistas restan.
        Divergencia: precio baja pero CVD sube → acumulación institucional.
        """
        df = self.df
        n  = self.params.get("cvd_length", 20)

        # Delta por vela
        df["bull_vol"] = np.where(df["close"] > df["open"], df["volume"],
                         np.where(df["close"] == df["open"], df["volume"] * 0.5, 0.0))
        df["bear_vol"] = np.where(df["close"] < df["open"], df["volume"],
                         np.where(df["close"] == df["open"], df["volume"] * 0.5, 0.0))
        df["delta"]    = df["bull_vol"] - df["bear_vol"]

        # CVD suavizado (media móvil del delta)
        df["cvd"]      = df["delta"].rolling(n).mean()

        # Tendencia precio y CVD en ventana n
        df["price_trend"] = df["close"].rolling(n).mean()
        df["cvd_trend"]   = df["cvd"].rolling(3).mean()

        # Divergencia alcista: precio baja pero CVD sube
        price_falling = df["price_trend"] < df["price_trend"].shift(3)
        cvd_rising    = df["cvd_trend"]   > df["cvd_trend"].shift(3)
        df["cvd_div_bull"] = price_falling & cvd_rising

        # Divergencia bajista: precio sube pero CVD baja
        price_rising   = df["price_trend"] > df["price_trend"].shift(3)
        cvd_falling    = df["cvd_trend"]   < df["cvd_trend"].shift(3)
        df["cvd_div_bear"] = price_rising & cvd_falling

        # Volumen alto
        vol_mult = self.params.get("vol_multiplier", 1.5)
        vol_len  = self.params.get("vol_length", 20)
        df["avg_vol"]   = df["volume"].rolling(vol_len).mean()
        df["high_vol"]  = df["volume"] > df["avg_vol"] * vol_mult

        # Absorción: wick largo con volumen alto
        df["body"]      = (df["close"] - df["open"]).abs()
        df["wick_low"]  = df[["open", "close"]].min(axis=1) - df["low"]
        df["wick_high"] = df["high"] - df[["open", "close"]].max(axis=1)
        wick_ratio      = self.params.get("sweep_wick_ratio", 2.0)
        df["absorption_bull"] = (df["wick_low"]  > df["body"] * wick_ratio) & df["high_vol"]
        df["absorption_bear"] = (df["wick_high"] > df["body"] * wick_ratio) & df["high_vol"]

        self.df = df

    # ----------------------------------------------------------
    # MÓDULO 2: ORDER BLOCKS
    # ----------------------------------------------------------

    def calc_order_blocks(self):
        """
        OB alcista: última vela bajista antes de impulso alcista fuerte.
        OB bajista: última vela alcista antes de impulso bajista fuerte.
        Precio dentro del OB = zona institucional activa.
        """
        df  = self.df
        n   = self.params.get("ob_length", 5)
        mit = self.params.get("ob_mitigation", 0.5)

        ob_bull_top    = []
        ob_bull_bottom = []
        ob_bear_top    = []
        ob_bear_bottom = []
        in_bull_ob     = []
        in_bear_ob     = []
        new_bull_ob    = []
        new_bear_ob    = []

        last_bull_top = last_bull_bot = np.nan
        last_bear_top = last_bear_bot = np.nan

        for i in range(len(df)):
            if i < n + 1:
                ob_bull_top.append(np.nan)
                ob_bull_bottom.append(np.nan)
                ob_bear_top.append(np.nan)
                ob_bear_bottom.append(np.nan)
                in_bull_ob.append(False)
                in_bear_ob.append(False)
                new_bull_ob.append(False)
                new_bear_ob.append(False)
                continue

            row   = df.iloc[i]
            prev  = df.iloc[i - n]

            # OB alcista: vela n periodos atrás era bajista y ahora rompemos su máximo
            if prev["close"] < prev["open"] and row["close"] > prev["high"]:
                last_bull_top = prev["high"]
                last_bull_bot = prev["low"]
                new_bull_ob.append(True)
            else:
                new_bull_ob.append(False)

            # OB bajista: vela n periodos atrás era alcista y ahora rompemos su mínimo
            if prev["close"] > prev["open"] and row["close"] < prev["low"]:
                last_bear_top = prev["high"]
                last_bear_bot = prev["low"]
                new_bear_ob.append(True)
            else:
                new_bear_ob.append(False)

            # Invalidar OB si precio lo penetra más del % de mitigación
            if not np.isnan(last_bull_top):
                ob_range   = last_bull_top - last_bull_bot
                mitig_line = last_bull_top - ob_range * mit
                if row["close"] < mitig_line:
                    last_bull_top = last_bull_bot = np.nan

            if not np.isnan(last_bear_top):
                ob_range   = last_bear_top - last_bear_bot
                mitig_line = last_bear_bot + ob_range * mit
                if row["close"] > mitig_line:
                    last_bear_top = last_bear_bot = np.nan

            ob_bull_top.append(last_bull_top)
            ob_bull_bottom.append(last_bull_bot)
            ob_bear_top.append(last_bear_top)
            ob_bear_bottom.append(last_bear_bot)

            # ¿Precio tocando/dentro del OB alcista?
            if not np.isnan(last_bull_top):
                price = row["close"]
                in_bull_ob.append(last_bull_bot <= price <= last_bull_top * 1.005)
            else:
                in_bull_ob.append(False)

            if not np.isnan(last_bear_top):
                price = row["close"]
                in_bear_ob.append(last_bear_bot * 0.995 <= price <= last_bear_top)
            else:
                in_bear_ob.append(False)

        df["ob_bull_top"]    = ob_bull_top
        df["ob_bull_bottom"] = ob_bull_bottom
        df["ob_bear_top"]    = ob_bear_top
        df["ob_bear_bottom"] = ob_bear_bottom
        df["in_bull_ob"]     = in_bull_ob
        df["in_bear_ob"]     = in_bear_ob
        df["new_bull_ob"]    = new_bull_ob
        df["new_bear_ob"]    = new_bear_ob

        self.df = df

    # ----------------------------------------------------------
    # MÓDULO 3: FAIR VALUE GAPS (FVG)
    # ----------------------------------------------------------

    def calc_fvg(self):
        """
        FVG alcista: gap entre high[i-2] y low[i] — precio se movió
        tan rápido que dejó un hueco sin negociación.
        Esos huecos actúan como imanes de precio.
        """
        df        = self.df
        min_pct   = self.params.get("fvg_min_pct", 0.2) / 100

        fvg_bull      = []
        fvg_bear      = []
        in_fvg_bull   = []
        in_fvg_bear   = []
        fvg_bull_top  = []
        fvg_bull_bot  = []
        fvg_bear_top  = []
        fvg_bear_bot  = []

        last_fvg_bull_top = last_fvg_bull_bot = np.nan
        last_fvg_bear_top = last_fvg_bear_bot = np.nan

        for i in range(len(df)):
            if i < 2:
                fvg_bull.append(False); fvg_bear.append(False)
                in_fvg_bull.append(False); in_fvg_bear.append(False)
                fvg_bull_top.append(np.nan); fvg_bull_bot.append(np.nan)
                fvg_bear_top.append(np.nan); fvg_bear_bot.append(np.nan)
                continue

            curr = df.iloc[i]
            prev2 = df.iloc[i - 2]
            threshold = curr["close"] * min_pct

            # FVG alcista: low actual > high de hace 2 velas
            is_fvg_bull = curr["low"] > prev2["high"] + threshold
            # FVG bajista: high actual < low de hace 2 velas
            is_fvg_bear = curr["high"] < prev2["low"] - threshold

            if is_fvg_bull:
                last_fvg_bull_top = curr["low"]
                last_fvg_bull_bot = prev2["high"]

            if is_fvg_bear:
                last_fvg_bear_top = prev2["low"]
                last_fvg_bear_bot = curr["high"]

            # Invalidar si precio lo rellena
            if not np.isnan(last_fvg_bull_top) and curr["close"] < last_fvg_bull_bot:
                last_fvg_bull_top = last_fvg_bull_bot = np.nan
            if not np.isnan(last_fvg_bear_top) and curr["close"] > last_fvg_bear_top:
                last_fvg_bear_top = last_fvg_bear_bot = np.nan

            fvg_bull.append(is_fvg_bull)
            fvg_bear.append(is_fvg_bear)
            fvg_bull_top.append(last_fvg_bull_top)
            fvg_bull_bot.append(last_fvg_bull_bot)
            fvg_bear_top.append(last_fvg_bear_top)
            fvg_bear_bot.append(last_fvg_bear_bot)

            # ¿Precio en zona FVG?
            p = curr["close"]
            in_fvg_bull.append(
                not np.isnan(last_fvg_bull_top) and last_fvg_bull_bot <= p <= last_fvg_bull_top
            )
            in_fvg_bear.append(
                not np.isnan(last_fvg_bear_top) and last_fvg_bear_bot <= p <= last_fvg_bear_top
            )

        df["fvg_bull"]      = fvg_bull
        df["fvg_bear"]      = fvg_bear
        df["in_fvg_bull"]   = in_fvg_bull
        df["in_fvg_bear"]   = in_fvg_bear
        df["fvg_bull_top"]  = fvg_bull_top
        df["fvg_bull_bot"]  = fvg_bull_bot
        df["fvg_bear_top"]  = fvg_bear_top
        df["fvg_bear_bot"]  = fvg_bear_bot

        self.df = df

    # ----------------------------------------------------------
    # MÓDULO 4: STOP HUNTS (barridas de liquidez)
    # ----------------------------------------------------------

    def calc_stop_hunts(self):
        """
        Stop hunt alcista: precio cae bajo mínimos previos con wick largo
        pero cierra arriba → trampa institucional, posible reversión.
        """
        df       = self.df
        lookback = self.params.get("sweep_lookback", 20)

        sh_bull = []
        sh_bear = []

        for i in range(len(df)):
            if i < lookback:
                sh_bull.append(False)
                sh_bear.append(False)
                continue

            row       = df.iloc[i]
            prev_low  = df["low"].iloc[i - lookback:i].min()
            prev_high = df["high"].iloc[i - lookback:i].max()
            high_vol  = row["high_vol"] if "high_vol" in df.columns else False

            # Stop hunt alcista: wick barre mínimos previos pero cierra arriba
            bull = (row["low"] < prev_low) and (row["close"] > prev_low) and high_vol
            # Stop hunt bajista: wick barre máximos previos pero cierra abajo
            bear = (row["high"] > prev_high) and (row["close"] < prev_high) and high_vol

            sh_bull.append(bool(bull))
            sh_bear.append(bool(bear))

        df["stop_hunt_bull"] = sh_bull
        df["stop_hunt_bear"] = sh_bear
        self.df = df

    # ----------------------------------------------------------
    # MÓDULO 5: MARKET STRUCTURE SHIFT (MSS)
    # ----------------------------------------------------------

    def calc_mss(self):
        """
        MSS alcista: precio cierra por encima del último swing high.
        Indica que la estructura cambió de bajista a alcista.
        Es el trigger de entry más fiable en SMC.
        """
        df  = self.df
        n   = self.params.get("swing_length", 5)

        swing_highs = []
        swing_lows  = []
        mss_bull    = []
        mss_bear    = []
        last_sh     = np.nan
        last_sl     = np.nan

        for i in range(len(df)):
            # Detectar pivot high/low (precio más alto/bajo en ventana n)
            if i >= n * 2:
                window_h = df["high"].iloc[i - n * 2:i]
                window_l = df["low"].iloc[i - n * 2:i]
                mid_h    = df["high"].iloc[i - n]
                mid_l    = df["low"].iloc[i - n]

                if mid_h == window_h.max():
                    last_sh = mid_h
                if mid_l == window_l.min():
                    last_sl = mid_l

            swing_highs.append(last_sh)
            swing_lows.append(last_sl)

            if i == 0:
                mss_bull.append(False)
                mss_bear.append(False)
                continue

            row  = df.iloc[i]
            prev = df.iloc[i - 1]

            # MSS alcista: cierre cruza swing high por primera vez
            bull = (not np.isnan(last_sh) and
                    row["close"] > last_sh and
                    prev["close"] <= last_sh)

            # MSS bajista: cierre cruza swing low por primera vez
            bear = (not np.isnan(last_sl) and
                    row["close"] < last_sl and
                    prev["close"] >= last_sl)

            mss_bull.append(bool(bull))
            mss_bear.append(bool(bear))

        df["swing_high"] = swing_highs
        df["swing_low"]  = swing_lows
        df["mss_bull"]   = mss_bull
        df["mss_bear"]   = mss_bear
        self.df = df

    # ----------------------------------------------------------
    # MÓDULO 6: EQUILIBRIUM / PREMIUM / DISCOUNT
    # ----------------------------------------------------------

    def calc_ranges(self):
        """
        Calcula el rango de la estructura actual y divide en:
        - Premium (>50%): zona cara, vender
        - Equilibrium (50%): zona neutra
        - Discount (<50%): zona barata, comprar
        """
        df = self.df
        n  = 50  # lookback para calcular el rango

        df["range_high"] = df["high"].rolling(n).max()
        df["range_low"]  = df["low"].rolling(n).min()
        df["range_mid"]  = (df["range_high"] + df["range_low"]) / 2
        df["range_pct"]  = (df["close"] - df["range_low"]) / (df["range_high"] - df["range_low"] + 1e-10)

        df["in_discount"]   = df["range_pct"] < 0.45
        df["in_equilibrium"]= (df["range_pct"] >= 0.45) & (df["range_pct"] <= 0.55)
        df["in_premium"]    = df["range_pct"] > 0.55

        self.df = df

    # ----------------------------------------------------------
    # SCORE DE CONFLUENCIA
    # ----------------------------------------------------------

    def calc_score(self) -> dict:
        """
        Calcula el score total de confluencia en la última vela.
        Máximo: 13 puntos.

        Distribución:
          Order Flow  : 4 pts (CVD div +2, vol alto +1, absorción +1)
          SMC         : 5 pts (en OB +2, FVG +1, nuevo OB +1, discount +1)
          Stop Hunt   : 2 pts (+2 si hay barrida alcista)
          MSS         : 2 pts (+2 si hay quiebre estructural alcista)
        """
        df   = self.df
        last = df.iloc[-1]

        s = {}

        # --- Order Flow ---
        s["cvd_div"]     = int(bool(last.get("cvd_div_bull",     False))) * 2
        s["high_vol"]    = int(bool(last.get("high_vol",         False))) * 1
        s["absorption"]  = int(bool(last.get("absorption_bull",  False))) * 1
        s["score_of"]    = s["cvd_div"] + s["high_vol"] + s["absorption"]

        # --- SMC ---
        s["in_ob"]       = int(bool(last.get("in_bull_ob",      False))) * 2
        s["in_fvg"]      = int(bool(last.get("in_fvg_bull",     False))) * 1
        s["new_ob"]      = int(bool(last.get("new_bull_ob",     False))) * 1
        s["discount"]    = int(bool(last.get("in_discount",     False))) * 1
        s["score_smc"]   = s["in_ob"] + s["in_fvg"] + s["new_ob"] + s["discount"]

        # --- Stop Hunt ---
        s["sweep"]       = int(bool(last.get("stop_hunt_bull",  False))) * 2
        s["score_sweep"] = s["sweep"]

        # --- MSS / Entry ---
        s["mss"]         = int(bool(last.get("mss_bull",        False))) * 2
        s["score_entry"] = s["mss"]

        # --- Total ---
        s["total"]       = s["score_of"] + s["score_smc"] + s["score_sweep"] + s["score_entry"]
        s["pct"]         = round(s["total"] / 13 * 100, 1)

        # --- Precio actual ---
        s["price"]        = round(float(last["close"]), 4)
        s["range_pct"]    = round(float(last.get("range_pct", 0.5)) * 100, 1)
        s["ob_bull_top"]  = last.get("ob_bull_top",  np.nan)
        s["ob_bull_bot"]  = last.get("ob_bull_bottom", np.nan)

        # --- Status ---
        threshold = self.params.get("signal_threshold", 8)
        warn      = self.params.get("warn_threshold",   6)

        if s["total"] >= threshold:
            s["status"] = "ENTRY"
            s["emoji"]  = "🐋"
            s["label"]  = "WHALE ENTRY"
        elif s["total"] >= warn:
            s["status"] = "SETUP"
            s["emoji"]  = "⚡"
            s["label"]  = "SETUP"
        elif s["total"] >= 4:
            s["status"] = "WATCH"
            s["emoji"]  = "👀"
            s["label"]  = "ZONA INTERÉS"
        else:
            s["status"] = "WAITING"
            s["emoji"]  = "⏳"
            s["label"]  = "ESPERANDO"

        self.score   = s["total"]
        self.status  = s["status"]
        self.signals = s
        return s

    # ----------------------------------------------------------
    # MÉTODO PRINCIPAL: RUN
    # ----------------------------------------------------------

    def run(self) -> dict | None:
        """
        Ejecuta el pipeline completo:
        fetch → calcular todos los módulos → retornar signals.
        Retorna None si falla la descarga.
        """
        if not self.fetch():
            return None

        self.calc_cvd()
        self.calc_order_blocks()
        self.calc_fvg()
        self.calc_stop_hunts()
        self.calc_mss()
        self.calc_ranges()
        result = self.calc_score()
        return result

    # ----------------------------------------------------------
    # HELPERS PARA EL DASHBOARD
    # ----------------------------------------------------------

    def get_ob_zones(self) -> list[dict]:
        """Retorna los Order Blocks activos para dibujar en el gráfico."""
        df     = self.df
        zones  = []
        seen   = set()

        for i in range(len(df) - 1, max(len(df) - 200, 0), -1):
            row = df.iloc[i]

            if row["new_bull_ob"] and not np.isnan(row["ob_bull_top"]):
                key = round(row["ob_bull_top"], 4)
                if key not in seen:
                    seen.add(key)
                    zones.append({
                        "type":   "bull",
                        "top":    row["ob_bull_top"],
                        "bottom": row["ob_bull_bottom"],
                        "time":   df.index[i],
                    })

            if row["new_bear_ob"] and not np.isnan(row["ob_bear_top"]):
                key = round(row["ob_bear_top"], 4)
                if key not in seen:
                    seen.add(key)
                    zones.append({
                        "type":   "bear",
                        "top":    row["ob_bear_top"],
                        "bottom": row["ob_bear_bottom"],
                        "time":   df.index[i],
                    })

            if len(zones) >= 6:
                break

        return zones

    def get_fvg_zones(self) -> list[dict]:
        """Retorna los FVGs activos para dibujar en el gráfico."""
        df    = self.df
        zones = []
        seen  = set()

        for i in range(len(df) - 1, max(len(df) - 200, 0), -1):
            row = df.iloc[i]

            if row["fvg_bull"] and not np.isnan(row["fvg_bull_top"]):
                key = round(row["fvg_bull_top"], 4)
                if key not in seen:
                    seen.add(key)
                    zones.append({
                        "type":   "bull",
                        "top":    row["fvg_bull_top"],
                        "bottom": row["fvg_bull_bot"],
                        "time":   df.index[i],
                    })

            if row["fvg_bear"] and not np.isnan(row["fvg_bear_top"]):
                key = round(row["fvg_bear_top"], 4)
                if key not in seen:
                    seen.add(key)
                    zones.append({
                        "type":   "bear",
                        "top":    row["fvg_bear_top"],
                        "bottom": row["fvg_bear_bot"],
                        "time":   df.index[i],
                    })

            if len(zones) >= 6:
                break

        return zones

    def summary_line(self) -> str:
        """Una línea de resumen para la consola."""
        s = self.signals
        if not s:
            return f"{self.ticker:<8} {'—':>5}  ⏳ Sin datos"

        bar_len  = 12
        filled   = int(s["total"] / 13 * bar_len)
        bar      = "█" * filled + "░" * (bar_len - filled)

        return (
            f"{self.ticker:<8} "
            f"{s['total']:>2}/13  "
            f"[{bar}]  "
            f"{s['emoji']} {s['label']:<16} "
            f"${s['price']:.2f}  "
            f"Range: {s['range_pct']:.0f}%"
        )


# =============================================================
# FUNCIÓN DE CONVENIENCIA: analizar un solo ticker
# =============================================================

def analyze(ticker: str, timeframe: str = "1h",
            period: str = "3mo", params: dict = None) -> dict | None:
    """
    Función rápida para analizar un ticker desde la consola o Jupyter.

    Uso:
        from whale_engine import analyze
        result = analyze("GGAL")
        print(result)
    """
    if params is None:
        params = {
            "cvd_length": 20, "vol_length": 20, "vol_multiplier": 1.5,
            "ob_length": 5, "ob_mitigation": 0.5, "fvg_min_pct": 0.2,
            "sweep_lookback": 20, "sweep_wick_ratio": 2.0,
            "swing_length": 5, "signal_threshold": 8, "warn_threshold": 6,
        }
    engine = WhaleEngine(ticker, timeframe, period, params)
    return engine.run()


# =============================================================
# TEST RÁPIDO (correr directamente: python whale_engine.py)
# =============================================================

if __name__ == "__main__":
    import sys

    ticker = sys.argv[1] if len(sys.argv) > 1 else "GGAL"
    print(f"\n🐋 Whale Engine — test rápido: {ticker}\n")

    result = analyze(ticker)

    if result:
        print(f"  Precio       : ${result['price']}")
        print(f"  Score total  : {result['total']}/13  ({result['pct']}%)")
        print(f"  Status       : {result['emoji']} {result['label']}")
        print(f"  Range pos.   : {result['range_pct']}%")
        print(f"\n  Detalle:")
        print(f"    Order Flow : {result['score_of']}/4"
              f"  (CVD:{result['cvd_div']} Vol:{result['high_vol']} Abs:{result['absorption']})")
        print(f"    SMC        : {result['score_smc']}/5"
              f"  (OB:{result['in_ob']} FVG:{result['in_fvg']} Disc:{result['discount']})")
        print(f"    Stop Hunt  : {result['score_sweep']}/2")
        print(f"    MSS Entry  : {result['score_entry']}/2")
    else:
        print("  Error al descargar datos. Verificá el ticker y la conexión.")
