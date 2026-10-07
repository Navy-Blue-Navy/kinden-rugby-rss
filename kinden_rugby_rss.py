import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin
import hashlib
import re


# --------------------------------------------------
# 設定
# --------------------------------------------------

URL = "https://www.kinden-sports.jp/kindentridentblitzs/news/"

OUTPUT = Path(__file__).parent / "kinden_rugby.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.kinden-sports.jp/kindentridentblitzs/",
    "Upgrade-Insecure-Requests": "1",
}


# --------------------------------------------------
# 既存RSSを読み込む
# --------------------------------------------------

old_items = {}

if OUTPUT.exists():
    try:
        old_tree = ET.parse(OUTPUT)

        for item in old_tree.getroot().findall("./channel/item"):

            guid = item.findtext("guid", "")

            if guid:
                old_items[guid] = {
                    "title": item.findtext("title", ""),
                    "link": item.findtext("link", ""),
                    "description": item.findtext("description", ""),
                    "pubDate": item.findtext("pubDate", ""),
                    "guid": guid,
                }

    except Exception:
        old_items = {}


# --------------------------------------------------
# ニュース一覧取得
# --------------------------------------------------

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

print("HTTP:", response.status_code)

response.raise_for_status()
response.encoding = "utf-8"

soup = BeautifulSoup(
    response.text,
    "html.parser"
)


# --------------------------------------------------
# ニュース取得
# --------------------------------------------------

current_items = []
seen = set()

date_pattern = re.compile(
    r"20\d{2}[./年]\d{1,2}[./月]\d{1,2}"
)


for a in soup.find_all("a", href=True):

    href = a.get("href", "").strip()

    article_url = urljoin(
        URL,
        href
    )

    # ニュース個別記事だけ対象
    if "/kindentridentblitzs/news/" not in article_url:
        continue

    # ニュース一覧ページそのものは除外
    if article_url.rstrip("/") == URL.rstrip("/"):
        continue

    title = " ".join(
        a.stripped_strings
    ).strip()

    if not title:
        continue

    # 同じURLの重複を除外
    if article_url in seen:
        continue

    seen.add(article_url)


    # --------------------------------------------------
    # 日付を探す
    # --------------------------------------------------

    date_text = None
    parent = a

    for _ in range(6):

        if parent is None:
            break

        text = " ".join(
            parent.stripped_strings
        )

        match = date_pattern.search(text)

        if match:
            date_text = match.group(0)
            break

        parent = parent.parent


    if not date_text:
        print(
            "日付取得失敗:",
            title
        )
        continue


    # --------------------------------------------------
    # 日付変換
    # --------------------------------------------------

    normalized_date = (
        date_text
        .replace("年", ".")
        .replace("月", ".")
        .replace("日", "")
        .replace("/", ".")
    )

    try:

        dt = datetime.strptime(
            normalized_date,
            "%Y.%m.%d"
        )

        # サイトに時刻表示がないため12:00 JST
        dt = dt.replace(
            hour=12,
            minute=0,
            second=0,
            tzinfo=JST
        )

        pub_date = format_datetime(dt)

    except Exception:

        print(
            "日付解析失敗:",
            date_text,
            title
        )
        continue


    # --------------------------------------------------
    # GUID
    # --------------------------------------------------

    guid = hashlib.sha256(
        article_url.encode("utf-8")
    ).hexdigest()


    # --------------------------------------------------
    # RSSデータ
    # --------------------------------------------------

    current_items.append(
        {
            "title": title,
            "link": article_url,
            "description": (
                "きんでんトリニティーブリッツ大阪 NEWS"
            ),
            "pubDate": pub_date,
            "guid": guid,
        }
    )


# --------------------------------------------------
# 既存RSSと統合
# --------------------------------------------------

all_items = []
seen_guids = set()


for item in current_items:

    if item["guid"] not in seen_guids:
        all_items.append(item)
        seen_guids.add(item["guid"])


for guid, item in old_items.items():

    if guid not in seen_guids:
        all_items.append(item)
        seen_guids.add(guid)


# --------------------------------------------------
# 新しい順
# --------------------------------------------------

def get_date(item):

    try:
        return parsedate_to_datetime(
            item["pubDate"]
        )

    except Exception:
        return datetime.min.replace(
            tzinfo=timezone.utc
        )


all_items.sort(
    key=get_date,
    reverse=True
)

all_items = all_items[:300]


# --------------------------------------------------
# RSS作成
# --------------------------------------------------

rss = ET.Element(
    "rss",
    version="2.0"
)

channel = ET.SubElement(
    rss,
    "channel"
)

ET.SubElement(
    channel,
    "title"
).text = "きんでんトリニティーブリッツ大阪 NEWS"

ET.SubElement(
    channel,
    "link"
).text = URL

ET.SubElement(
    channel,
    "description"
).text = (
    "きんでんトリニティーブリッツ大阪の新着ニュース"
)

ET.SubElement(
    channel,
    "language"
).text = "ja"


# --------------------------------------------------
# RSS記事
# --------------------------------------------------

for item in all_items:

    element = ET.SubElement(
        channel,
        "item"
    )

    ET.SubElement(
        element,
        "title"
    ).text = item["title"]

    ET.SubElement(
        element,
        "link"
    ).text = item["link"]

    ET.SubElement(
        element,
        "description"
    ).text = item["description"]

    ET.SubElement(
        element,
        "pubDate"
    ).text = item["pubDate"]

    guid_element = ET.SubElement(
        element,
        "guid"
    )

    guid_element.set(
        "isPermaLink",
        "false"
    )

    guid_element.text = item["guid"]


# --------------------------------------------------
# XML保存
# --------------------------------------------------

tree = ET.ElementTree(rss)

ET.indent(
    tree,
    space="  "
)

tree.write(
    OUTPUT,
    encoding="utf-8",
    xml_declaration=True
)


# --------------------------------------------------
# 結果表示
# --------------------------------------------------

print("RSS作成成功")

print(
    "今回取得:",
    len(current_items),
    "件"
)

print(
    "RSS保存件数:",
    len(all_items),
    "件"
)

print(
    "保存先:",
    OUTPUT
)

print()
print("取得記事:")


for i, item in enumerate(
    current_items,
    start=1
):

    print()

    print(
        f"[{i}] {item['title']}"
    )

    print(
        "    ",
        item["pubDate"]
    )

    print(
        "    ",
        item["link"]
    )
