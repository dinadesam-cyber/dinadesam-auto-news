import os
import json
import re
import urllib.parse
import requests
import feedparser
from bs4 import BeautifulSoup

# Verified Tamil Nadu News RSS Sources
RSS_FEEDS = [
    ("https://feedburner.com", "Hindu Tamil Thisai"),
    ("https://dinamani.com", "Dinamani"),
    ("https://oneindia.com", "Oneindia Tamil"),
    ("https://google.com", "Google News Tamil")
]

HISTORY_FILE = "posted_urls.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
}

def fetch_url_smart(url):
    """Tries direct fetch first, then falls back to free open-source proxy if blocked by cloud IP."""
    try:
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200 and len(res.text) > 500 and "<rss" in res.text.lower() or "<html" in res.text.lower():
            # Check if it's not a Cloudflare block page
            if "just a moment..." not in res.text.lower() and "cf-browser-verification" not in res.text.lower():
                return res.text
    except Exception:
        pass

    # Fallback: Free open-source AllOrigins proxy (Bypasses GitHub Actions IP blocks)
    try:
        encoded = urllib.parse.quote(url, safe="")
        proxy_url = f"https://allorigins.win{encoded}"
        res = requests.get(proxy_url, headers=HEADERS, timeout=25)
        if res.status_code == 200 and len(res.text) > 300:
            return res.text
    except Exception as e:
        print(f"Proxy note for {url}: {e}")
    return ""

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_history(history):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history[-500:], f, ensure_ascii=False, indent=2)

def get_access_token():
    url = "https://googleapis.com"
    data = {
        "client_id": os.environ["CLIENT_ID"].strip(),
        "client_secret": os.environ["CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"
    }
    res = requests.post(url, data=data, timeout=20)
    res.raise_for_status()
    return res.json()["access_token"]

def detect_labels(title, body):
    text = (title + " " + body).lower()
    labels = ["Tamil Nadu", "தமிழ்நாடு"]
    
    keywords = {
        "Chennai": ["சென்னை", "chennai"],
        "Coimbatore": ["கோவை", "கோயம்புத்தூர்", "coimbatore"],
        "Madurai": ["மதுரை", "madurai"],
        "Politics": ["அரசியல்", "முதலமைச்சர்", "ஸ்டாலின்", "திமுக", "அதிமுக", "பாஜக", "விஜய்", "தவெக", "அமைச்சர்"],
        "Cinema": ["சினிமா", "நடிகர்", "நடிகை", "திரைப்படம்", "ரஜினி", "கமல்", "அஜித்"],
        "Education": ["பள்ளி", "கல்லூரி", "தேர்வு", "மாணவர்கள்", "கல்வி"],
        "Weather": ["மழை", "வானிலை", "புயல்", "வெப்பம்"],
        "Sports": ["கிரிக்கெட்", "விளையாட்டு", "ஐபிஎல்", "செஸ்"]
    }
    
    for label, words in keywords.items():
        for w in words:
            if w in text:
                labels.append(label)
                break
    return list(dict.fromkeys(labels))[:5]

def extract_full_article(entry, url):
    image_url = ""
    paragraphs = []

    if "media_content" in entry and len(entry.media_content) > 0:
        image_url = entry.media_content.get("url", "")
    elif "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
        image_url = entry.media_thumbnail.get("url", "")

    html_text = fetch_url_smart(url)
    if html_text:
        soup = BeautifulSoup(html_text, "html.parser")
        if not image_url:
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                img = og_img["content"].strip()
                if img.startswith("http") and "google" not in img.lower():
                    image_url = img

        for p in soup.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if len(txt) > 50 and re.search(r'[\u0B80-\u0BFF]', txt):
                junk = ["read also", "மேலும் படிக்க", "subscribe", "whatsapp", "telegram", "copyright", "all rights reserved", "follow us", "advertisement", "cookies"]
                if not any(j in txt.lower() for j in junk):
                    if txt not in paragraphs:
                        paragraphs.append(txt)

    # Fallback to RSS summary if needed
    if len(paragraphs) < 2:
        summary_html = entry.get("summary", "") or entry.get("description", "")
        if summary_html:
            soup_sum = BeautifulSoup(summary_html, "html.parser")
            if not image_url:
                img_tag = soup_sum.find("img")
                if img_tag and img_tag.get("src"):
                    image_url = img_tag["src"].strip()
            sum_txt = soup_sum.get_text(" ", strip=True)
            if len(sum_txt) > 40 and re.search(r'[\u0B80-\u0BFF]', sum_txt):
                paragraphs.append(sum_txt)

    return image_url, paragraphs[:8]

def publish_to_blogger(token, title, html_content, labels):
    blog_id = os.environ["BLOG_ID"].strip()
    api_url = f"https://googleapis.com{blog_id}/posts/"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "kind": "blogger#post",
        "blog": {"id": blog_id},
        "title": title,
        "content": html_content,
        "labels": labels
    }
    res = requests.post(api_url, headers=headers, json=payload, timeout=25)
    res.raise_for_status()
    return res.json().get("url")

def main():
    history = load_history()
    posted_something = False

    tn_keywords = ["தமிழ்நாடு", "தமிழகம்", "சென்னை", "மதுரை", "கோவை", "திருச்சி", "சேலம்", "நெல்லை", "ஸ்டாலின்", "திமுக", "அதிமுக", "விஜய்", "பாஜக", "வேலூர்", "தஞ்சை", "ஈரோடு", "கன்னியாகுமரி", "தூத்துக்குடி", "புதுச்சேரி"]

    for feed_url, source_name in RSS_FEEDS:
        if posted_something:
            break
        print(f"Fetching feed: {source_name}")
        xml_data = fetch_url_smart(feed_url)
        if not xml_data:
            print(f"Could not load XML for {source_name}")
            continue

        feed = feedparser.parse(xml_data)
        print(f"Found {len(feed.entries)} entries in {source_name}")

        for entry in feed.entries[:15]:
            link = entry.get("link", "").strip()
            raw_title = entry.get("title", "").strip()

            if not link or not raw_title or link in history:
                continue

            title = raw_title.rsplit(" - ", 1).strip() if " - " in raw_title else raw_title
            if not re.search(r'[\u0B80-\u0BFF]', title):
                continue

            summary_txt = entry.get("summary", "")
            if not any(k in (title + " " + summary_txt) for k in tn_keywords):
                continue

            print(f"Extracting article: {title}")
            image_url, paragraphs = extract_full_article(entry, link)

            if not image_url or len(paragraphs) < 1:
                print(f"Skipping (img={bool(image_url)}, paras={len(paragraphs)})")
                continue

            body_html = "".join([f"<p style='font-size:16px; line-height:1.8; margin-bottom:15px;'>{p}</p>" for p in paragraphs])
            
            full_html = f"""
            <div style="text-align:center; margin-bottom:20px;">
                <img src="{image_url}" alt="{title}" style="max-width:100%; height:auto; border-radius:8px;" />
            </div>
            {body_html}
            <hr style="margin:25px 0; border:0; border-top:1px solid #ddd;" />
            <p style="font-size:14px; color:#555;">
                <strong>செய்தி மூலம் (Original Source):</strong> 
                <a href="{link}" target="_blank" rel="nofollow noopener">{source_name} - முழு செய்தியைப் படிக்க</a>
            </p>
            """

            labels = detect_labels(title, " ".join(paragraphs))
            token = get_access_token()
            post_url = publish_to_blogger(token, title, full_html, labels)

            print(f"SUCCESS! Published to DINADESAM: {post_url}")
            history.append(link)
            save_history(history)
            posted_something = True
            break

    if not posted_something:
        print("No new valid Tamil Nadu article found in this run.")

if __name__ == "__main__":
    main()
