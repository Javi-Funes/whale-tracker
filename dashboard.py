# =============================================================
# WHALE TRACKER — dashboard.py v2 (fix clicks)
# =============================================================

import sys
import json
from datetime import datetime
import numpy as np

try:
    import dash
    from dash import dcc, html, Input, Output, State, ALL, callback_context
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError:
    print("\n  ⚠ pip install -r requirements.txt\n"); sys.exit(1)

try:
    from config import TICKERS, TIMEFRAME, PERIOD, ENGINE, UPDATE_INTERVAL, DASHBOARD
except ImportError:
    print("\n  ⚠ Corré: python setup_console.py\n"); sys.exit(1)

from whale_engine import WhaleEngine

engines: dict[str, WhaleEngine] = {
    t: WhaleEngine(t, TIMEFRAME, PERIOD, ENGINE) for t in TICKERS
}

THEME = {
    "bg":"#060a0f","bg2":"#0d1520","bg3":"#111d2e",
    "border":"rgba(100,180,255,0.12)","text":"#e8f4ff",
    "text2":"#7ba8c8","text3":"#4a7090","accent":"#00d4ff",
    "green":"#00e5a0","red":"#ff4466","amber":"#f0b429","purple":"#a855f7",
    "grid":"rgba(100,180,255,0.05)","up":"#00e5a0","down":"#ff4466",
    "ob_bull":"rgba(0,212,255,0.12)","ob_bear":"rgba(255,68,102,0.10)",
    "fvg_bull":"rgba(168,85,247,0.12)","fvg_bear":"rgba(255,68,102,0.08)",
}

def build_chart(ticker):
    engine = engines[ticker]
    result = engine.run() if engine.df is None else engine.calc_score()
    df = engine.df
    if df is None or df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sin datos", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False,
                           font=dict(color=THEME["text2"], size=16))
        fig.update_layout(paper_bgcolor=THEME["bg"], plot_bgcolor=THEME["bg2"])
        return fig

    df = df.tail(DASHBOARD.get("candles", 120)).copy()
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        vertical_spacing=0.03, row_heights=[0.65, 0.20, 0.15])

    fig.add_trace(go.Candlestick(
        x=df.index, open=df["open"], high=df["high"], low=df["low"], close=df["close"],
        increasing=dict(line=dict(color=THEME["up"], width=1), fillcolor=THEME["up"]),
        decreasing=dict(line=dict(color=THEME["down"], width=1), fillcolor=THEME["down"]),
        showlegend=False), row=1, col=1)

    for zone in engine.get_ob_zones():
        c = THEME["ob_bull"] if zone["type"]=="bull" else THEME["ob_bear"]
        b = THEME["accent"]  if zone["type"]=="bull" else THEME["red"]
        fig.add_hrect(y0=zone["bottom"], y1=zone["top"], fillcolor=c,
                      line=dict(color=b, width=0.8, dash="dot"),
                      annotation_text=f"OB {'▲' if zone['type']=='bull' else '▼'} {zone['top']:.2f}",
                      annotation=dict(font=dict(color=b, size=10), x=1.0, xanchor="right"),
                      row=1, col=1)

    for zone in engine.get_fvg_zones():
        c = THEME["fvg_bull"] if zone["type"]=="bull" else THEME["fvg_bear"]
        b = THEME["purple"]   if zone["type"]=="bull" else THEME["red"]
        fig.add_hrect(y0=zone["bottom"], y1=zone["top"], fillcolor=c,
                      line=dict(color=b, width=0.5, dash="dash"),
                      annotation_text=f"FVG {zone['top']:.2f}",
                      annotation=dict(font=dict(color=b, size=9), x=0.01, xanchor="left"),
                      row=1, col=1)

    last = df.iloc[-1]
    if "range_mid" in df.columns and not np.isnan(last["range_mid"]):
        fig.add_hline(y=last["range_mid"],
                      line=dict(color=THEME["amber"], width=1, dash="dot"),
                      annotation_text=f"EQ {last['range_mid']:.2f}",
                      annotation=dict(font=dict(color=THEME["amber"], size=10)),
                      row=1, col=1)

    if "swing_high" in df.columns:
        sh = df[df["swing_high"].notna() & (df["swing_high"] != df["swing_high"].shift(1))]
        if len(sh): fig.add_trace(go.Scatter(x=sh.index, y=sh["swing_high"], mode="markers",
            marker=dict(symbol="triangle-down", size=8, color=THEME["red"], opacity=0.7),
            showlegend=False), row=1, col=1)

    if "swing_low" in df.columns:
        sl = df[df["swing_low"].notna() & (df["swing_low"] != df["swing_low"].shift(1))]
        if len(sl): fig.add_trace(go.Scatter(x=sl.index, y=sl["swing_low"], mode="markers",
            marker=dict(symbol="triangle-up", size=8, color=THEME["green"], opacity=0.7),
            showlegend=False), row=1, col=1)

    if "mss_bull" in df.columns:
        mss = df[df["mss_bull"]==True]
        if len(mss): fig.add_trace(go.Scatter(x=mss.index, y=mss["low"]*0.998,
            mode="markers+text", marker=dict(symbol="arrow-up", size=14, color=THEME["green"]),
            text=["MSS↑"]*len(mss), textposition="bottom center",
            textfont=dict(color=THEME["green"], size=9), showlegend=False), row=1, col=1)

    if "stop_hunt_bull" in df.columns:
        sw = df[df["stop_hunt_bull"]==True]
        if len(sw): fig.add_trace(go.Scatter(x=sw.index, y=sw["low"]*0.996,
            mode="markers", marker=dict(symbol="star", size=12, color=THEME["amber"]),
            showlegend=False), row=1, col=1)

    if "cvd" in df.columns:
        fig.add_trace(go.Bar(x=df.index, y=df["cvd"],
            marker=dict(color=[THEME["green"] if v>=0 else THEME["red"]
                               for v in df["cvd"].fillna(0)], opacity=0.7),
            showlegend=False), row=2, col=1)
        if "cvd_div_bull" in df.columns:
            d = df[df["cvd_div_bull"]==True]
            if len(d): fig.add_trace(go.Scatter(x=d.index, y=d["cvd"], mode="markers",
                marker=dict(symbol="circle", size=8, color=THEME["amber"]),
                showlegend=False), row=2, col=1)

    if "volume" in df.columns:
        fig.add_trace(go.Bar(x=df.index, y=df["volume"],
            marker=dict(color=[THEME["green"] if c>=o else THEME["down"]
                               for c,o in zip(df["close"],df["open"])], opacity=0.6),
            showlegend=False), row=3, col=1)
        if "avg_vol" in df.columns:
            fig.add_trace(go.Scatter(x=df.index, y=df["avg_vol"],
                line=dict(color=THEME["amber"], width=1, dash="dot"),
                showlegend=False), row=3, col=1)

    score = result.get("total",0) if result else 0
    status= result.get("label","ESPERANDO") if result else "ESPERANDO"
    price = result.get("price",0) if result else 0
    rng   = result.get("range_pct",50) if result else 50
    tc = (THEME["green"] if score>=ENGINE.get("signal_threshold",8)
          else THEME["amber"] if score>=ENGINE.get("warn_threshold",6) else THEME["text2"])

    fig.update_layout(
        title=dict(text=(f"<b>{ticker}</b>  ·  ${price:.2f}  ·  "
                         f"Score: <span style='color:{tc}'>{score}/13</span>  ·  "
                         f"{status}  ·  Range: {rng:.0f}%  ·  TF: {TIMEFRAME}  ·  "
                         f"{datetime.now().strftime('%H:%M:%S')}"),
                   font=dict(color=THEME["text"], size=13), x=0.01),
        paper_bgcolor=THEME["bg"], plot_bgcolor=THEME["bg2"],
        font=dict(color=THEME["text2"], family="monospace", size=11),
        margin=dict(l=60, r=120, t=50, b=20),
        xaxis_rangeslider_visible=False, hovermode="x unified",
        hoverlabel=dict(bgcolor=THEME["bg3"], font=dict(color=THEME["text"], size=11)),
    )
    for i in range(1,4):
        fig.update_xaxes(gridcolor=THEME["grid"], linecolor=THEME["border"], row=i, col=1)
        fig.update_yaxes(gridcolor=THEME["grid"], linecolor=THEME["border"], row=i, col=1)
    fig.update_yaxes(title_text="Precio",  title_font=dict(size=10), row=1, col=1)
    fig.update_yaxes(title_text="CVD",     title_font=dict(size=10), row=2, col=1)
    fig.update_yaxes(title_text="Volumen", title_font=dict(size=10), row=3, col=1)
    return fig


def score_card(ticker, result, selected):
    is_sel = ticker == selected
    if not result:
        return html.Div([
            html.Div(ticker, style={"fontWeight":"700","color":THEME["text"],"fontFamily":"monospace"}),
            html.Div("Cargando...", style={"color":THEME["text3"],"fontSize":"11px"}),
        ], id={"type":"ticker-card","index":ticker}, n_clicks=0, style={
            "background":THEME["bg"] if is_sel else THEME["bg3"],
            "border":f"1px solid {THEME['accent'] if is_sel else THEME['border']}",
            "borderRadius":"10px","padding":"10px 14px","marginBottom":"8px","cursor":"pointer"})

    score  = result.get("total",0)
    status = result.get("status","WAITING")
    label  = result.get("label","ESPERANDO")
    emoji  = result.get("emoji","⏳")
    price  = result.get("price",0)
    pct    = score/13*100
    sc = (THEME["green"] if status=="ENTRY" else THEME["amber"] if status=="SETUP"
          else THEME["accent"] if status=="WATCH" else THEME["text3"])
    bc = sc if (is_sel or status in ("ENTRY","SETUP")) else THEME["border"]

    return html.Div([
        html.Div([
            html.Span(ticker, style={"fontWeight":"700","fontSize":"14px",
                                     "color":THEME["text"],"fontFamily":"monospace"}),
            html.Span(f"${price:.2f}", style={"fontSize":"11px","color":THEME["text3"],
                                               "fontFamily":"monospace","float":"right"}),
        ]),
        html.Div(style={"background":THEME["bg"],"borderRadius":"3px","height":"4px",
                        "margin":"6px 0","overflow":"hidden"},
                 children=[html.Div(style={"width":f"{pct:.0f}%","height":"100%",
                                           "background":sc,"borderRadius":"3px"})]),
        html.Div([
            html.Span(f"{emoji} {label}", style={"fontSize":"11px","color":sc,"fontWeight":"600"}),
            html.Span(f"{score}/13", style={"fontSize":"11px","color":sc,
                                             "fontFamily":"monospace","float":"right"}),
        ]),
    ], id={"type":"ticker-card","index":ticker}, n_clicks=0, style={
        "background":THEME["bg"] if is_sel else THEME["bg3"],
        "border":f"1px solid {bc}","borderRadius":"10px",
        "padding":"10px 14px","marginBottom":"8px","cursor":"pointer"})


app = dash.Dash(__name__, title="🐋 Whale Tracker", update_title=None)

app.layout = html.Div(style={"background":THEME["bg"],"minHeight":"100vh",
                               "fontFamily":"monospace","color":THEME["text"]}, children=[
    html.Div(style={"background":THEME["bg2"],"borderBottom":f"1px solid {THEME['border']}",
                    "padding":"14px 24px","display":"flex","alignItems":"center",
                    "justifyContent":"space-between"},
    children=[
        html.Div([
            html.Span("🐋 "), 
            html.Span("WHALE TRACKER", style={"fontSize":"18px","fontWeight":"700","color":THEME["accent"]}),
            html.Span(" — SMC Confluence Engine", style={"fontSize":"12px","color":THEME["text3"],"marginLeft":"10px"}),
        ]),
        html.Div(id="header-time", style={"fontSize":"12px","color":THEME["text3"]}),
    ]),
    html.Div(style={"display":"flex","height":"calc(100vh - 56px)"}, children=[
        html.Div(style={"width":"220px","minWidth":"220px","background":THEME["bg2"],
                        "borderRight":f"1px solid {THEME['border']}","padding":"14px 12px","overflowY":"auto"},
        children=[
            html.Div("ACTIVOS", style={"fontSize":"10px","color":THEME["text3"],
                                        "letterSpacing":"0.1em","marginBottom":"12px"}),
            html.Div(id="sidebar-cards"),
        ]),
        html.Div(style={"flex":"1","padding":"12px","overflow":"hidden"}, children=[
            dcc.Graph(id="main-chart", style={"height":"100%"},
                      config={"displayModeBar":True,"displaylogo":False,"scrollZoom":True,
                               "modeBarButtonsToRemove":["lasso2d","select2d"]}),
        ]),
        html.Div(style={"width":"200px","minWidth":"200px","background":THEME["bg2"],
                        "borderLeft":f"1px solid {THEME['border']}","padding":"14px 12px","overflowY":"auto"},
        children=[
            html.Div("SEÑAL ACTIVA", style={"fontSize":"10px","color":THEME["text3"],
                                             "letterSpacing":"0.1em","marginBottom":"12px"}),
            html.Div(id="signal-detail"),
        ]),
    ]),
    dcc.Store(id="selected-ticker", data=TICKERS[0]),
    dcc.Store(id="results-store",   data={}),
    dcc.Interval(id="interval-fast", interval=5_000,               n_intervals=0),
    dcc.Interval(id="interval-data", interval=UPDATE_INTERVAL*1000, n_intervals=0),
])


@app.callback(Output("results-store","data"), Input("interval-data","n_intervals"))
def update_data(n):
    out = {}
    for t in TICKERS:
        try:
            r = engines[t].run()
            if r:
                out[t] = {k:(None if isinstance(v,float) and np.isnan(v) else v)
                          for k,v in r.items()}
        except Exception as e:
            print(f"  [ERROR] {t}: {e}")
    return out


@app.callback(
    Output("selected-ticker","data"),
    Input({"type":"ticker-card","index":ALL},"n_clicks"),
    State("selected-ticker","data"),
    prevent_initial_call=True,
)
def select_ticker(n_clicks_list, current):
    ctx = callback_context
    if not ctx.triggered:
        return current
    try:
        id_dict = json.loads(ctx.triggered[0]["prop_id"].split(".")[0])
        t = id_dict.get("index", current)
        return t if t in TICKERS else current
    except Exception:
        return current


@app.callback(
    Output("main-chart","figure"),
    Input("selected-ticker","data"),
    Input("interval-fast","n_intervals"),
)
def update_chart(ticker, n):
    return build_chart(ticker)


@app.callback(
    Output("sidebar-cards","children"),
    Input("results-store","data"),
    Input("selected-ticker","data"),
)
def update_sidebar(results, selected):
    st = sorted(TICKERS, key=lambda t:(results.get(t) or {}).get("total",-1), reverse=True)
    return [score_card(t, results.get(t), selected) for t in st]


@app.callback(
    Output("signal-detail","children"),
    Output("header-time","children"),
    Input("selected-ticker","data"),
    Input("results-store","data"),
    Input("interval-fast","n_intervals"),
)
def update_detail(ticker, results, n):
    now_str = datetime.now().strftime("%H:%M:%S  ·  %d/%m/%Y")
    result  = (results or {}).get(ticker)
    if not result:
        return html.Div("Cargando...", style={"color":THEME["text3"],"fontSize":"12px"}), now_str

    score  = result.get("total",0)
    status = result.get("status","WAITING")
    sc = (THEME["green"] if status=="ENTRY" else THEME["amber"] if status=="SETUP"
          else THEME["accent"] if status=="WATCH" else THEME["text3"])

    def row(label, val, color=None):
        return html.Div([
            html.Span(label, style={"fontSize":"10px","color":THEME["text3"],"display":"block",
                                    "marginTop":"8px","letterSpacing":"0.05em"}),
            html.Span(str(val), style={"fontSize":"13px","fontWeight":"600",
                                        "color":color or THEME["text"]}),
        ])

    def pts(val, label):
        v = int(val) if val else 0
        c = THEME["green"] if v>0 else THEME["text3"]
        return html.Div([
            html.Span(f"{'✓' if v>0 else '·'} {label}", style={"fontSize":"11px","color":c}),
            html.Span(f"+{v}", style={"fontSize":"11px","color":c,"float":"right"}),
        ], style={"padding":"2px 0"})

    action = ("→ Buscá entry en M5\ncon SL bajo el OB" if status=="ENTRY"
              else f"→ Faltan ~{max(0,8-score)}pts\npara señal completa" if status in ("SETUP","WATCH")
              else "→ Sin confluencia\nEsperando setup")

    return html.Div([
        html.Div([
            html.Div(f"{score}/13", style={"fontSize":"36px","fontWeight":"700",
                                            "color":sc,"lineHeight":"1"}),
            html.Div(result.get("label",""), style={"fontSize":"11px","color":sc,
                                                     "marginTop":"4px","fontWeight":"600"}),
        ], style={"background":THEME["bg3"],"borderRadius":"10px","padding":"14px",
                  "marginBottom":"12px","border":f"1px solid {sc}44","textAlign":"center"}),
        row("PRECIO",         f"${result.get('price',0):.2f}"),
        row("POSICIÓN RANGE", f"{result.get('range_pct',0):.1f}%"),
        html.Hr(style={"borderColor":THEME["border"],"margin":"12px 0"}),
        html.Div("ORDER FLOW", style={"fontSize":"10px","color":THEME["text3"],
                                       "letterSpacing":"0.08em","marginBottom":"4px"}),
        pts(result.get("cvd_div"),    "CVD divergencia"),
        pts(result.get("high_vol"),   "Volumen alto"),
        pts(result.get("absorption"), "Absorción"),
        html.Div("SMC", style={"fontSize":"10px","color":THEME["text3"],
                                "letterSpacing":"0.08em","margin":"8px 0 4px"}),
        pts(result.get("in_ob"),    "En Order Block"),
        pts(result.get("in_fvg"),   "En FVG"),
        pts(result.get("new_ob"),   "Nuevo OB"),
        pts(result.get("discount"), "En Discount"),
        html.Div("TRIGGERS", style={"fontSize":"10px","color":THEME["text3"],
                                     "letterSpacing":"0.08em","margin":"8px 0 4px"}),
        pts(result.get("sweep"), "Stop Hunt"),
        pts(result.get("mss"),   "MSS alcista"),
        html.Hr(style={"borderColor":THEME["border"],"margin":"12px 0"}),
        html.Div(action, style={"fontSize":"11px","color":sc,"background":THEME["bg3"],
                                 "borderRadius":"8px","padding":"10px","whiteSpace":"pre-line",
                                 "lineHeight":"1.6","border":f"1px solid {sc}33"}),
    ]), now_str


if __name__ == "__main__":
    port = DASHBOARD.get("port", 8050)
    print(f"\n  🐋 Whale Tracker Dashboard")
    print(f"  Tickers : {', '.join(TICKERS)}")
    print(f"  URL     : http://localhost:{port}")
    print(f"  Codespaces: click en 'Open in Browser' ↗\n")
    app.run(host="0.0.0.0", port=port, debug=False,
            dev_tools_silence_routes_logging=True)
