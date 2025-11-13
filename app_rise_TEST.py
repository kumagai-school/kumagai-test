import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go


def _normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df

    # code ゼロ埋め
    if "code" in df.columns:
        df["code"] = df["code"].astype(str).str.zfill(4)

    # 数値っぽい列を変換
    for col in ["high", "low", "倍率", "current_price"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df



# =============================================================
# 🔑 Supabase 接続とセッションキーの初期化 (追加)
# =============================================================
from supabase import create_client, Client # 1. import 追加
import hashlib
import uuid
import datetime

# 接続クライアントを初期化（キャッシュで効率化）
@st.cache_resource
def init_connection():
    try:
        # secrets.toml から情報を読み込む
        url: str = st.secrets["supabase"]["url"]
        key: str = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        # st.error(f"Supabase接続エラー: secrets.tomlを確認してください。{e}")
        return None

supabase: Client = init_connection()

# ユーザー識別キー（共有パスワード利用時の代替策）
if 'session_key' not in st.session_state:
    # 認証済みセッションごとに一意なキーを生成
    unique_id = uuid.uuid4().hex
    # 共有パスワードを利用するため、セッションとパスワードを組み合わせて一意性を高める
    auth_key = st.session_state.get("authenticated_pwd", "default")
    st.session_state['session_key'] = hashlib.sha256((unique_id + auth_key).encode()).hexdigest()

# DB操作で使用するキー
SESSION_KEY = st.session_state.get('session_key', None)
# =============================================================



# ✅ 許可するパスワードを複数指定（リスト形式）
VALID_USERS = {
    "nao":  "admin",
    "kuma":  "member",
    "5678":  "member",
}# ユーザー提供のパスワードを使用

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
    st.session_state["role"] = None

if not st.session_state["authenticated"]:
    pwd = st.text_input("🔐 パスワードを入力してください", type="password")
    if pwd in VALID_USERS:
        st.session_state["authenticated"] = True
        st.session_state["authenticated_pwd"] = pwd
        st.session_state["role"] = VALID_USERS[pwd]   # ← 権限を付与
        # ✅ 認証後に session_key を作る（pwd を材料にする）
        unique_id = uuid.uuid4().hex
        st.session_state['session_key'] = hashlib.sha256((unique_id + pwd).encode()).hexdigest()
        st.rerun()
    elif pwd:
        st.error("パスワードが違います。")
    st.stop()

SESSION_KEY = st.session_state.get('session_key')
use_batch_with_current = (st.session_state.get("role") == "admin")

st.set_page_config(page_title="RシステムPRO", layout="wide")

st.markdown("""
    <h1 style='text-align:left; color:#2E86C1; font-size:26px; line-height:1.4em;'>
        ＲシステムPRO
    </h1>
    <h1 style='text-align:left; color:#2E86C1; font-size:20px; line-height:1.4em;'>
        『ルール1』スクリーニングシステム
    </h1>
    <h1 style='text-align:left; color:#000000; font-size:15px; line-height:1.4em;'>
        「2週間以内で1.3～2倍に暴騰した銘柄」を抽出しています。
    </h1>
""", unsafe_allow_html=True)

st.markdown("""
<div style='
    background-color: #ffffff;
    padding: 12px;
    border-radius: 8px;
    font-size: 13px;
    color: #000000;
    margin-bottom: 20px;
    line-height: 1.6em;
'>
<p>銘柄名をクリックすると、「直近高値」「高値から過去2週間以内の安値」が表示されます。<br>
表示された画面下の「計算する」をクリックすると、「上昇率」「上げ幅」「上げ幅の半値」「上げ幅の半値押し」が算出されます。<br>
銘柄選別でご活用下さいませ。</p>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style='
    border: 1px solid red;
    background-color: #ffffff;
    padding: 12px;
    border-radius: 8px;
    font-size: 13px;
    color: #b30000;
    margin-bottom: 20px;
    line-height: 1.3em;
'>
<p style='margin: 6px 0;'⚠️ 抽出された銘柄のすべてが「ルール1」に該当するわけではございません。</p>
<p style='margin: 6px 0;'>⚠️ ETF など「ルール1」対象外の銘柄も含まれています。</p>
<p style='margin: 6px 0;'>⚠️ **「本日の抽出結果」は約30分ごとに更新されます。**</p>
<p style='margin: 6px 0;'>⚠️ 平日8:30〜9:00の間に短時間のメンテナンスが入ることがあります。</p>
<p style='margin: 6px 0;'>⚠️ 表示されるチャートは昨日までの日足チャートです。</p>
<p style='margin: 6px 0;'>⚠️株式分割や株式併合などがあった場合、過去の株価は分割・併合を考慮しておりません。</p>
</div>
""", unsafe_allow_html=True)

use_batch_with_current = st.session_state.get("role") == "admin"

# -------------------------------------------------------------
# 監視リスト表示関数 (追加)
# -------------------------------------------------------------
def display_watch_list():
    if not supabase or not SESSION_KEY:
        st.info("データベース接続またはセッションIDが確立されていません。")
        return

    st.markdown("## 📈 マイ監視リスト（1週間限定）")

    try:
        response = supabase.table("watch_list").select("*").eq("session_key", SESSION_KEY).execute()
        if not response.data:
            st.info("監視リストに登録された銘柄はありません。")
            return
        watch_df = pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"監視リストの読み込み中にエラーが発生しました: {e}")
        return

    watch_df['high_date'] = pd.to_datetime(watch_df['high_date'])
    today = pd.to_datetime(datetime.date.today())
    watch_df['expiry_date'] = watch_df['high_date'] + pd.Timedelta(days=7)
    active_df = watch_df[watch_df['expiry_date'] >= today].copy()
    if active_df.empty:
        st.info("現在、監視期間内の銘柄はありません。")
        return

    # 👇 列名修正（current_price の末尾カンマを削除）
    display_cols = ['code', 'name', 'high_date', 'half_value_push', 'current_price']
    for c in display_cols:
        if c not in active_df.columns:
            active_df[c] = None

    display_df = active_df[display_cols].rename(columns={
        'code': '銘柄コード',
        'name': '銘柄名',
        'high_date': '高値日 (監視開始)',
        'half_value_push': '半値押し価格',
        'current_price': '現在値',
    })
    display_df['高値日 (監視開始)'] = pd.to_datetime(display_df['高値日 (監視開始)']).dt.strftime('%Y-%m-%d')

    st.dataframe(display_df, use_container_width=True, hide_index=True)
    st.caption("※掲載期間は高値日（監視開始日）から7日間です。期限切れの銘柄は自動で非表示になります。")




# -------------------------------------------------------------
# キャッシュのTTLを30分 (1800秒) に設定
# -------------------------------------------------------------
@st.cache_data(ttl=1800)
def load_data(source: str, use_batch: bool = False) -> pd.DataFrame:
    try:
        if use_batch:
            url = "https://app.kumagai-stock.com/api/highlow/batch"
        else:
            url_map = {
                "today": "https://app.kumagai-stock.com/api/highlow/today",
                "yesterday": "https://app.kumagai-stock.com/api/highlow/yesterday",
                "target2day": "https://app.kumagai-stock.com/api/highlow/target2day",
                "target3day": "https://app.kumagai-stock.com/api/highlow/target3day",
                "target4day": "https://app.kumagai-stock.com/api/highlow/target4day",
                "target5day": "https://app.kumagai-stock.com/api/highlow/target5day",
            }
            url = url_map.get(source, url_map["today"])

        # ★ SESSIONではなく、ふつうの requests.get を使う
        res = requests.get(url, timeout=(3, 15))
        res.raise_for_status()
        
        # JSON → DataFrame
        df = pd.DataFrame(res.json())
        df = _normalize_schema(df)  # ← これを使う場合は、上に関数定義を置いてください

        # high/low 無ければ表示不能なので即座に空を返す
        if df is None or df.empty or not {"high", "low"} <= set(df.columns):
            return pd.DataFrame()

        # 倍率が無ければ計算して補う
        if "倍率" not in df.columns:
            df["倍率"] = (df["high"] / df["low"]).round(2)

        # 必須列の欠損は落とす
        df = df.dropna(subset=["high", "low"])

        return df

    except Exception as e:
        st.error(f"データの読み込み中にエラーが発生しました: {e}")
        return pd.DataFrame()

# -------------------------------------------------------------
# ラジオボタンの配置
# -------------------------------------------------------------

# ===== ここより上に display_watch_list() と load_data() の定義がある前提 =====

# --- ページ切替（先に分岐して、監視リストだけ表示するときは即終了） ---
st.markdown("<hr>", unsafe_allow_html=True)
page_mode = st.radio("表示モードを選択", ["✅ スクリーナー結果", "📈 マイ監視リスト (1週間限定)"], horizontal=True)
st.markdown("<hr>", unsafe_allow_html=True)

if page_mode == "📈 マイ監視リスト (1週間限定)":
    display_watch_list()
    st.stop()  # ← 以降のスクリーナー処理に進まない

# --- ここからスクリーナー処理 ---
option = st.radio("『高値』付けた日を選んでください", ["本日", "昨日", "2日前", "3日前", "4日前", "5日前"], horizontal=True)
data_source = {
    "本日": "today",
    "昨日": "yesterday",
    "2日前": "target2day",
    "3日前": "target3day",
    "4日前": "target4day",
    "5日前": "target5day",
}[option]

# 初回はキャッシュクリア（任意）
if "initial_data_loaded" not in st.session_state:
    st.session_state["initial_data_loaded"] = True
    load_data.clear()

# ★ ここで必ず df を定義してから、以降で参照する
df = load_data(data_source, use_batch=use_batch_with_current)

# 空や None の場合はここで終了（未定義参照を防ぐ）
if df is None or df.empty:
    st.info("データがありません。")
    st.stop()

# code 列がある場合のみ除外フィルタを適用
exclude_codes = {"9501", "9432", "7203"}
if "code" in df.columns:
    df = df[~df["code"].isin(exclude_codes)]
else:
    st.warning("銘柄コード列が見つからないため、除外リストを適用しませんでした。")

# 表示に必須の列があるか確認
required_for_display = {"high", "low"}
missing = required_for_display - set(df.columns)
if missing:
    st.warning(f"必要な列が不足しています: {', '.join(sorted(missing))}")
    st.stop()

# --- ここから per-row 表示ループ ---
for _, row in df.iterrows():
    code = row.get("code", "")
    name = row.get("name", "")
    # ...（ここに銘柄名リンク、ボタン群、columns、チャートの try-except などを配置）
        
    # リンク先のURLを定義
    code_link = f"https://kabuka-check-app.onrender.com/?code={code}"
    
    # リンク先：決算・企業情報（株探）
    kabutan_finance_url = f"https://kabutan.jp/stock/finance?code={code}"
        
    # リンク先：ニュース（株探）
    kabutan_news_url = f"https://kabutan.jp/stock/news?code={code}"
    
    multiplier_html = f"<span style='color:green; font-weight:bold;'>{row['倍率']:.2f}倍</span>"

    st.markdown("<hr style='border-top: 2px solid #ccc;'>", unsafe_allow_html=True)

    st.markdown(f"""
        <div style='font-size:18px; line-height:1.6em;'>
            <b><a href="{code_link}" target="_blank">{name}（{code}）</a></b>　
            {multiplier_html}<br>
            📉 安値 ： {row["low"]}（{row["low_date"]}）<br>
            📈 高値 ： {row["high"]}（{row["high_date"]}）
        </div>
    """, unsafe_allow_html=True)
        
    # 1. 詳細・半値押し計算へ のボタン (単一行f-string)
    detail_button_html = f'<a href="{code_link}" target="_blank" style="{button_style}" {hover_attr} title="別ページで詳細な計算結果とチャートを確認します。">詳細・半値押し計算へ</a>'
        
    # 2. 決算・企業情報（株探） のボタン (単一行f-string)
    kabutan_finance_button_html = f'<a href="{kabutan_finance_url}" target="_blank" style="{button_style} margin-left: 10px;" {hover_attr} title="株探の企業情報ページへ移動し、決算情報や株価を確認します。">決算・企業情報（株探）</a>'
        
    # 3. ニュース（株探） のボタン (単一行f-string)
    kabutan_news_button_html = f'<a href="{kabutan_news_url}" target="_blank" style="{button_style} margin-left: 10px;" {hover_attr} title="株探のニュースページへ移動し、最新の情報を確認します。">ニュース（株探）</a>'
        
    # 3つのボタンを同じブロックでマークダウンとして表示することで並べる
    st.markdown(detail_button_html + kabutan_finance_button_html + kabutan_news_button_html, unsafe_allow_html=True)


# -------------------------------------------------------------
# 4. 監視リストに追加機能の追加
# -------------------------------------------------------------
# 監視リスト追加ボタン＋スペーサ
col_add, col_spacer = st.columns([1, 4])

with col_add:
    if st.button("➕ 監視リストに追加", key=f"add_{code}"):
        if not supabase or not SESSION_KEY:
            st.error("データベース接続またはセッションIDが未確立です。")
        else:
            days_ago = {"本日": 0, "昨日": 1, "2日前": 2, "3日前": 3, "4日前": 4, "5日前": 5}.get(option, 0)
            high_date_calc = (datetime.date.today() - datetime.timedelta(days=days_ago)).strftime('%Y-%m-%d')

            data_to_insert = {
                "session_key": SESSION_KEY,
                "code": code,
                "name": name,
                "high_date": high_date_calc,
                "half_value_push": None,
            }

            try:
                response = supabase.table("watch_list").insert(data_to_insert).execute()
                if response.data:
                    st.success(f"銘柄 **{name}** を監視リストに追加しました！")
                else:
                    st.error(f"銘柄 {name} の追加に失敗しました。詳細: {response.error}")
            except Exception as e:
                st.error(f"データベースエラーが発生しました: {e}")

with col_spacer:
    st.empty()

# ← columns ブロックを抜けた“ここ”でチャート描画
try:
    candle_url = "https://app.kumagai-stock.com/api/candle"
    resp = requests.get(candle_url, params={"code": code}, timeout=5)
    resp.raise_for_status()
    chart_data = resp.json().get("data", [])

    if chart_data:
        df_chart = pd.DataFrame(chart_data)
        df_chart["date_str"] = pd.to_datetime(df_chart["date"]).dt.strftime("%Y-%m-%d")

        fig = go.Figure(data=[
            go.Candlestick(
                x=df_chart["date_str"],
                open=df_chart["open"],
                high=df_chart["high"],
                low=df_chart["low"],
                close=df_chart["close"],
                increasing_line_color='red',
                decreasing_line_color='blue',
                hoverinfo="skip",
            )
        ])
        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(visible=False, type="category"),
            yaxis=dict(visible=False),
            xaxis_rangeslider_visible=False,
            height=200,
            plot_bgcolor='#f8f8f8',
            paper_bgcolor='#f8f8f8',
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "staticPlot": True})
    else:
        st.caption("（チャートデータなし）")
except Exception as e:
    st.caption(f"（エラー: {e}）")

st.markdown("<hr style='border-top: 2px solid #ccc;'>", unsafe_allow_html=True)

st.markdown("""
<div style='
    border: 1px solid red;
    background-color: #ffffff;
    padding: 12px;
    border-radius: 8px;
    font-size: 13px;
    color: #b30000;
    margin-bottom: 20px;
    line-height: 1.6em;
'>
<p>※ピックアップチャートの銘柄については、あくまで「ルール1」銘柄のレッスンとなります。</p>
<p>※特定の取引を推奨するものではなく、銘柄の助言ではございません。</p>
<p>※本サービスは利益を保証するものではなく、投資にはリスクが伴います。投資の際は自己責任でよろしくお願いいたします。</p>
</div>
""", unsafe_allow_html=True)



# -------------------------------------------------------------


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