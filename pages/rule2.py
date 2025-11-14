import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import os
import plotly.graph_objects as go

# Tower API のベースURL
API_BASE = os.getenv("TOWER_API_BASE", "https://app.kumagai-stock.com")


# 5ヶ月もみ合いブレイク銘柄一覧を取得
@st.cache_data(ttl=60)
def fetch_breakouts():
    url = f"{API_BASE}/api/pattern/5m_breakout"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return []
    return data


# 5ヶ月分のチャート（終値）を取得
@st.cache_data(ttl=300)
def fetch_candle_5m(code: str):
    url = f"{API_BASE}/api/candle"
    params = {"code": code}
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    j = resp.json()

    cd = j.get("code")
    rows = j.get("data", [])
    if not rows:
        return cd, pd.DataFrame()

    df = pd.DataFrame(rows)  # date, open, high, low, close
    # dateは "YYYYMMDD" 想定
    df["dt"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["dt"]).sort_values("dt")

    # 直近5ヶ月（ざっくり155日）に絞る
    if not df.empty:
        end_dt = df["dt"].max()
        start_dt = end_dt - timedelta(days=155)
        df = df[df["dt"] >= start_dt]

    return cd, df


# =========================
# Streamlit UI
# =========================
st.markdown("---")
st.markdown("### 「ルール2」スクリーニング")

with st.spinner("塔サーバーからデータ取得中…"):
    try:
        records = fetch_breakouts()
    except Exception as e:
        st.error(f"API呼び出し中にエラーが発生しました: {e}")
        st.stop()

if not records:
    st.info("現在、条件に合致する銘柄はありません。")
    st.stop()

st.success(f"抽出銘柄数：{len(records)} 銘柄")

# 銘柄ごとにカード表示
for rec in records:
    code = rec.get("code", "")
    name = rec.get("name", "")
    base_high = rec.get("base_high", None)
    base_low = rec.get("base_low", None)
    break_close = rec.get("break_close", None)
    break_date_str = rec.get("break_date", "")

    # ブレイク日を "〇月〇日" に整形
    try:
        d = datetime.strptime(break_date_str, "%Y%m%d")
        break_date_disp = d.strftime("%m月%d日")
    except Exception:
        break_date_disp = break_date_str

    # === テキスト部分 ===
    st.markdown(f"### {name}（{code}）")

    if base_high is not None:
        st.write(f"**もみ合い高値：** {base_high:,.0f} 円")
    if base_low is not None:
        st.write(f"**もみ合い安値：** {base_low:,.0f} 円")
    if break_close is not None:
        st.write(f"**ブレイクポイント：** {break_close:,.0f} 円（{break_date_disp}）")

    # === 5ヶ月チャート ===
    _, df_candle = fetch_candle_5m(code)
    if df_candle.empty:
        st.warning("チャートデータが取得できませんでした。")
    else:
        st.write("**5ヵ月 日足チャート（ローソク足）**")

        # Plotly 用にソート
        df_plot = df_candle.sort_values("dt")

        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=df_plot["dt"],
                    open=df_plot["open"],
                    high=df_plot["high"],
                    low=df_plot["low"],
                    close=df_plot["close"],
                    name="日足"
                )
            ]
        )

        # レイアウト少し整える（お好みで調整OK）
        fig.update_layout(
            xaxis_title="日付",
            yaxis_title="株価（円）",
            xaxis_rangeslider_visible=False,
            height=400,
            margin=dict(l=40, r=20, t=40, b=40),
        )

        st.plotly_chart(fig, use_container_width=True)


    st.markdown("---")


