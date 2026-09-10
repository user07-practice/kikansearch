import sqlite3
import pandas as pd
import streamlit as st
import requests
import re
import os

# =========================
# データベースの場所
# =========================

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "books.db"
)

def extract_volume_number(title):
    """
    書籍タイトルから巻数を取り出す。

    例:
    ダンダダン 24
    ダンダダン 24巻
    ダンダダン 第24巻
    ダンダダン（24）
    """

    patterns = [
        r"第\s*(\d+)\s*巻",
        r"(\d+)\s*巻",
        r"[（(]\s*(\d+)\s*[）)]",
        r"\s(\d+)$"
    ]

    for pattern in patterns:
        match = re.search(pattern, title)

        if match:
            return int(match.group(1))

    return None



# =========================
# データベース
# =========================

def init_db():

    print()
    print("===== Streamlit データベース確認 =====")
    print(f"読み込むDB: {DB_PATH}")
    print(f"DBファイル存在: {os.path.exists(DB_PATH)}")
    print("=====================================")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT,
            series_name TEXT,
            status TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()



def get_books():
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query(
        "SELECT id, title, author, series_name, status FROM books",
        conn
    )

    conn.close()
    return df


def add_book(title, author, series_name, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO books
        (title, author, series_name, status)
        VALUES (?, ?, ?, ?)
        """,
        (title, author, series_name, status)
    )

    conn.commit()
    conn.close()


def delete_book(book_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM books WHERE id = ?",
        (book_id,)
    )

    conn.commit()
    conn.close()


# =========================
# ISBNを整える
# =========================

def normalize_isbn(isbn):
    """ISBNのハイフンや空白を取り除く"""

    isbn = str(isbn)
    isbn = isbn.replace("-", "")
    isbn = isbn.replace(" ", "")
    isbn = isbn.replace("　", "")

    return isbn.strip()


# =========================
# ISBNを整える
# =========================

def normalize_isbn(isbn):
    """ISBNのハイフン・空白を取り除く"""

    isbn = str(isbn)
    isbn = isbn.replace("-", "")
    isbn = isbn.replace(" ", "")
    isbn = isbn.replace("　", "")

    return isbn.strip()


# =========================
# 国立国会図書館サーチ
# =========================

def search_ndl(title=None, isbn=None, max_results=20):
    """
    国立国会図書館サーチ SRU APIで書籍を検索する
    """

    url = "https://ndlsearch.ndl.go.jp/api/sru"

    # -------------------------
    # 検索条件
    # -------------------------

    if isbn:
        query = f'isbn="{normalize_isbn(isbn)}"'

    elif title:
        title = re.sub(r"\s+", " ", title).strip()

        if not title:
            return []

        query = f'title="{title}"'

    else:
        return []

    params = {
        "operation": "searchRetrieve",
        "version": "1.2",
        "query": query,
        "maximumRecords": min(max_results, 30),
        "recordPacking": "xml",
        "recordSchema": "dcndl"
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=30
        )

        response.raise_for_status()

    except requests.RequestException as e:
        st.error(
            f"国立国会図書館サーチへの接続に失敗しました: {e}"
        )
        return []

    # -------------------------
    # XML解析
    # -------------------------

    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(response.content)

    except ET.ParseError as e:
        st.error(
            f"NDLから取得したXMLを解析できませんでした: {e}"
        )
        return []

    # XML名前空間
    NS = {
        "srw": "http://www.loc.gov/zing/srw/",
        "dc": "http://purl.org/dc/elements/1.1/",
        "dcterms": "http://purl.org/dc/terms/",
        "dcndl": "http://ndl.go.jp/dcndl/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    }

    results = []

    # -------------------------
    # recordDataを1件ずつ処理
    # -------------------------

    for record_data in root.findall(
        ".//srw:recordData",
        NS
    ):

        bib = record_data.find(
            ".//dcndl:BibResource",
            NS
        )

        if bib is None:
            continue

        # =========================
        # タイトル
        # =========================

        title_value = ""

        title_element = bib.find(
            "dcterms:title",
            NS
        )

        if title_element is not None:
            title_value = (
                title_element.text or ""
            ).strip()

        # dcterms:titleがなければdc:title
        if not title_value:

            dc_title = bib.find(
                "dc:title",
                NS
            )

            if dc_title is not None:

                value_element = dc_title.find(
                    ".//rdf:value",
                    NS
                )

                if value_element is not None:
                    title_value = (
                        value_element.text or ""
                    ).strip()

                elif dc_title.text:
                    title_value = (
                        dc_title.text or ""
                    ).strip()

        if not title_value:
            continue

        # =========================
        # シリーズ名
        # =========================

        series_name = ""

        series_element = bib.find(
            "dcndl:seriesTitle",
            NS
        )

        if series_element is not None:
            series_name = (
                series_element.text or ""
            ).strip()

        # =========================
        # 巻数
        # =========================

        volume = ""

        volume_element = bib.find(
            "dcndl:volume",
            NS
        )

        if volume_element is not None:
            volume = (
                volume_element.text or ""
            ).strip()

        # =========================
        # 著者
        # =========================

        author_value = ""

        creator = bib.find(
            "dc:creator",
            NS
        )

        if creator is not None:

            author_value = (
                creator.text or ""
            ).strip()

        if not author_value:

            creator = bib.find(
                "dcterms:creator",
                NS
            )

            if creator is not None:

                name_element = creator.find(
                    ".//foaf:name",
                    NS
                )

                if name_element is not None:
                    author_value = (
                        name_element.text or ""
                    ).strip()

        # =========================
        # 出版社
        # =========================

        publisher_value = ""

        publisher = bib.find(
            "dc:publisher",
            NS
        )

        if publisher is not None:

            publisher_value = (
                publisher.text or ""
            ).strip()

        if not publisher_value:

            publisher = bib.find(
                "dcterms:publisher",
                NS
            )

            if publisher is not None:

                name_element = publisher.find(
                    ".//foaf:name",
                    NS
                )

                if name_element is not None:
                    publisher_value = (
                        name_element.text or ""
                    ).strip()

        # =========================
        # 発売日
        # =========================

        published_date = ""

        issued = bib.find(
            "dcterms:issued",
            NS
        )

        if issued is not None:
            published_date = (
                issued.text or ""
            ).strip()

        # =========================
        # ISBN
        # =========================

        isbn_value = ""

        for identifier in bib.findall(
            "dcterms:identifier",
            NS
        ):

            value = (
                identifier.text or ""
            ).strip()

            clean_value = normalize_isbn(value)

            if len(clean_value) in (10, 13):

                isbn_value = clean_value
                break

        # =========================
        # 結果を保存
        # =========================

        results.append({
            "title": title_value,
            "author": author_value or "不明",
            "series_name": series_name,
            "volume": volume,
            "publisher": publisher_value,
            "published_date": published_date,
            "isbn10": "",
            "isbn13": isbn_value
        })

    return results




# =========================
# ISBN検索
# =========================

def search_book_by_isbn(isbn):
    """
    ISBNからopenBDで書籍情報を取得する
    """

    def extract_volume_number(title):
        """
        書籍タイトルから巻数を推測する。

        例:
            ダンダダン 24
            ダンダダン 24巻
            ダンダダン 第24巻
            ダンダダン（24）
        """

        patterns = [
            r"第\s*(\d+)\s*巻",
            r"(\d+)\s*巻",
            r"[（(]\s*(\d+)\s*[）)]",
            r"\s(\d+)$"
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                title,
                re.IGNORECASE
            )

            if match:
                return int(
                    match.group(1)
                )

        return None

    isbn = normalize_isbn(isbn)

    if not isbn:
        return []

    url = f"https://api.openbd.jp/v1/get"

    params = {
        "isbn": isbn
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

    except requests.RequestException as e:

        st.error(
            f"openBDへの接続に失敗しました: {e}"
        )

        return []

    except ValueError:

        st.error(
            "openBDから正しいデータを取得できませんでした。"
        )

        return []

    if not data or data[0] is None:
        return []

    book = data[0]

    summary = book.get("summary", {})

    title = summary.get("title", "")
    author = summary.get("author", "")
    publisher = summary.get("publisher", "")
    pubdate = summary.get("pubdate", "")

    if not title:
        return []

    return [{
        "title": title,
        "author": author or "不明",
        "series_name": "",
        "publisher": publisher or "",
        "published_date": pubdate or "",
        "isbn10": "",
        "isbn13": isbn
    }]

def split_title_and_volume(text):
    """
    「ダンダダン 23」
    「ダンダダン 23巻」
    「ダンダダン 第23巻」
    などを

    タイトル = ダンダダン
    巻数 = 23

    に分ける。
    """

    text = re.sub(r"\s+", " ", text).strip()

    patterns = [
        r"^(.+?)\s+第(\d+)\s*巻$",
        r"^(.+?)\s+(\d+)\s*巻$",
        r"^(.+?)\s+(\d+)$",
    ]

    for pattern in patterns:

        match = re.match(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:

            return (
                match.group(1).strip(),
                int(match.group(2))
            )

    return text, None



# =========================
# タイトル検索
# =========================

def search_book_by_title(title):

    title = title.strip()

    if not title:
        return []

    # -------------------------
    # タイトルと巻数を分離
    # -------------------------

    search_title, target_volume = split_title_and_volume(title)

    # -------------------------
    # NDLではタイトルだけ検索
    # -------------------------

    results = search_ndl(
        title=search_title,
        max_results=30
    )

    if not results:
        return []

    search_word = search_title.lower()

    # -------------------------
    # 検索結果の順位付け
    # -------------------------

    def score_book(book):

        book_title = book["title"].lower()

        score = 0

        # タイトル一致
        if book_title == search_word:
            score += 100

        elif book_title.startswith(search_word):
            score += 80

        elif search_word in book_title:
            score += 60

        else:
            score += 10

        # -------------------------
        # 巻数が指定されている場合
        # -------------------------

        if target_volume is not None:

            volume = str(
                book.get("volume", "")
            ).strip()

            # NDLから取得した巻数と一致
            if volume == str(target_volume):
                score += 1000

            # タイトルから巻数を取得
            title_volume = extract_volume_number(
                book["title"]
            )

            if title_volume == target_volume:
                score += 900

        # シリーズ名あり
        if book.get("series_name"):
            score += 5

        # 巻数あり
        if book.get("volume"):
            score += 5

        return score

    results.sort(
        key=score_book,
        reverse=True
    )

    return results[:30]




# =========================
# Streamlit画面
# =========================

st.set_page_config(
    page_title="私の本棚アプリ",
    page_icon="📚"
)

st.title("📚 私の本棚アプリ")

init_db()


# =========================
# サイドバー
# =========================

st.sidebar.header("✨ 本の登録")


# セッション状態
if "search_results" not in st.session_state:
    st.session_state.search_results = []

if "auto_title" not in st.session_state:
    st.session_state.auto_title = ""

if "auto_author" not in st.session_state:
    st.session_state.auto_author = ""

if "auto_series" not in st.session_state:
    st.session_state.auto_series = ""

if "auto_isbn" not in st.session_state:
    st.session_state.auto_isbn = ""


# =========================
# 検索方法
# =========================

search_type = st.sidebar.radio(
    "検索方法",
    ["ISBNで検索", "タイトルで検索"]
)


# =========================
# ISBN検索
# =========================

if search_type == "ISBNで検索":

    isbn_input = st.sidebar.text_input(
        "ISBN",
        placeholder="9784041176085"
    )

    if st.sidebar.button(
        "🔍 ISBNから検索"
    ):

        if not isbn_input.strip():

            st.sidebar.error(
                "ISBNを入力してください。"
            )

        else:

            with st.spinner(
                "本を検索しています..."
            ):

                results = search_book_by_isbn(
                    isbn_input
                )

            st.session_state.search_results = results

            if results:
                st.sidebar.success(
                    f"{len(results)}件見つかりました！"
                )
            else:
                st.sidebar.error(
                    "本が見つかりませんでした。"
                )


# =========================
# タイトル検索
# =========================

else:

    title_input = st.sidebar.text_input(
        "本のタイトル",
        placeholder="例：薬屋のひとりごと"
    )

    if st.sidebar.button(
        "🔍 タイトルから検索"
    ):

        if not title_input.strip():

            st.sidebar.error(
                "タイトルを入力してください。"
            )

        else:

            with st.spinner(
                "本を検索しています..."
            ):

                results = search_book_by_title(
                    title_input
                )

            st.session_state.search_results = results

            if results:
                st.sidebar.success(
                    f"{len(results)}件見つかりました！"
                )
            else:
                st.sidebar.error(
                    "本が見つかりませんでした。"
                )


# =========================
# 検索結果
# =========================

if st.session_state.search_results:

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔎 検索結果")

    results = st.session_state.search_results

    options = []

    options = []

    for i, book in enumerate(results):

        display_parts = []

        # タイトル
        if book.get("title"):
            display_parts.append(
                f"タイトル: {book['title']}"
            )

        # シリーズ名
        if book.get("series_name"):
            display_parts.append(
                f"シリーズ: {book['series_name']}"
            )

        # 巻数
        if book.get("volume"):
            display_parts.append(
                f"巻数: {book['volume']}"
            )

        # 著者
        if book.get("author"):
            display_parts.append(
                f"著者: {book['author']}"
            )

        display_text = " / ".join(display_parts)

        options.append(display_text)

    selected_index = st.sidebar.selectbox(
        "登録したい本を選択",
        range(len(options)),
        format_func=lambda x: options[x]
    )

    selected_book = results[selected_index]

    st.sidebar.write("### 選択した本")

    st.sidebar.write(
        f"**タイトル:** {selected_book['title']}"
    )

    st.sidebar.write(
        f"**著者:** {selected_book['author']}"
    )

    if selected_book["publisher"]:

        st.sidebar.write(
            f"**出版社:** {selected_book['publisher']}"
        )

    if selected_book["published_date"]:

        st.sidebar.write(
            f"**発売日:** {selected_book['published_date']}"
        )

    if selected_book["isbn13"]:

        st.sidebar.write(
            f"**ISBN:** {selected_book['isbn13']}"
        )

    if selected_book["series_name"]:

        st.sidebar.write(
            f"**シリーズ:** {selected_book['series_name']}"
        )

    if st.sidebar.button(
        "⬇️ この本の情報を入力欄に入れる"
    ):

        st.session_state.auto_title = (
            selected_book["title"]
        )

        st.session_state.auto_author = (
            selected_book["author"]
        )

        st.session_state.auto_series = (
            selected_book["series_name"]
        )

        st.session_state.auto_isbn = (
            selected_book["isbn13"]
            or selected_book["isbn10"]
        )

        st.sidebar.success(
            "本の情報を入力欄にセットしました！"
        )


# =========================
# 手動確認・修正
# =========================

st.sidebar.markdown("---")

st.sidebar.subheader(
    "📝 本の情報を確認"
)

title = st.sidebar.text_input(
    "タイトル（必須）",
    value=st.session_state.auto_title
)

author = st.sidebar.text_input(
    "著者",
    value=st.session_state.auto_author
)

series_name = st.sidebar.text_input(
    "シリーズ名",
    value=st.session_state.auto_series
)

status = st.sidebar.selectbox(
    "読書ステータス",
    ["読みたい本", "読んだ本"]
)


# =========================
# 本棚へ登録
# =========================

if st.sidebar.button(
    "📥 この内容で本棚に登録！"
):

    if title.strip():

        add_book(
            title,
            author,
            series_name,
            status
        )

        st.success(
            f"「{title}」を本棚に保存しました！"
        )

        st.session_state.auto_title = ""
        st.session_state.auto_author = ""
        st.session_state.auto_series = ""
        st.session_state.auto_isbn = ""
        st.session_state.search_results = []

        st.rerun()

    else:

        st.sidebar.error(
            "タイトルを入力してください。"
        )


# =========================
# 本棚
# =========================

st.header("現在の私の本棚")

df = get_books()

if not df.empty:

    df_display = df.rename(
        columns={
            "title": "タイトル",
            "author": "著者",
            "series_name": "シリーズ名",
            "status": "状態"
        }
    )

    st.dataframe(
        df_display[
            [
                "タイトル",
                "著者",
                "シリーズ名",
                "状態"
            ]
        ],
        use_container_width=True
    )

    # =====================
    # 削除
    # =====================

    st.subheader("🗑️ 本の削除")

    options_dict = {}

    for _, row in df.iterrows():

        book_id = int(row["id"])
        book_title = str(row["title"])

        options_dict[book_id] = book_title

    delete_target = st.selectbox(
        "削除する本を選んでください",
        options=list(options_dict.keys()),
        format_func=lambda x: options_dict[x]
    )

    if st.button(
        "選択した本を削除"
    ):

        delete_book(delete_target)

        st.success(
            "本棚から削除しました。"
        )

        st.rerun()

else:

    st.info(
        "まだ本が登録されていません。"
    )
