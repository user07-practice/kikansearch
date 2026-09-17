import os
import sqlite3
import smtplib
import requests
import re
import unicodedata


from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime


# =========================================================
# ネットワーク設定
# =========================================================

os.environ["http_proxy"] = ""
os.environ["https_proxy"] = ""
os.environ["HTTP_PROXY"] = ""
os.environ["HTTPS_PROXY"] = ""


# =========================================================
# Gmail設定
# =========================================================

MY_EMAIL = ""
APP_PASSWORD = ""


# =========================================================
# Google Books API設定
# =========================================================

GOOGLE_BOOKS_API_KEY = ""


# =========================================================
# Gmailを送る
# =========================================================

def send_gmail(subject, body):

    msg = MIMEText(body, "plain", "utf-8")

    msg["Subject"] = subject
    msg["From"] = MY_EMAIL
    msg["To"] = MY_EMAIL
    msg["Date"] = formatdate(localtime=True)

    try:

        server = smtplib.SMTP_SSL(
            "smtp.gmail.com",
            465,
            timeout=10
        )

        server.login(
            MY_EMAIL,
            APP_PASSWORD
        )

        server.send_message(msg)

        server.quit()

        return True

    except Exception as e:

        print(f"メール送信エラー: {e}")

        return False


# =========================================================
# ISBNを整える
# =========================================================

def normalize_isbn(isbn):

    if not isbn:
        return ""

    isbn = str(isbn)

    isbn = isbn.replace("-", "")
    isbn = isbn.replace(" ", "")
    isbn = isbn.replace("　", "")

    return isbn.strip()


# =========================================================
# タイトルから巻数を取得
# =========================================================

def extract_volume_number(title):

    if not title:
        return None

    title = str(title).strip()

    # 全角数字を半角に変換
    title = title.translate(
        str.maketrans(
            "０１２３４５６７８９",
            "0123456789"
        )
    )

    patterns = [

        # 第45巻
        r"第\s*(\d+)\s*巻",

        # 45巻
        r"(\d+)\s*巻",

        # （45）
        r"[（(]\s*(\d+)\s*[）)]",

        # 末尾が「45」
        r"(\d+)\s*$",

        # 末尾が「. 45」
        r"\.\s*(\d+)\s*$",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            title,
            re.IGNORECASE
        )

        if match:

            try:

                return int(
                    match.group(1)
                )

            except ValueError:

                pass

    return None

# =========================================================
# 発売日をdatetimeに変換
# =========================================================

def parse_published_date(date_text):

    if not date_text:
        return None

    date_text = str(date_text).strip()

    # YYYY-MM-DD
    try:

        return datetime.strptime(
            date_text,
            "%Y-%m-%d"
        )

    except ValueError:

        pass

    # YYYY-MM
    try:

        return datetime.strptime(
            date_text,
            "%Y-%m"
        )

    except ValueError:

        pass

    # YYYY
    try:

        return datetime.strptime(
            date_text,
            "%Y"
        )

    except ValueError:

        pass

    return None


# =========================================================
# Google BooksからISBNを取得
# =========================================================

def get_isbn(volume_info):

    identifiers = volume_info.get(
        "industryIdentifiers",
        []
    )

    # ISBN-13を優先
    for identifier in identifiers:

        if identifier.get("type") == "ISBN_13":

            return normalize_isbn(
                identifier.get(
                    "identifier",
                    ""
                )
            )

    # ISBN-10
    for identifier in identifiers:

        if identifier.get("type") == "ISBN_10":

            return normalize_isbn(
                identifier.get(
                    "identifier",
                    ""
                )
            )

    return ""


# =========================================================
# Google Booksで次巻が既刊になっているか確認
# =========================================================

def search_google_books_next_volume(
    series_name,
    next_volume
):

    print()
    print("==========================================")
    print("📚 Google Booksで既刊チェック")
    print("==========================================")

    print(
        f"シリーズ: {series_name}"
    )

    print(
        f"探す巻: {next_volume}巻"
    )

    url = (
        "https://www.googleapis.com/books/v1/volumes"
    )

    # =====================================================
    # 検索方法
    # =====================================================

    queries = [

        f'"{series_name}" "{next_volume}巻"',

        f'"{series_name}" {next_volume}',

        f'{series_name} {next_volume}巻',

    ]

    all_items = []

    seen_ids = set()

    # =====================================================
    # Google Books検索
    # =====================================================

    for search_no, query in enumerate(
        queries,
        start=1
    ):

        print()
        print(
            f"--- Google Books検索 {search_no}/3 ---"
        )

        print(
            f"検索文字列: {query}"
        )

        params = {

            "q": query,

            "maxResults": 40,

            "langRestrict": "ja",

            "orderBy": "relevance",

            "key": GOOGLE_BOOKS_API_KEY

        }

        try:

            response = requests.get(
                url,
                params=params,
                timeout=10
            )

            print(
                f"ステータスコード: "
                f"{response.status_code}"
            )

            response.raise_for_status()

            data = response.json()

        except Exception as e:

            print(
                f"Google Books検索エラー: {e}"
            )

            continue

        items = data.get(
            "items",
            []
        )

        print(
            f"取得件数: {len(items)}"
        )

        # =================================================
        # 重複除去
        # =================================================

        for item in items:

            item_id = item.get(
                "id",
                ""
            )

            if item_id:

                if item_id in seen_ids:
                    continue

                seen_ids.add(item_id)

            all_items.append(item)

    # =====================================================
    # Google Booksの検索結果を確認
    # =====================================================

    print()
    print("===== Google Books検索結果 =====")

    for i, item in enumerate(
        all_items,
        start=1
    ):

        volume_info = item.get(
            "volumeInfo",
            {}
        )

        title = volume_info.get(
            "title",
            ""
        )

        published_date = volume_info.get(
            "publishedDate",
            ""
        )

        print(
            f"{i}: "
            f"{title} | "
            f"発売日={published_date}"
        )

    print(
        "================================"
    )

    # =====================================================
    # 次巻に一致する本を探す
    # =====================================================

    candidates = []

    for item in all_items:

        volume_info = item.get(
            "volumeInfo",
            {}
        )

        title = volume_info.get(
            "title",
            ""
        )

        if not title:
            continue

        # -------------------------------------------------
        # タイトルにシリーズ名が入っているか
        # -------------------------------------------------

        normalized_series = unicodedata.normalize(
            "NFKC",
            series_name
        ).lower().strip()

        normalized_title = unicodedata.normalize(
            "NFKC",
            title
        ).lower().strip()

        if normalized_series not in normalized_title:
            print(
                f"シリーズ名不一致で除外: {title}"
            )

            continue

        # -------------------------------------------------
        # タイトルから巻数を取得
        # -------------------------------------------------

        found_volume = extract_volume_number(
            title
        )

        print(
            f"巻数判定: "
            f"{title} → {found_volume}"
        )

        # -------------------------------------------------
        # 巻数が正常に取得できた場合
        # -------------------------------------------------

        if found_volume is not None:

            if found_volume != next_volume:
                continue

        # -------------------------------------------------
        # 巻数が取得できなかった場合
        #
        # Google Booksの検索条件そのものに
        # 次巻の番号を入れているので、
        # タイトルに次巻の数字が含まれているか確認する
        # -------------------------------------------------

        else:

            normalized_title = (
                title
                .translate(
                    str.maketrans(
                        "０１２３４５６７８９",
                        "0123456789"
                    )
                )
                .strip()
            )

            volume_pattern = (
                rf"(?<!\d){next_volume}(?!\d)"
            )

            if not re.search(
                    volume_pattern,
                    normalized_title
            ):
                continue

            # タイトルから取得できなかったが
            # 検索結果として次巻の番号が確認できた
            found_volume = next_volume

        # -------------------------------------------------
        # 著者
        # -------------------------------------------------

        authors = volume_info.get(
            "authors",
            ["不明"]
        )

        author = ", ".join(
            authors
        )

        # -------------------------------------------------
        # 発売日
        # -------------------------------------------------

        published_date = volume_info.get(
            "publishedDate",
            ""
        )

        # -------------------------------------------------
        # ISBN
        # -------------------------------------------------

        isbn = get_isbn(
            volume_info
        )

        candidates.append({

            "title": title,

            "author": author,

            "publishedDate": published_date,

            "isbn": isbn,

            "volume": found_volume

        })

    # =====================================================
    # 結果
    # =====================================================

    print()
    print(
        f"次巻に一致した本: "
        f"{len(candidates)}件"
    )

    if not candidates:

        print(
            f"⚠️ {next_volume}巻は"
            "まだGoogle Booksに見つかりません。"
        )

        return None

    # =====================================================
    # 同じ本の重複除去
    # =====================================================

    unique_results = []

    seen_books = set()

    for book in candidates:

        key = (
            book["title"],
            book["isbn"]
        )

        if key in seen_books:
            continue

        seen_books.add(key)

        unique_results.append(book)

    print()
    print(
        f"重複除去後: "
        f"{len(unique_results)}件"
    )

    # =====================================================
    # 最初の候補を返す
    # =====================================================

    book = unique_results[0]

    print()
    print("🎉 次巻が見つかりました！")

    print(
        f"タイトル: {book['title']}"
    )

    print(
        f"著者: {book['author']}"
    )

    print(
        f"発売日: "
        f"{book['publishedDate'] or '不明'}"
    )

    print(
        f"ISBN: "
        f"{book['isbn'] or '不明'}"
    )

    print(
        f"巻数: {book['volume']}巻"
    )

    return book


# =========================================================
# 本棚からシリーズごとの最新巻を取得
# =========================================================

def get_latest_volumes():

    print()
    print("===== 本棚データ確認 =====")

    db_path = os.path.join(
        os.path.dirname(
            os.path.abspath(__file__)
        ),
        "books.db"
    )

    print(
        f"読み込むDB: {db_path}"
    )

    print(
        f"DBファイル存在: "
        f"{os.path.exists(db_path)}"
    )

    conn = sqlite3.connect(
        db_path
    )

    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, series_name, title
        FROM books
    """)

    rows = cursor.fetchall()

    conn.close()

    print()
    print(
        f"books.dbから {len(rows)} 件取得しました。"
    )

    latest_volumes = {}

    for row in rows:

        series_name = str(
            row[1] or ""
        ).strip()

        title = str(
            row[2] or ""
        ).strip()

        if not series_name:

            print(
                f"⚠️ シリーズ名なし: {title}"
            )

            continue

        volume = extract_volume_number(
            title
        )

        print(
            f"巻数判定: "
            f"{title} → {volume}"
        )

        if volume is None:

            print(
                "  ⚠️ 巻数を取得できませんでした"
            )

            continue

        if series_name not in latest_volumes:

            latest_volumes[
                series_name
            ] = volume

        elif volume > latest_volumes[
            series_name
        ]:

            latest_volumes[
                series_name
            ] = volume

    print()
    print(
        "===== シリーズごとの最新巻 ====="
    )

    for series_name, volume in (
        latest_volumes.items()
    ):

        print(
            f"{series_name} → {volume}巻"
        )

    print(
        "================================"
    )

    return latest_volumes


# =========================================================
# 次巻・新刊チェック
# =========================================================

def check_new_books():

    latest_volumes = get_latest_volumes()

    if not latest_volumes:

        print(
            "本棚から巻数を取得できませんでした。"
        )

        return

    print()
    print(
        "=========================================="
    )

    print(
        "📚 既刊になった新刊チェック開始"
    )

    print(
        "=========================================="
    )

    notifications = []

    # =====================================================
    # シリーズごとに処理
    # =====================================================

    for series_name, latest_volume in (
        latest_volumes.items()
    ):

        next_volume = latest_volume + 1

        print()
        print(
            "=========================================="
        )

        print(
            f"シリーズ: {series_name}"
        )

        print(
            f"現在の最新巻: {latest_volume}巻"
        )

        print(
            f"確認する巻: {next_volume}巻"
        )

        print(
            "=========================================="
        )

        # =================================================
        # Google Booksで次巻を探す
        # =================================================

        book = search_google_books_next_volume(
            series_name,
            next_volume
        )

        # =================================================
        # 見つからなかった
        # =================================================

        if book is None:

            print(
                "→ まだ既刊として確認できません。"
            )

            continue

        # =================================================
        # 発売日
        # =================================================

        release_date = parse_published_date(
            book["publishedDate"]
        )

        # 発売日が分からなくても、
        # Google Booksに既刊として登録されていれば
        # 一旦通知対象とする
        if release_date is None:

            print(
                "⚠️ 発売日は取得できませんでした。"
            )

        else:

            print(
                f"📅 発売日確認: "
                f"{book['publishedDate']}"
            )

        # =================================================
        # 通知対象
        # =================================================

        print(
            "📧 新刊通知対象です！"
        )

        notifications.append({

            "series": series_name,

            "title": book["title"],

            "author": book["author"],

            "release_date": (
                book["publishedDate"]
                or
                "不明"
            ),

            "isbn": book["isbn"],

            "volume": next_volume

        })

    # =====================================================
    # 通知する本がない
    # =====================================================

    if not notifications:

        print()
        print(
            "📭 既刊になった新刊はありませんでした。"
        )

        return

    # =====================================================
    # メール本文
    # =====================================================

    body_lines = [

        "📚 新刊のお知らせ",

        "",

        "本棚に登録されている最新巻の次の巻が、",

        "既刊として確認されました。",

        ""

    ]

    for book in notifications:

        body_lines.append(
            f"【{book['series']}】"
        )

        body_lines.append(
            f"{book['title']}"
        )

        body_lines.append(
            f"巻数: {book['volume']}巻"
        )

        body_lines.append(
            f"著者: {book['author']}"
        )

        body_lines.append(
            f"発売日: "
            f"{book['release_date']}"
        )

        body_lines.append(
            f"ISBN: "
            f"{book['isbn'] or '不明'}"
        )

        body_lines.append("")

    body = "\n".join(
        body_lines
    )

    subject = (
        "【新刊通知】"
        "本棚の次巻が既刊になりました"
    )

    print()
    print(
        "=========================================="
    )

    print(
        "📧 メールを送信します"
    )

    print(
        "=========================================="
    )

    print(body)

    success = send_gmail(
        subject,
        body
    )

    if success:

        print(
            "✅ メール送信成功！"
        )

    else:

        print(
            "❌ メール送信失敗"
        )


# =========================================================
# 実行
# =========================================================

if __name__ == "__main__":

    check_new_books()
