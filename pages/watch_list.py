import os
import streamlit as st
from supabase import create_client, Client
import pandas as pd
import requests
import uuid
import hashlib

# --- ① Supabase接続関数（まず定義） ---
@st.cache_resource
def init_connection() -> Client | None:
    url = None
    key = None

    try:
        if "supabase" in st.secrets:
            url = st.secrets["supabase"].get("url")
            key = st.secrets["supabase"].get("key")
    except Exception:
        pass

    if not url:
        url = os.environ.get("SUPABASE_URL")
    if not key:
        key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        return None

    return create_client(url, key)

# --- ② Supabase クライアント作成 ---
supabase: Client | None = init_connection()

# --- ③ 接続がなければ停止 ---
if supabase is None:
    st.error(
        "Supabase 接続情報が設定されていません。\n"
        "secrets.toml または SUPABASE_URL / SUPABASE_KEY を設定してください。"
    )
    st.stop()


# ③ そのあとにチェック（←これをいきなりファイルの先頭に書かない）
if supabase is None:
    st.error(
        "Supabase 接続情報が設定されていません。\n"
        "secrets.toml または環境変数 SUPABASE_URL / SUPABASE_KEY を設定してください。"
    )
    st.stop()

if "session_key" not in st.session_state:
    st.session_state["session_key"] = hashlib.sha256(
        ("guest" + str(uuid.uuid4())).encode()
    ).hexdigest()

SESSION_KEY = st.session_state["session_key"]

def add_to_watch_list(code, name, half_retrace, current_price, distance_percent):
    """マイ監視リストに1銘柄追加"""
    if not supabase or not SESSION_KEY:
        st.error("データベース接続またはセッションIDが未確立です。")
        return

    payload = {
        "session_key": SESSION_KEY,
        "list_type": "my",
        "code": str(code).zfill(4),
        "name": name,
        "half_retrace": float(half_retrace) if half_retrace is not None else None,
        "current_price": float(current_price) if current_price is not None else None,
        "distance_percent": float(distance_percent) if distance_percent is not None else None,
    }
def fmt_num(val, fmt="{:.2f}"):
    """None / NaN を '-' にして表示"""
    if val is None:
        return "-"
    try:
        import math
        if isinstance(val, float) and math.isnan(val):
            return "-"
    except Exception:
        pass
    try:
        return fmt.format(val)
    except Exception:
        return str(val)

    try:
        resp = supabase.table("watch_list").insert(payload).execute()
        if resp.data:
            st.success(f"銘柄 **{name}（{code}）** をマイ監視リストに追加しました。")
    except Exception as e:
        st.error(f"マイ監視リストへの登録中にエラーが発生しました: {e}")
        
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
st.header("📌 RシステムPRO 監視リスト")

def load_rsystem_watchlist():
    sources = [
        ("本日", "today"),
        ("2日前", "target2day"),
        ("3日前", "target3day"),
    ]
    all_rows = []
    for label, key in sources:
        try:
            df_part = load_rsystem_data(key)  # あなたが既に使っている読み込み関数
        except Exception:
            continue

        if df_part is None or df_part.empty:
            continue
        df_part = df_part.copy()
        df_part["day_label"] = label
        all_rows.append(df_part)

    if not all_rows:
        return pd.DataFrame()
    return pd.concat(all_rows, ignore_index=True)


# 実データ取得
df_sys = load_rsystem_watchlist()

if df_sys.empty:
    st.info("本日・2日前・3日前の抽出結果がありません。")
else:
    # 🔹 見出し行
    header_cols = st.columns([3, 2, 2, 2, 3, 1])
    with header_cols[0]:
        st.markdown("**日付 / 銘柄**")
    with header_cols[1]:
        st.markdown("**上げ幅の半値押し**")
    with header_cols[2]:
        st.markdown("**現在株価**")
    with header_cols[3]:
        st.markdown("**半値押しまでの距離(%)**")
    with header_cols[4]:
        st.markdown("**株探リンク**")
    with header_cols[5]:
        st.markdown("**マイリスト**")

    st.markdown("<hr>", unsafe_allow_html=True)

    # 🔹 1銘柄ずつ枠付きで表示
    for idx, row in df_sys.iterrows():
        code = row.get("code", "")
        name = row.get("name", "")
        day_label = row.get("day_label", "本日")

        high = row.get("high")
        low = row.get("low")
        half_retrace = (high + low) / 2 if high is not None and low is not None else None

        current_price = row.get("current_price")
        distance = row.get("halfPriceDistancePercent")

        kabutan_chart = f"https://kabutan.jp/stock/chart?code={code}"
        kabutan_fin   = f"https://kabutan.jp/stock/finance?code={code}"
        kabutan_news  = f"https://kabutan.jp/stock/news?code={code}"

        # 枠付きコンテナ
        with st.container():
            st.markdown(
                "<div style='border:1px solid #ddd; border-radius:6px; padding:6px 10px; margin-bottom:6px;'>",
                unsafe_allow_html=True,
            )

            cols = st.columns([3, 2, 2, 2, 3, 1])

            with cols[0]:
                st.markdown(f"**[{day_label}] {name}（{code}）**")
            with cols[1]:
                st.write(fmt_num(half_retrace))
            with cols[2]:
                st.write(fmt_num(current_price, "{:.1f}"))
            with cols[3]:
                st.write(fmt_num(distance, "{:.2f}"))

            with cols[4]:
                st.markdown(
                    f"[チャート]({kabutan_chart})｜"
                    f"[決算]({kabutan_fin})｜"
                    f"[ニュース]({kabutan_news})"
                )

            with cols[5]:
                if st.button("追加", key=f"to_my_{code}_{idx}"):
                    add_to_watch_list(
                        code=code,
                        name=name,
                        half_retrace=half_retrace,
                        current_price=current_price,
                        distance_percent=distance,
                    )
                    st.rerun()

            st.markdown("</div>", unsafe_allow_html=True)
