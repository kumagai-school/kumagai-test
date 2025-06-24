import streamlit as st
import requests
import math

# 外部APIのURL（Cloudflare Tunnel 経由）
HIGHLOW_API = "https://app.kumagai-stock.com/api/highlow"

# ページ設定
st.set_page_config(page_title="ルール1 株価チェック", layout="centered")

# CSS（入力欄の文字拡大）
st.markdown("""
    <style>
    input[type="number"], input[type="text"] {
        font-size: 22px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# タイトル
st.markdown("""
    <h1 style='text-align:left; color:#2E86C1; font-size:26px; line-height:1.4em;'>
        『ルール1』<br>株価チェックアプリ
    </h1>
""", unsafe_allow_html=True)

st.markdown("---")
st.markdown("<h4>📌 <strong>注意事項</strong></h4>", unsafe_allow_html=True)

st.markdown("""
<div style='color:red; font-size:14px;'>
<ul>
  <li>このアプリは東京証券取引所（.T）上場企業のみに対応しています。</li>
  <li>平日8時30分～9時に5分程度のメンテナンスが入ることがあります。</li>
  <li>ゴールデンウィークなどの連休・イレギュラーな日程には正確に対応できない場合があります。</li>
</ul>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

st.caption("ルール１に該当する企業コードをこちらにご入力ください。")

# 追加：
query_params = st.experimental_get_query_params()
default_code = query_params.get("code", ["7203"])[0]  # デフォルトは7203

# 修正：
code = st.text_input("企業コード（半角英数字のみ、例: 7203）", default_code)

recent_high = None
recent_low = None

def green_box(label, value, unit):
    st.markdown(f"""
        <div style="
            background-color: #f0fdf4;
            border-left: 4px solid #4CAF50;
            padding: 10px 15px;
            border-radius: 5px;
            margin-bottom: 10px;">
            ✅ <strong>{label}：</strong><br>
            <span style="font-size:24px; font-weight:bold;">{value} {unit}</span>
        </div>
    """, unsafe_allow_html=True)

if code:
    try:
        response = requests.get(HIGHLOW_API, params={"code": code})
        if response.status_code == 200:
            data = response.json()
            company_name = data.get("name", "企業名不明")
            recent_high = data["high"]
            high_date = data["high_date"]
            recent_low = data["low"]
            low_date = data["low_date"]

            st.subheader(f"{company_name}（{code}）の株価情報")
            st.markdown(f"✅ **直近5営業日の高値**:<br><span style='font-size:24px'>{recent_high:.2f} 円（{high_date}）</span>", unsafe_allow_html=True)
            st.markdown(f"✅ **高値日から過去2週間以内の安値**:<br><span style='font-size:24px'>{recent_low:.2f} 円（{low_date}）</span>", unsafe_allow_html=True)

        else:
            st.error(f"APIエラー: {response.status_code} - {response.text}")
    except Exception as e:
        st.error(f"データ取得中にエラーが発生しました: {e}")

st.markdown("---")
st.markdown("<h4>📌 <strong>注意事項</strong></h4>", unsafe_allow_html=True)

st.markdown("""
<div style='color:red; font-size:14px;'>
<ul>
  <li>チャートは当日分は反映しておりません。
</ul>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

if code.strip():  # 入力がある場合、自動で表示
    with st.spinner("データを取得中..."):
        try:
          candle_url = "https://app.kumagai-stock.com/api/candle"
          resp = requests.get(candle_url, params={"code": code})
          chart_data = resp.json().get("data", [])

          if not chart_data:
              st.warning("チャートデータが取得できませんでした。")
          else:
              import pandas as pd
              import plotly.graph_objects as go

              df = pd.DataFrame(chart_data)
              df["date"] = pd.to_datetime(df["date"], errors="coerce")
              df["date_str"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")

              df["hovertext"] = (
                "日付: " + df["date_str"] + "<br>" +
                "始値: " + df["open"].astype(str) + "<br>" +
                "高値: " + df["high"].astype(str) + "<br>" +
                "安値: " + df["low"].astype(str) + "<br>" +
                "終値: " + df["close"].astype(str)
              )

              fig = go.Figure(data=[
                  go.Candlestick(
                      x=df["date_str"],
                      open=df["open"],
                      high=df["high"],
                      low=df["low"],
                      close=df["close"],
                      increasing_line_color='red',
                      decreasing_line_color='blue',
                      hovertext=df["hovertext"],
                      hoverinfo="text"
                  )
              ])

              fig.update_layout(
                  title=f"{data.get('name', '')} の2週間ローソク足チャート",
                  xaxis_title="日付",
                  yaxis_title="株価",
                  xaxis_rangeslider_visible=False,
                  xaxis=dict(
                      type='category',  # ← 営業日のみ詰めて表示
                      tickangle=-45     # 日付が重なりにくくなります
                  )
              )
              st.plotly_chart(fig, use_container_width=True, key="chart")

        except Exception as e:
          st.error(f"チャート取得中にエラーが発生しました: {e}")

st.markdown("---")

# 計算ツール
if recent_high and recent_low:
    st.markdown("""
        <h2 style='text-align:left; color:#2E86C1; font-size:26px; line-height:1.4em;'>
            上げ幅の半値押し<br>計算ツール
        </h2>
    """, unsafe_allow_html=True)

    high_input = st.number_input("高値（円）", min_value=0.0, value=recent_high, format="%.2f")
    low_input = st.number_input("2週間以内の最安値（円）", min_value=0.0, value=recent_low, format="%.2f")
    st.caption("必要であれば高値・安値を修正して「計算する」をタップしてください。")

    if st.button("計算する"):
        if high_input > low_input > 0:
            rise_rate = high_input / low_input
            width = high_input - low_input
            half = math.floor(width / 2)
            retrace = math.floor(high_input - half)

            green_box("上昇率", f"{rise_rate:.2f}", "倍")
            green_box("上げ幅", f"{width:.2f}", "円")
            green_box("上げ幅の半値", f"{half}", "円")
            green_box("上げ幅の半値押し", f"{retrace}", "円")
        else:
            st.warning("高値＞安値 の数値を正しく入力してください。")

st.markdown("""
<div style='
    text-align: center;
    color: gray;
    font-size: 14px;
    font-family: "Segoe UI", "Helvetica Neue", "Arial", sans-serif !important;
    letter-spacing: 0.5px;
    unicode-bidi: plaintext;
'>
&copy; 2025 KumagaiNext All rights reserved.
</div>
""", unsafe_allow_html=True)

