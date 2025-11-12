import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go


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
VALID_PASSWORDS = ["kuma", "5678"] # ユーザー提供のパスワードを使用

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if not st.session_state["authenticated"]:
    pwd = st.text_input("🔐 パスワードを入力してください", type="password")
    if pwd in VALID_PASSWORDS:
        st.session_state["authenticated"] = True
        st.session_state["authenticated_pwd"] = pwd # 認証済みパスワードを保存
        st.rerun()  # ← 再描画して中身を表示
    elif pwd:
        st.error("パスワードが違います。")
    st.stop()

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
<p style='margin: 6px 0;'>⚠️ 抽出された銘柄のすべてが「ルール1」に該当するわけではございません。</p>
<p style='margin: 6px 0;'>⚠️ ETF など「ルール1」対象外の銘柄も含まれています。</p>
<p style='margin: 6px 0;'>⚠️ **「本日の抽出結果」は約30分ごとに更新されます。**</p>
<p style='margin: 6px 0;'>⚠️ 平日8:30〜9:00の間に短時間のメンテナンスが入ることがあります。</p>
<p style='margin: 6px 0;'>⚠️ 表示されるチャートは昨日までの日足チャートです。</p>
<p style='margin: 6px 0;'>⚠️株式分割や株式併合などがあった場合、過去の株価は分割・併合を考慮しておりません。</p>
</div>
""", unsafe_allow_html=True)


# -------------------------------------------------------------
# キャッシュのTTLを30分 (1800秒) に設定
# -------------------------------------------------------------
@st.cache_data(ttl=1800)  
def load_data(source):
    try:
        url_map = {
            "today": "https://app.kumagai-stock.com/api/highlow/today",
            "yesterday": "https://app.kumagai-stock.com/api/highlow/yesterday",
            "target2day": "https://app.kumagai-stock.com/api/highlow/target2day",
            "target3day": "https://app.kumagai-stock.com/api/highlow/target3day",
            "target4day": "https://app.kumagai-stock.com/api/highlow/target4day",
            "target5day": "https://app.kumagai-stock.com/api/highlow/target5day"
        }
        url = url_map.get(source, url_map["today"])
        res = requests.get(url, timeout=10)
        res.raise_for_status()
        
        # データの型を明示的に変換（high, lowなどが数値であることを保証）
        df = pd.DataFrame(res.json())
        if not df.empty:
            for col in ["high", "low", "current_price"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')
            df.dropna(subset=["high", "low"], inplace=True)
            
        return df
    except Exception as e:
        st.error(f"データの読み込み中にエラーが発生しました: {e}")
        return pd.DataFrame()

# -------------------------------------------------------------
# ラジオボタンの配置
# -------------------------------------------------------------

# --- ページのタブ切り替えUIの追加 ---
st.markdown("<hr>", unsafe_allow_html=True)
page_mode = st.radio(
    "表示モードを選択", 
    ["✅ スクリーナー結果", "📈 マイ監視リスト (1週間限定)"], 
    horizontal=True
)
st.markdown("<hr>", unsafe_allow_html=True)

if page_mode == "✅ スクリーナー結果":
    # 既存のスクリーナーコード（load_dataからチャート表示まで）をここに配置
    # ...
    pass # 既存のコードをここに貼り付ける
elif page_mode == "📈 マイ監視リスト (1週間限定)":
    # 新しい監視リストの表示ロジックを呼び出す
    display_watch_list()


option = st.radio("『高値』付けた日を選んでください", ["本日", "昨日", "2日前", "3日前", "4日前", "5日前"], horizontal=True)

data_source = {
    "本日": "today",
    "昨日": "yesterday",
    "2日前": "target2day",
    "3日前": "target3day",
    "4日前": "target4day",
    "5日前": "target5day"
}[option]

# -------------------------------------------------------------
# アプリ起動時（初回実行時）にキャッシュを強制クリアするロジック
# -------------------------------------------------------------
if 'initial_data_loaded' not in st.session_state:
    st.session_state['initial_data_loaded'] = True
    load_data.clear()
    
# ここで最新データがロードされる
df = load_data(data_source, use_batch=use_batch_with_current)

# 🔽 除外したい銘柄コードを指定
exclude_codes = {"9501", "9432", "7203"}  # 必要に応じて追加

# 🔽 除外処理（コードが含まれていない行のみ残す）
df = df[~df["code"].isin(exclude_codes)]

if df.empty:
    st.info("データがありません。")
else:
    # -------------------------------------------------------------
    # 🌟 共通スタイルを定義 (単一行で定義)
    # -------------------------------------------------------------
    
    # スタイルを定義（共通スタイル）
    button_style = "display: inline-block; padding: 3px 7px; margin-top: 4px; background-color: #f0f2f6; color: #4b4b4b; border: 1px solid #d3d3d3; border-radius: 4px; text-decoration: none; font-size: 11px; font-weight: normal; line-height: 1.2; white-space: nowrap; transition: background-color 0.1s;"
    
    # ホバー時のアクション（共通）
    hover_attr = 'onmouseover="this.style.backgroundColor=\'#e8e8e8\'" onmouseout="this.style.backgroundColor=\'#f0f2f6\'"'

    for _, row in df.iterrows():
        code = row["code"]
        name = row.get("name", "")
        
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
        col_add, col_spacer = st.columns([1, 4]) # ボタンとスペースで横並びにする
        with col_add:
            # 'key' を設定して、複数のボタンが同じ銘柄コードを持つようにする
            if st.button("➕ 監視リストに追加", key=f"add_{code}"):
        
                if not supabase or not SESSION_KEY:
                    st.error("データベース接続またはセッションIDが未確立です。")
                else:
                    # ラジオボタンの選択結果から高値日（監視開始日）を決定
                    today_date = datetime.date.today().strftime('%Y-%m-%d')
                    # 簡略化のため、選択された「〇日前」を今日から引いて 'high_date' とする（実際のスクリーナーの日付ロジックに合わせて要調整）
                    days_ago = {"本日": 0, "昨日": 1, "2日前": 2, "3日前": 3, "4日前": 4, "5日前": 5}.get(option, 0)
                    high_date_calc = (datetime.date.today() - datetime.timedelta(days=days_ago)).strftime('%Y-%m-%d')

                    data_to_insert = {
                        "session_key": SESSION_KEY,
                        "code": code,
                        "name": name,
                        "high_date": high_date_calc, 
                        # 半値押し価格は、現時点で取得できないため、一旦NULLまたは0を送信。
                        # 別途、詳細ページから取得するか、スクリーナーAPIから値を取得する必要があります。
                        "half_value_push": None 
                    }
            
                    # Supabaseへの挿入（テーブル名: watch_list）
                    try:
                        # 重複登録防止のチェックは省略し、とりあえず挿入
                        response = supabase.table("watch_list").insert(data_to_insert).execute()
                
                        # エラーチェック (Supabaseクライアントの挙動による)
                        if response.data:
                            st.success(f"銘柄 **{name}** を監視リストに追加しました！")
                        else:
                            # サーバー側のエラーが発生した場合
                            st.error(f"銘柄 {name} の追加に失敗しました。詳細: {response.error}")

                    except Exception as e:
                        st.error(f"データベースエラーが発生しました: {e}")


        try:
            candle_url = "https://app.kumagai-stock.com/api/candle"
            resp = requests.get(candle_url, params={"code": code})
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
                        hoverinfo="skip"
                    )
                ])
                fig.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    xaxis=dict(visible=False, type="category"),
                    yaxis=dict(visible=False),
                    xaxis_rangeslider_visible=False,
                    height=200,
                    plot_bgcolor='#f8f8f8',  # チャート背景を薄いグレーに
                    paper_bgcolor='#f8f8f8'
                )
                st.plotly_chart(fig, width='stretch', config={"displayModeBar": False, "staticPlot": True})
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
# 監視リスト表示関数 (追加)
# -------------------------------------------------------------
def display_watch_list():
    if not supabase or not SESSION_KEY:
        st.info("データベース接続またはセッションIDが確立されていません。")
        return

    st.markdown("## 📈 マイ監視リスト（1週間限定）", unsafe_allow_html=True)
    
    # 1. データの取得
    try:
        # 現在のセッションキーに紐づいたデータを全て取得
        response = supabase.table("watch_list").select("*").eq("session_key", SESSION_KEY).execute()
        
        if not response.data:
            st.info("監視リストに登録された銘柄はありません。")
            return
            
        watch_df = pd.DataFrame(response.data)

    except Exception as e:
        st.error(f"監視リストの読み込み中にエラーが発生しました: {e}")
        return

    # 2. 掲載期限のチェックとフィルター
    watch_df['high_date'] = pd.to_datetime(watch_df['high_date'])
    today = pd.to_datetime(datetime.date.today())
    
    # 掲載期限（high_date + 7日）を過ぎた銘柄を除外
    watch_df['expiry_date'] = watch_df['high_date'] + pd.Timedelta(days=7)
    active_df = watch_df[watch_df['expiry_date'] >= today].copy()

    if active_df.empty:
        st.info("現在、監視期間内の銘柄はありません。")
        return

    # 3. データの整形と表示
    display_cols = ['code', 'name', 'high_date', 'half_value_push']
    display_df = active_df[display_cols].rename(columns={
        'code': '銘柄コード',
        'name': '銘柄名',
        'high_date': '高値日 (監視開始)',
        'half_value_push': '半値押し価格'
    })
    
    # 日付列のフォーマットを調整
    display_df['高値日 (監視開始)'] = display_df['高値日 (監視開始)'].dt.strftime('%Y-%m-%d')
    
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True
    )
    st.caption("※掲載期間は高値日（監視開始日）から7日間です。期限切れの銘柄は自動で非表示になります。")

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