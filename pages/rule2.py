import streamlit as st
import requests
import pandas as pd
from datetime import datetime

API_BASE = st.secrets.get("TOWER_API_BASE", "https://app.kumagai-stock.com")

@st.cache_data(ttl=60)
def fetch_5m_breakouts():
    url = f"{API_BASE}/api/pattern/5m_breakout"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return pd.DataFrame()
    df = pd.DataFrame(data)

    # break_date を人間向けに
    if "break_date" in df.columns:
        df["break_date_dt"] = pd.to_datetime(df["break_date"], format="%Y%m%d", errors="coerce")
        df["ブレイク日"] = df["break_date_dt"].dt.strftime("%Y-%m-%d")

    return df

st.title("5ヶ月もみ合い ➝ ブレイク銘柄（ルール2）")
st.write(f"Tower API: `{API_BASE}`")

with st.spinner("5ヶ月もみ合いブレイク銘柄を取得中…"):
    try:
        df = fetch_5m_breakouts()
    except requests.exceptions.RequestException as e:
        st.error(f"API呼び出し中にエラーが発生しました: {e}")
        st.stop()

if df.empty:
    st.info("現在、条件に合致する銘柄はありません。")
else:
    st.success(f"抽出銘柄数: {len(df)} 件")
    st.dataframe(df, use_container_width=True, hide_index=True)
