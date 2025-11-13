import os
import streamlit as st
from supabase import create_client, Client
import pandas as pd
import requests
import uuid
import hashlib
from requests.exceptions import ReadTimeout, RequestException


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
def load_batch_current() -> pd.DataFrame:
    """現在値付きの batch を 1回だけ取得してキャッシュ"""
    batch_url = "https://app.kumagai-stock.com/api/highlow/batch"
    try:
        res = requests.get(batch_url, timeout=(3, 7))  # 接続3秒 + 読み取り7秒
        res.raise_for_status()
        df = pd.DataFrame(res.json())
        if df.empty:
            return pd.DataFrame()
        # 必要な列だけ残す
        cols = ["code", "current_price", "halfPriceDistancePercent"]
        return df[[c for c in cols if c in df.columns]].copy()
    except ReadTimeout:
        st.warning("現在値の取得がタイムアウトしました。半値押しは表示されますが、現在値・距離は空欄になります。")
        return pd.DataFrame()
    except RequestException as e:
        st.warning(f"現在値の取得に失敗しました: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def load_rsystem_data(source_key: str) -> pd.DataFrame:
    """
    本日・2日前・3日前の抽出結果に、
    可能なら batch から現在値をマージして返す。
    batch が失敗してもページは落とさない。
    """
    url_map = {
        "today":      "https://app.kumagai-stock.com/api/highlow/today",
        "target2day": "https://app.kumagai-stock.com/api/highlow/target2day",
        "target3day": "https://app.kumagai-stock.com/api/highlow/target3day",
    }
    base_url = url_map.get(source_key, url_map["today"])

    # ① ベース（高値・安値など）
    try:
        res = requests.get(base_url, timeout=(3, 15))  # ← url → base_url に修正
        res.raise_for_status()
        df_base = pd.DataFrame(res.json())             # ← base_res → res に修正
    except Exception as e:
        st.error(f"抽出データの取得に失敗しました: {e}")
        return pd.DataFrame()

    if df_base.empty:
        return df_base

    # code を文字列ゼロ埋め
    df_base["code"] = df_base["code"].astype(str).str.zfill(4)

    # ② batch で現在値などを取得（取れたらラッキー）
    try:
        batch_url = "https://app.kumagai-stock.com/api/highlow/batch"
        # ★ 読み込みタイムアウトを伸ばす（30〜40秒くらい）
        batch_res = requests.get(batch_url, timeout=(5, 40))
        batch_res.raise_for_status()

        df_batch = pd.DataFrame(batch_res.json())
        if not df_batch.empty:
            df_batch["code"] = df_batch["code"].astype(str).str.zfill(4)
            df_batch = df_batch[["code", "current_price", "halfPriceDistancePercent"]]

            # code で LEFT JOIN
            df = df_base.merge(df_batch, on="code", how="left")
        else:
            df = df_base.copy()
            df["current_price"] = None
            df["halfPriceDistancePercent"] = None

    except Exception as e:
        # ★ ここで全体を落とさないのがポイント
        st.warning(f"現在値の取得に失敗しました（{e}）。高値・安値のみで表示します。")
        df = df_base.copy()
        df["current_price"] = None
        df["halfPriceDistancePercent"] = None

    return df


def load_rsystem_watchlist() -> pd.DataFrame:
    """RシステムPRO監視リスト用に、本日・2日前・3日前をまとめて取得する"""
    sources = [
        ("本日", "today"),
        ("2日前", "target2day"),
        ("3日前", "target3day"),
    ]
    all_rows = []

    for label, key in sources:
        try:
            df_part = load_rsystem_data(key)  # 既にある読み込み関数を利用
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
st.markdown("### 📌 マイ監視リスト")
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
# 📌 RシステムPRO 監視リスト（本日 + 2日前 + 3日前）
# ==============================================================

st.markdown("""
    <style>
        .watchbox {
            border: 1px solid #d0d0d0;
            border-radius: 8px;
            padding: 6px 12px;
            margin-bottom: 10px;
            background-color: #fafafa;
        }
        .watchtext {
            font-size: 12px;
            color: #333333;
            font-family: "Segoe UI", "Helvetica Neue", "Arial";
        }
        .watchheader {
            font-size: 12px;
            font-weight: 600;
            color: #444444;
        }
        .watchlink {
            font-size: 11px;
            color: #1f4e79;
        }
        .addbutton {
            font-size: 10px !important;
            padding: 2px 6px !important;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown("### 📌 RシステムPRO 監視リスト（本日＋2日前＋3日前）")

df_sys = load_rsystem_watchlist()

if df_sys.empty:
    st.info("本日・2日前・3日前の抽出結果がありません。")
else:

    # 見出し行
    cols_header = st.columns([3, 2, 2, 2, 3, 1])
    headers = ["日付 / 銘柄", "半値押し株価", "現在値", "対半値押し比(%)", "株探", "追加"]
    for c, h in zip(cols_header, headers):
        with c:
            st.markdown(f"<span class='watchheader'>{h}</span>", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    # 銘柄ごとに表示
    for idx, row in df_sys.iterrows():
        code = row.get("code", "")
        name = row.get("name", "")
        day_label = row.get("day_label", "")

        high = row.get("high")
        low = row.get("low")

        half_retrace = (high + low) / 2 if high and low else None
        current_price = row.get("current_price")
        distance = row.get("halfPriceDistancePercent")

        # 株探リンク
        chart_url = f"https://kabutan.jp/stock/chart?code={code}"
        fin_url   = f"https://kabutan.jp/stock/finance?code={code}"
        news_url  = f"https://kabutan.jp/stock/news?code={code}"

        # 🔽 枠で囲む
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

　　　　    # ✅ 枠付きのコンテナで中身を全部包む
        with st.container(border=True):   # ★ ここがポイント
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

