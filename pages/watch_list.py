import os
import streamlit as st
from supabase import create_client, Client
import pandas as pd
import requests

# ① Supabase接続関数
@st.cache_resource
def init_connection() -> Client | None:
    url = None
    key = None

    # まず secrets から読む
    try:
        if "supabase" in st.secrets:
            url = st.secrets["supabase"].get("url")
            key = st.secrets["supabase"].get("key")
    except Exception:
        pass

    # ダメなら環境変数から
    if not url:
        url = os.environ.get("SUPABASE_URL")
    if not key:
        key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        return None

    return create_client(url, key)

# ② ここで supabase 変数を作る（←これが先）
supabase: Client | None = init_connection()

# ③ そのあとにチェック（←これをいきなりファイルの先頭に書かない）
if supabase is None:
    st.error(
        "Supabase 接続情報が設定されていません。\n"
        "secrets.toml または環境変数 SUPABASE_URL / SUPABASE_KEY を設定してください。"
    )
    st.stop()

# ④ ここから下にページ本体のコード
st.title("📈 マイ監視リストページ")

# ② RシステムPRO用 API
@st.cache_data(ttl=900)
def load_rsystem_data(source):
    url_map = {
        "today": "https://app.kumagai-stock.com/api/highlow/today",
        "target2day": "https://app.kumagai-stock.com/api/highlow/target2day",
        "target3day": "https://app.kumagai-stock.com/api/highlow/target3day",
    }
    url = url_map.get(source)
    res = requests.get(url, timeout=10)
    res.raise_for_status()
    return pd.DataFrame(res.json())


# ③ マイ監視リストを読み込む
def load_my_watchlist():
    resp = (
        supabase.table("watch_list")
        .select("*")
        .eq("session_key", SESSION_KEY)
        .eq("list_type", "my")
        .order("id", desc=True)
        .execute()
    )
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()


# ④ マイ監視リストを削除
def delete_my_item(item_id):
    supabase.table("watch_list").delete().eq("id", item_id).execute()


# ⑤ 上げ幅の半値押しを計算
def calc_half_retrace(high, low):
    return round((high + low) / 2, 2)


# ==============================================================
st.title("📈 マイ監視リストページ（独立）")

st.markdown("---")
st.header("📌 マイ監視リスト")
my_df = load_my_watchlist()

if my_df.empty:
    st.info("マイ監視リストはまだ空です。")
else:
    for _, row in my_df.iterrows():
        code = row["code"]
        name = row["name"]

        cols = st.columns([3, 2, 2, 2, 3])
        with cols[0]:
            st.markdown(f"**{name}（{code}）**")
        with cols[1]:
            st.write(f"上げ幅の半値押し: {row['half_retrace']}")
        with cols[2]:
            st.write(f"現在値: {row['current_price']}")
        with cols[3]:
            st.write(f"半値押しまで: {row['distance_percent']}%")

        kabutan_chart = f"https://kabutan.jp/stock/chart?code={code}"
        kabutan_fin   = f"https://kabutan.jp/stock/finance?code={code}"
        kabutan_news  = f"https://kabutan.jp/stock/news?code={code}"

        with cols[4]:
            st.markdown(
                f"[チャート]({kabutan_chart})｜"
                f"[決算]({kabutan_fin})｜"
                f"[ニュース]({kabutan_news})"
            )
            if st.button("削除", key=f"del_{row['id']}"):
                delete_my_item(row['id'])
                st.rerun()

st.markdown("---")

# ==============================================================
st.header("📌 RシステムPRO 監視リスト（本日＋2日前＋3日前 自動反映）")

# ⑥ 今日・2日前・3日前をまとめて取得
sources = [
    ("本日", "today"),
    ("2日前", "target2day"),
    ("3日前", "target3day"),
]

all_rows = []

for label, key in sources:
    try:
        df = load_rsystem_data(key)
        if df is not None and not df.empty:
            df["day_label"] = label
            all_rows.append(df)
    except:
        pass

if not all_rows:
    st.info("データがありません。")
else:
    df_all = pd.concat(all_rows, ignore_index=True)

    for _, row in df_all.iterrows():
        code = row["code"]
        name = row["name"]
        day_label = row["day_label"]

        high, low = row["high"], row["low"]
        half_retrace = calc_half_retrace(high, low)
        current_price = row.get("current_price")
        distance = row.get("halfPriceDistancePercent")

        kabutan_chart = f"https://kabutan.jp/stock/chart?code={code}"
        kabutan_fin   = f"https://kabutan.jp/stock/finance?code={code}"
        kabutan_news  = f"https://kabutan.jp/stock/news?code={code}"

        cols = st.columns([3, 2, 2, 2, 3])
        with cols[0]:
            st.markdown(f"**[{day_label}] {name}（{code}）**")
        with cols[1]:
            st.write(f"半値押し: {half_retrace}")
        with cols[2]:
            st.write(f"現在値: {current_price}")
        with cols[3]:
            st.write(f"距離: {distance}%")
        with cols[4]:
            st.markdown(
                f"[チャート]({kabutan_chart})｜"
                f"[決算]({kabutan_fin})｜"
                f"[ニュース]({kabutan_news})"
            )
