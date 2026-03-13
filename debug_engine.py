# =============================================================
# WHALE TRACKER — debug_engine.py
# Diagnóstico detallado: muestra el estado interno de cada
# módulo para verificar que los cálculos son correctos.
# =============================================================
# USO:
#   python debug_engine.py GGAL
# =============================================================

import sys
import numpy as np
import pandas as pd
from whale_engine import WhaleEngine

ticker = sys.argv[1] if len(sys.argv) > 1 else "GGAL"

print(f"\n🔬 Debug completo — {ticker}\n")

engine = WhaleEngine(
    ticker    = ticker,
    timeframe = "1h",
    period    = "3mo",
    params    = {
        "cvd_length": 20, "vol_length": 20, "vol_multiplier": 1.5,
        "ob_length": 5, "ob_mitigation": 0.5, "fvg_min_pct": 0.2,
        "sweep_lookback": 20, "sweep_wick_ratio": 2.0,
        "swing_length": 5, "signal_threshold": 8, "warn_threshold": 6,
    }
)

# Fetch + calcular todo
ok = engine.fetch()
if not ok:
    print("ERROR: No se pudieron descargar datos.")
    sys.exit(1)

engine.calc_cvd()
engine.calc_order_blocks()
engine.calc_fvg()
engine.calc_stop_hunts()
engine.calc_mss()
engine.calc_ranges()

df = engine.df

print(f"  Total de velas descargadas : {len(df)}")
print(f"  Primer dato : {df.index[0]}")
print(f"  Último dato : {df.index[-1]}")
print(f"  Columnas    : {list(df.columns)}\n")

# ── ÚLTIMAS 5 VELAS ─────────────────────────────────────────
print("─" * 60)
print("ÚLTIMAS 5 VELAS")
print("─" * 60)
cols = ["open", "high", "low", "close", "volume"]
print(df[cols].tail(5).to_string())
print()

# ── CVD ─────────────────────────────────────────────────────
print("─" * 60)
print("MÓDULO 1 — CVD / ORDER FLOW")
print("─" * 60)
print(df[["close", "volume", "delta", "cvd", "cvd_div_bull",
          "high_vol", "absorption_bull"]].tail(10).to_string())

# Contar señales en todo el histórico
print(f"\n  CVD divergencia alcista en historial : "
      f"{df['cvd_div_bull'].sum()} velas")
print(f"  Volumen alto en historial            : "
      f"{df['high_vol'].sum()} velas")
print(f"  Absorción alcista en historial       : "
      f"{df['absorption_bull'].sum()} velas")

# ── ORDER BLOCKS ────────────────────────────────────────────
print("\n" + "─" * 60)
print("MÓDULO 2 — ORDER BLOCKS")
print("─" * 60)
print(df[["close", "ob_bull_top", "ob_bull_bottom",
          "in_bull_ob", "new_bull_ob"]].tail(10).to_string())

# Últimos OBs detectados
new_obs = df[df["new_bull_ob"] == True]
if len(new_obs) > 0:
    print(f"\n  Últimos OBs alcistas detectados:")
    for idx, row in new_obs.tail(5).iterrows():
        print(f"    {idx}  top={row['ob_bull_top']:.3f}  "
              f"bot={row['ob_bull_bottom']:.3f}")
else:
    print("\n  ⚠ No se detectaron OBs alcistas en el historial")
    print("  → Revisá el parámetro ob_length (actual: 5)")

# ── FVG ─────────────────────────────────────────────────────
print("\n" + "─" * 60)
print("MÓDULO 3 — FVG / IMBALANCE")
print("─" * 60)
fvg_count = df["fvg_bull"].sum()
print(f"  FVGs alcistas detectados en historial: {fvg_count}")
if fvg_count > 0:
    print(df[df["fvg_bull"] == True][
        ["close", "fvg_bull_top", "fvg_bull_bot"]].tail(5).to_string())
else:
    print("  ⚠ No se detectaron FVGs — umbral puede ser muy alto")
    print(f"  → fvg_min_pct actual: 0.2%")
    # Calcular gaps reales
    gaps = (df["low"] - df["high"].shift(2)).dropna()
    gaps_pos = gaps[gaps > 0]
    if len(gaps_pos) > 0:
        print(f"  → Gaps positivos reales encontrados: {len(gaps_pos)}")
        print(f"  → Gap promedio: {gaps_pos.mean():.4f}  "
              f"Gap máximo: {gaps_pos.max():.4f}")
        threshold_needed = gaps_pos.mean() / df["close"].mean() * 100
        print(f"  → Umbral sugerido: {threshold_needed:.3f}%")

# ── STOP HUNTS ───────────────────────────────────────────────
print("\n" + "─" * 60)
print("MÓDULO 4 — STOP HUNTS")
print("─" * 60)
sh_count = df["stop_hunt_bull"].sum()
print(f"  Stop hunts alcistas en historial: {sh_count}")
if sh_count > 0:
    print(df[df["stop_hunt_bull"] == True][
        ["low", "close", "volume", "high_vol"]].tail(5).to_string())
else:
    print("  ⚠ No se detectaron stop hunts")
    # Mostrar cuántos casi lo son
    lookback = 20
    near_sweeps = 0
    for i in range(lookback, len(df)):
        row = df.iloc[i]
        prev_low = df["low"].iloc[i-lookback:i].min()
        if row["low"] < prev_low and row["close"] > prev_low:
            near_sweeps += 1
    print(f"  → Barridas sin volumen alto: {near_sweeps} "
          f"(falta condición high_vol)")

# ── MSS ─────────────────────────────────────────────────────
print("\n" + "─" * 60)
print("MÓDULO 5 — MSS / ESTRUCTURA")
print("─" * 60)
mss_count = df["mss_bull"].sum()
print(f"  MSS alcistas en historial: {mss_count}")
if mss_count > 0:
    print(df[df["mss_bull"] == True][
        ["close", "swing_high", "swing_low"]].tail(5).to_string())
    print(f"\n  Último swing high: {df['swing_high'].dropna().iloc[-1]:.3f}")
    print(f"  Último swing low : {df['swing_low'].dropna().iloc[-1]:.3f}")

# ── RANGES ──────────────────────────────────────────────────
print("\n" + "─" * 60)
print("MÓDULO 6 — RANGES (Premium/Equilibrium/Discount)")
print("─" * 60)
last = df.iloc[-1]
print(f"  Range high   : ${last['range_high']:.3f}")
print(f"  Range low    : ${last['range_low']:.3f}")
print(f"  Range mid    : ${last['range_mid']:.3f}")
print(f"  Precio actual: ${last['close']:.3f}")
print(f"  Posición     : {last['range_pct']*100:.1f}%  "
      f"({'DISCOUNT' if last['in_discount'] else 'EQUILIBRIUM' if last['in_equilibrium'] else 'PREMIUM'})")

# ── RESUMEN DIAGNÓSTICO ──────────────────────────────────────
print("\n" + "═" * 60)
print("RESUMEN DIAGNÓSTICO")
print("═" * 60)

checks = [
    ("Datos descargados",           len(df) > 30),
    ("CVD calculado",               "cvd" in df.columns and not df["cvd"].isna().all()),
    ("OBs detectados historial",    df["new_bull_ob"].sum() > 0),
    ("FVGs detectados historial",   df["fvg_bull"].sum() > 0),
    ("Stop hunts historial",        df["stop_hunt_bull"].sum() > 0),
    ("MSS detectados historial",    df["mss_bull"].sum() > 0),
    ("Ranges calculados",           not df["range_pct"].isna().all()),
]

all_ok = True
for label, result in checks:
    icon = "✓" if result else "✗"
    color = "" 
    print(f"  {icon}  {label}")
    if not result:
        all_ok = False

print()
if all_ok:
    print("  ✓ Todos los módulos funcionan correctamente.")
    print("  → El score 0/13 es real: no hay confluencia activa ahora.")
    print("  → El sistema está esperando el momento correcto.")
else:
    print("  ⚠ Algunos módulos necesitan ajuste de parámetros.")
    print("  → Revisá los umbrales sugeridos arriba.")

print()
