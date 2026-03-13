# =============================================================
# WHALE TRACKER — dashboard.py
# Gráfico interactivo con velas japonesas, zonas SMC,
# score de confluencia y monitor multi-ticker en el browser.
# =============================================================
# CÓMO USAR:
#   python dashboard.py
#   → Abre automáticamente en http://localhost:8050
#   → En Codespaces: click en "Open in Browser" que aparece
# =============================================================

import sys
import threading
import time
from datetime import datetime

import pandas as pd
import numpy as np

try:
    import dash
    from dash import dcc, html, Input, Output, callback_context
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    print("\n  ⚠ Instalá las dependencias: pip install -r requirements.txt\n")
    sys.exit(1)

try:
    from config import TICKERS, TIMEFRAME, PERIOD, ENGINE, UPDATE_INTERVAL, DASHBOARD
except ImportError:
    print("\n  ⚠ No encontré config.py — corré: python setup_console.py\n")
    sys.exit(1)

from whale_engine import WhaleEngine

# =============================================================
# ESTADO GLOBAL
# =============================================================

engines: dict[str, WhaleEngine] = {
    t: WhaleEngine(t, TIMEFRAME, PERIOD, ENGINE) for t in TICKERS
}
cache:   dict[str, dict] = {}   # último resultado por ticker
lock = threading.Lock()

# =============================================================
# COLORES Y TEMA
# =============================================================

THEME = {
    "bg":       "#060a0f",
    "bg2":      "#0d1520",
    "bg3":      "#111d2e",
    "border":   "rgba(100,180,255,0.12)",
    "text":     "#e8f4ff",
    "text2":    "#7ba8c8",
    "text3":    "#4a7090",
    "accent":   "#00d4ff",
    "green":    "#00e5a0",
    "green2":   "#00a372",
    "red":      "#ff4466",
    "amber":    "#f0b429",
    "purple":   "#a855f7",
    "grid":     "rgba(100,180,255,0.05)",
    "up":       "#00e5a0",
    "down":     "#ff4466",
    "ob_bull":  "rgba(0,212,255,0.12)",
    "ob_bear":  "rgba(255,68,102,0.10)",
    "fvg_bull": "rgba(168,85,247,0.12)",
    "fvg_bear": "rgba(255,68,102,0.08)",
}

# =============================================================
# CONSTRUCCIÓN DEL GRÁFICO
# =============================================================

def build_chart(ticker: str) -> go.Figure:
    """Construye el gráfico completo para un ticker."""
    engine = engines[ticker]

    # Correr engine si no hay datos
    if engine.df is None:
        result = engine.run()
    else:
        result = engine.calc_score()

    df = engine.df
    if df is None or df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos disponibles",
                           xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False,
                           font=dict(color=THEME["text2"], size=16))
        fig.update_layout(paper_bgcolor=THEME["bg"], plot_bgcolor=THEME["bg2"])
        return fig

    # Limitar a las últimas N velas
    candles = DASHBOARD.get("candles", 120)
    df = df.tail(candles).copy()

    # ── FIGURA CON SUBPLOTS ──────────────────────────────────
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.65, 0.20, 0.15],
        subplot_titles=["", "", ""],
    )

    # ── VELAS JAPONESAS ─────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"], high=df["high"],
        low=df["low"],   close=df["close"],
        name="Precio",
        increasing=dict(line=dict(color=THEME["up"],   width=1),
                        fillcolor=THEME["up"]),
        decreasing=dict(line=dict(color=THEME["down"], width=1),
                        fillcolor=THEME["down"]),
        showlegend=False,
    ), row=1, col=1)

    # ── ZONAS ORDER BLOCK ────────────────────────────────────
    ob_zones = engine.get_ob_zones()
    for zone in ob_zones:
        color = THEME["ob_bull"] if zone["type"] == "bull" else THEME["ob_bear"]
        border = THEME["accent"] if zone["type"] == "bull" else THEME["red"]
        label  = f"OB {'▲' if zone['type'] == 'bull' else '▼'} {zone['top']:.2f}"

        fig.add_hrect(
            y0=zone["bottom"], y1=zone["top"],
            fillcolor=color,
            line=dict(color=border, width=0.8, dash="dot"),
            annotation_text=label,
            annotation=dict(
                font=dict(color=border, size=10),
                x=1.0, xanchor="right",
            ),
            row=1, col=1,
        )

    # ── ZONAS FVG ────────────────────────────────────────────
    fvg_zones = engine.get_fvg_zones()
    for zone in fvg_zones:
        color  = THEME["fvg_bull"] if zone["type"] == "bull" else THEME["fvg_bear"]
        border = THEME["purple"]   if zone["type"] == "bull" else THEME["red"]
        label  = f"FVG {zone['top']:.2f}"

        fig.add_hrect(
            y0=zone["bottom"], y1=zone["top"],
            fillcolor=color,
            line=dict(color=border, width=0.5, dash="dash"),
            annotation_text=label,
            annotation=dict(
                font=dict(color=border, size=9),
                x=0.01, xanchor="left",
            ),
            row=1, col=1,
        )

    # ── EQUILIBRIUM LINE ─────────────────────────────────────
    last = df.iloc[-1]
    if "range_mid" in df.columns and not np.isnan(last["range_mid"]):
        fig.add_hline(
            y=last["range_mid"],
            line=dict(color=THEME["amber"], width=1, dash="dot"),
            annotation_text=f"EQ {last['range_mid']:.2f}",
            annotation=dict(font=dict(color=THEME["amber"], size=10)),
            row=1, col=1,
        )

    # ── SWING HIGHS / LOWS ───────────────────────────────────
    if "swing_high" in df.columns:
        sh_points = df[df["swing_high"].notna() & 
                       (df["swing_high"] != df["swing_high"].shift(1))]
        if len(sh_points) > 0:
            fig.add_trace(go.Scatter(
                x=sh_points.index,
                y=sh_points["swing_high"],
                mode="markers",
                marker=dict(symbol="triangle-down", size=8,
                           color=THEME["red"], opacity=0.7),
                name="Swing High",
                showlegend=False,
            ), row=1, col=1)

    if "swing_low" in df.columns:
        sl_points = df[df["swing_low"].notna() & 
                       (df["swing_low"] != df["swing_low"].shift(1))]
        if len(sl_points) > 0:
            fig.add_trace(go.Scatter(
                x=sl_points.index,
                y=sl_points["swing_low"],
                mode="markers",
                marker=dict(symbol="triangle-up", size=8,
                           color=THEME["green"], opacity=0.7),
                name="Swing Low",
                showlegend=False,
            ), row=1, col=1)

    # ── SEÑALES MSS ──────────────────────────────────────────
    if "mss_bull" in df.columns:
        mss = df[df["mss_bull"] == True]
        if len(mss) > 0:
            fig.add_trace(go.Scatter(
                x=mss.index,
                y=mss["low"] * 0.998,
                mode="markers+text",
                marker=dict(symbol="arrow-up", size=14,
                           color=THEME["green"], line=dict(width=1)),
                text=["MSS↑"] * len(mss),
                textposition="bottom center",
                textfont=dict(color=THEME["green"], size=9),
                name="MSS ↑",
                showlegend=False,
            ), row=1, col=1)

    # ── STOP HUNTS ───────────────────────────────────────────
    if "stop_hunt_bull" in df.columns:
        sweeps = df[df["stop_hunt_bull"] == True]
        if len(sweeps) > 0:
            fig.add_trace(go.Scatter(
                x=sweeps.index,
                y=sweeps["low"] * 0.996,
                mode="markers+text",
                marker=dict(symbol="star", size=12,
                           color=THEME["amber"],
                           line=dict(color=THEME["amber"], width=1)),
                text=["🎣"] * len(sweeps),
                textposition="bottom center",
                textfont=dict(size=10),
                name="Stop Hunt",
                showlegend=False,
            ), row=1, col=1)

    # ── CVD (subplot 2) ──────────────────────────────────────
    if "cvd" in df.columns:
        cvd_colors = [THEME["green"] if v >= 0 else THEME["red"]
                      for v in df["cvd"].fillna(0)]
        fig.add_trace(go.Bar(
            x=df.index,
            y=df["cvd"],
            name="CVD",
            marker=dict(color=cvd_colors, opacity=0.7),
            showlegend=False,
        ), row=2, col=1)

        # Marcar divergencias
        if "cvd_div_bull" in df.columns:
            divs = df[df["cvd_div_bull"] == True]
            if len(divs) > 0:
                fig.add_trace(go.Scatter(
                    x=divs.index,
                    y=divs["cvd"],
                    mode="markers",
                    marker=dict(symbol="circle", size=8,
                               color=THEME["amber"],
                               line=dict(color=THEME["amber"], width=1)),
                    name="CVD Div",
                    showlegend=False,
                ), row=2, col=1)

    # ── VOLUMEN (subplot 3) ──────────────────────────────────
    if "volume" in df.columns:
        vol_colors = [THEME["green"] if c >= o else THEME["down"]
                      for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(
            x=df.index,
            y=df["volume"],
            name="Volumen",
            marker=dict(color=vol_colors, opacity=0.6),
            showlegend=False,
        ), row=3, col=1)

        # Línea de volumen promedio
        if "avg_vol" in df.columns:
            fig.add_trace(go.Scatter(
                x=df.index,
                y=df["avg_vol"],
                line=dict(color=THEME["amber"], width=1, dash="dot"),
                name="Vol. Promedio",
                showlegend=False,
            ), row=3, col=1)

    # ── LAYOUT ───────────────────────────────────────────────
    score  = result.get("total", 0) if result else 0
    status = result.get("label", "ESPERANDO") if result else "ESPERANDO"
    price  = result.get("price", 0) if result else 0
    rng    = result.get("range_pct", 50) if result else 50

    title_color = (THEME["green"] if score >= ENGINE.get("signal_threshold", 8)
                   else THEME["amber"] if score >= ENGINE.get("warn_threshold", 6)
                   else THEME["text2"])

    fig.update_layout(
        title=dict(
            text=(f"<b>{ticker}</b>  ·  ${price:.2f}  ·  "
                  f"Score: <span style='color:{title_color}'>{score}/13</span>  ·  "
                  f"{status}  ·  Range: {rng:.0f}%  ·  "
                  f"TF: {TIMEFRAME}  ·  "
                  f"{datetime.now().strftime('%H:%M:%S')}"),
            font=dict(color=THEME["text"], size=13),
            x=0.01,
        ),
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["bg2"],
        font=dict(color=THEME["text2"], family="monospace", size=11),
        margin=dict(l=60, r=120, t=50, b=20),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor=THEME["bg3"],
            font=dict(color=THEME["text"], size=11),
        ),
    )

    # Ejes
    for i in range(1, 4):
        fig.update_xaxes(
            gridcolor=THEME["grid"],
            linecolor=THEME["border"],
            showgrid=True, row=i, col=1,
        )
        fig.update_yaxes(
            gridcolor=THEME["grid"],
            linecolor=THEME["border"],
            showgrid=True, row=i, col=1,
        )

    # Labels subplots
    fig.update_yaxes(title_text="Precio",  title_font=dict(size=10), row=1, col=1)
    fig.update_yaxes(title_text="CVD",     title_font=dict(size=10), row=2, col=1)
    fig.update_yaxes(title_text="Volumen", title_font=dict(size=10), row=3, col=1)

    return fig


# =============================================================
# TARJETA DE SCORE PARA UN TICKER
# =============================================================

def score_card(ticker: str, result: dict | None) -> html.Div:
    """Genera la tarjeta visual de score para la barra lateral."""
    if not result:
        return html.Div([
            html.Div(ticker, className="card-ticker"),
            html.Div("Cargando...", style={"color": THEME["text3"],
                                           "fontSize": "11px"}),
        ], style={
            "background": THEME["bg3"],
            "border": f"1px solid {THEME['border']}",
            "borderRadius": "10px",
            "padding": "10px 14px",
            "marginBottom": "8px",
            "cursor": "pointer",
        })

    score  = result.get("total", 0)
    status = result.get("status", "WAITING")
    label  = result.get("label",  "ESPERANDO")
    emoji  = result.get("emoji",  "⏳")
    price  = result.get("price",  0)
    pct    = score / 13 * 100

    border_color = (THEME["green"]  if status == "ENTRY"
               else THEME["amber"]  if status == "SETUP"
               else THEME["accent"] if status == "WATCH"
               else THEME["border"])

    score_color = (THEME["green"]  if status == "ENTRY"
              else THEME["amber"]  if status == "SETUP"
              else THEME["accent"] if status == "WATCH"
              else THEME["text3"])

    # Mini barra de score
    bar_filled = f"{pct:.0f}%"

    return html.Div([
        html.Div([
            html.Span(ticker, style={
                "fontWeight": "700", "fontSize": "14px",
                "color": THEME["text"], "fontFamily": "monospace",
            }),
            html.Span(f"${price:.2f}", style={
                "fontSize": "11px", "color": THEME["text3"],
                "fontFamily": "monospace", "float": "right",
            }),
        ]),
        html.Div([
            # Barra de score
            html.Div(style={
                "background": THEME["bg"],
                "borderRadius": "3px",
                "height": "4px",
                "marginTop": "6px",
                "marginBottom": "6px",
                "overflow": "hidden",
            }, children=[
                html.Div(style={
                    "width": bar_filled,
                    "height": "100%",
                    "background": score_color,
                    "borderRadius": "3px",
                    "transition": "width 0.5s",
                })
            ]),
        ]),
        html.Div([
            html.Span(f"{emoji} {label}", style={
                "fontSize": "11px", "color": score_color, "fontWeight": "600",
            }),
            html.Span(f"{score}/13", style={
                "fontSize": "11px", "color": score_color,
                "fontFamily": "monospace", "float": "right",
            }),
        ]),
    ], style={
        "background": THEME["bg3"],
        "border": f"1px solid {border_color}",
        "borderRadius": "10px",
        "padding": "10px 14px",
        "marginBottom": "8px",
        "cursor": "pointer",
        "transition": "border-color 0.3s",
    }, id=f"card-{ticker}")


# =============================================================
# LAYOUT DE LA APP
# =============================================================

app = dash.Dash(
    __name__,
    title="🐋 Whale Tracker",
    update_title=None,
)

app.layout = html.Div(style={
    "background": THEME["bg"],
    "minHeight":  "100vh",
    "fontFamily": "'Space Grotesk', monospace",
    "color":       THEME["text"],
}, children=[

    # ── HEADER ──────────────────────────────────────────────
    html.Div(style={
        "background":   THEME["bg2"],
        "borderBottom": f"1px solid {THEME['border']}",
        "padding":      "14px 24px",
        "display":      "flex",
        "alignItems":   "center",
        "justifyContent": "space-between",
    }, children=[
        html.Div([
            html.Span("🐋 ", style={"fontSize": "22px"}),
            html.Span("WHALE TRACKER", style={
                "fontSize": "18px", "fontWeight": "700",
                "color": THEME["accent"], "letterSpacing": "0.05em",
            }),
            html.Span(" — SMC Confluence Engine", style={
                "fontSize": "12px", "color": THEME["text3"],
                "marginLeft": "10px",
            }),
        ]),
        html.Div(id="header-time", style={
            "fontSize": "12px", "color": THEME["text3"],
            "fontFamily": "monospace",
        }),
    ]),

    # ── BODY ────────────────────────────────────────────────
    html.Div(style={
        "display": "flex",
        "height":  "calc(100vh - 56px)",
    }, children=[

        # ── SIDEBAR IZQUIERDO ────────────────────────────────
        html.Div(style={
            "width":      "220px",
            "minWidth":   "220px",
            "background": THEME["bg2"],
            "borderRight": f"1px solid {THEME['border']}",
            "padding":    "14px 12px",
            "overflowY":  "auto",
        }, children=[
            html.Div("ACTIVOS", style={
                "fontSize": "10px", "color": THEME["text3"],
                "letterSpacing": "0.1em", "marginBottom": "12px",
                "fontFamily": "monospace",
            }),
            html.Div(id="sidebar-cards"),
        ]),

        # ── GRÁFICO PRINCIPAL ────────────────────────────────
        html.Div(style={"flex": "1", "padding": "12px", "overflow": "hidden"},
        children=[
            dcc.Graph(
                id="main-chart",
                style={"height": "100%"},
                config={
                    "displayModeBar": True,
                    "modeBarButtonsToRemove": ["lasso2d", "select2d"],
                    "displaylogo": False,
                    "scrollZoom": True,
                },
            ),
        ]),

        # ── PANEL DERECHO — DETALLE ──────────────────────────
        html.Div(style={
            "width":      "200px",
            "minWidth":   "200px",
            "background": THEME["bg2"],
            "borderLeft":  f"1px solid {THEME['border']}",
            "padding":    "14px 12px",
            "overflowY":  "auto",
        }, children=[
            html.Div("SEÑAL ACTIVA", style={
                "fontSize": "10px", "color": THEME["text3"],
                "letterSpacing": "0.1em", "marginBottom": "12px",
                "fontFamily": "monospace",
            }),
            html.Div(id="signal-detail"),
        ]),
    ]),

    # ── STORES Y TIMERS ─────────────────────────────────────
    dcc.Store(id="selected-ticker", data=TICKERS[0]),
    dcc.Store(id="results-store",   data={}),
    dcc.Interval(id="interval-fast", interval=5_000,    n_intervals=0),  # 5s → UI
    dcc.Interval(id="interval-data", interval=UPDATE_INTERVAL * 1000,
                 n_intervals=0),  # 60s → datos
])


# =============================================================
# CALLBACKS
# =============================================================

# ── Actualizar datos ─────────────────────────────────────────
@app.callback(
    Output("results-store", "data"),
    Input("interval-data", "n_intervals"),
    prevent_initial_call=False,
)
def update_data(n):
    """Corre todos los engines y guarda resultados."""
    new_results = {}
    for ticker in TICKERS:
        try:
            result = engines[ticker].run()
            if result:
                # Serializar (quitar NaN para JSON)
                clean = {k: (None if isinstance(v, float) and np.isnan(v) else v)
                         for k, v in result.items()}
                new_results[ticker] = clean
        except Exception as e:
            print(f"  [ERROR] {ticker}: {e}")
    return new_results


# ── Seleccionar ticker al hacer click en card ─────────────────
@app.callback(
    Output("selected-ticker", "data"),
    [Input(f"card-{t}", "n_clicks") for t in TICKERS],
    prevent_initial_call=True,
)
def select_ticker(*args):
    ctx = callback_context
    if not ctx.triggered:
        return TICKERS[0]
    triggered_id = ctx.triggered[0]["prop_id"].split(".")[0]
    ticker = triggered_id.replace("card-", "")
    return ticker if ticker in TICKERS else TICKERS[0]


# ── Actualizar gráfico principal ─────────────────────────────
@app.callback(
    Output("main-chart", "figure"),
    Input("selected-ticker", "data"),
    Input("interval-fast",   "n_intervals"),
)
def update_chart(ticker, n):
    return build_chart(ticker)


# ── Actualizar sidebar cards ──────────────────────────────────
@app.callback(
    Output("sidebar-cards", "children"),
    Input("results-store",  "data"),
    Input("selected-ticker","data"),
)
def update_sidebar(results, selected):
    cards = []
    # Ordenar por score
    sorted_tickers = sorted(
        TICKERS,
        key=lambda t: (results.get(t) or {}).get("total", -1),
        reverse=True,
    )
    for ticker in sorted_tickers:
        result = results.get(ticker)
        card   = score_card(ticker, result)
        # Highlight si está seleccionado
        if ticker == selected:
            card.style["border"] = f"1px solid {THEME['accent']}"
            card.style["background"] = THEME["bg"]
        cards.append(card)
    return cards


# ── Actualizar panel de detalle ───────────────────────────────
@app.callback(
    Output("signal-detail", "children"),
    Output("header-time",   "children"),
    Input("selected-ticker", "data"),
    Input("results-store",   "data"),
    Input("interval-fast",   "n_intervals"),
)
def update_detail(ticker, results, n):
    now_str = datetime.now().strftime("%H:%M:%S  ·  %d/%m/%Y")
    result  = (results or {}).get(ticker)

    if not result:
        return html.Div("Cargando datos...",
                        style={"color": THEME["text3"], "fontSize": "12px"}), now_str

    score  = result.get("total", 0)
    status = result.get("status", "WAITING")
    score_color = (THEME["green"]  if status == "ENTRY"
              else THEME["amber"]  if status == "SETUP"
              else THEME["accent"] if status == "WATCH"
              else THEME["text3"])

    def row(label, value, color=None):
        return html.Div([
            html.Span(label, style={
                "fontSize": "10px", "color": THEME["text3"],
                "display": "block", "marginTop": "8px",
                "fontFamily": "monospace", "letterSpacing": "0.05em",
            }),
            html.Span(str(value), style={
                "fontSize": "13px", "fontWeight": "600",
                "color": color or THEME["text"],
                "fontFamily": "monospace",
            }),
        ])

    def pts(val, label):
        v = int(val) if val else 0
        c = THEME["green"] if v > 0 else THEME["text3"]
        return html.Div([
            html.Span(f"{'✓' if v > 0 else '·'} {label}", style={
                "fontSize": "11px", "color": c, "fontFamily": "monospace",
            }),
            html.Span(f"+{v}", style={
                "fontSize": "11px", "color": c,
                "fontFamily": "monospace", "float": "right",
            }),
        ], style={"padding": "2px 0"})

    detail = html.Div([
        # Score grande
        html.Div([
            html.Div(f"{score}/13", style={
                "fontSize": "36px", "fontWeight": "700",
                "color": score_color, "fontFamily": "monospace",
                "lineHeight": "1",
            }),
            html.Div(result.get("label", ""), style={
                "fontSize": "11px", "color": score_color,
                "marginTop": "4px", "fontWeight": "600",
            }),
        ], style={
            "background": THEME["bg3"],
            "borderRadius": "10px",
            "padding": "14px",
            "marginBottom": "12px",
            "border": f"1px solid {score_color}44",
            "textAlign": "center",
        }),

        # Precio y range
        row("PRECIO", f"${result.get('price', 0):.2f}"),
        row("POSICIÓN RANGE", f"{result.get('range_pct', 0):.1f}%"),

        # Separador
        html.Hr(style={"borderColor": THEME["border"], "margin": "12px 0"}),

        # Detalle módulos
        html.Div("ORDER FLOW", style={
            "fontSize": "10px", "color": THEME["text3"],
            "letterSpacing": "0.08em", "marginBottom": "4px",
            "fontFamily": "monospace",
        }),
        pts(result.get("cvd_div"),    "CVD divergencia"),
        pts(result.get("high_vol"),   "Volumen alto"),
        pts(result.get("absorption"), "Absorción"),

        html.Div("SMC", style={
            "fontSize": "10px", "color": THEME["text3"],
            "letterSpacing": "0.08em", "margin": "8px 0 4px",
            "fontFamily": "monospace",
        }),
        pts(result.get("in_ob"),   "En Order Block"),
        pts(result.get("in_fvg"),  "En FVG"),
        pts(result.get("new_ob"),  "Nuevo OB"),
        pts(result.get("discount"),"En Discount"),

        html.Div("TRIGGERS", style={
            "fontSize": "10px", "color": THEME["text3"],
            "letterSpacing": "0.08em", "margin": "8px 0 4px",
            "fontFamily": "monospace",
        }),
        pts(result.get("sweep"), "Stop Hunt"),
        pts(result.get("mss"),   "MSS alcista"),

        # Acción recomendada
        html.Hr(style={"borderColor": THEME["border"], "margin": "12px 0"}),
        html.Div(
            ("→ Buscá entry en M5\ncon SL bajo el OB"
             if status == "ENTRY"
             else f"→ Faltan ~{max(0, 8-score)}pts\npara señal completa"
             if status in ("SETUP", "WATCH")
             else "→ Sin confluencia\nEsperando setup"),
            style={
                "fontSize": "11px",
                "color": score_color,
                "background": THEME["bg3"],
                "borderRadius": "8px",
                "padding": "10px",
                "whiteSpace": "pre-line",
                "lineHeight": "1.6",
                "border": f"1px solid {score_color}33",
            }
        ),
    ])

    return detail, now_str


# =============================================================
# LANZAR APP
# =============================================================

if __name__ == "__main__":
    port      = DASHBOARD.get("port", 8050)
    auto_open = DASHBOARD.get("auto_open", True)

    print(f"\n  🐋 Whale Tracker Dashboard")
    print(f"  Tickers  : {', '.join(TICKERS)}")
    print(f"  Timeframe: {TIMEFRAME}")
    print(f"  URL      : http://localhost:{port}")
    print(f"\n  En Codespaces: click en 'Open in Browser' ↗")
    print(f"  Ctrl+C para detener\n")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        dev_tools_silence_routes_logging=True,
    )
