import os
import json
import re
import requests
import feedparser
from bs4 import BeautifulSoup

# Cloud-Friendly Verified Aggregator Feeds (Never blocked by Cloudflare)
RSS_FEEDS = [
    ("https://google.com", "Google News Tamil"),
    ("https://bing.com", "Bing News Tamil")
]

HISTORY_FILE = "posted_urls.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ta,en-US;q=0.9,en;q=0.8"
}

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

def resolve_real_url(url):
    try:
        if "://bing.com" in url and "url=" in url:
            from urllib.parse import urlparse, parse_qs, unquote
            parsed = parse_qs(urlparse(url).query)
            if "url" in parsed:
                return unquote(parsed["url"])
        res = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        return res.url
    except:
        return url

def extract_full_article(url):
    image_url = ""
    paragraphs = []

    try:
        res = requests.get(url, headers=HEADERS, timeout=20)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                img = og_img["content"].strip()
                if img.startswith("http") and "google" not in img.lower():
                    image_url = img

            for p in soup.find_all("p"):
                txt = p.get_text(" ", strip=True)
                if len(txt) > 55 and re.search(r'[\u0B80-\u0BFF]', txt):
                    junk = ["read also", "மேலும் படிக்க", "subscribe", "whatsapp", "telegram", "copyright", "all rights reserved", "follow us", "advertisement", "cookies"]
                    if not any(j in txt.lower() for j in junk):
                        if txt not in paragraphs:
                            paragraphs.append(txt)
    except Exception as e:
        print(f"Fetch error: {e}")

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

    for feed_url, feed_name in RSS_FEEDS:
        if posted_something:
            break
        print(f"Checking: {feed_name}")
        try:
            rss_res = requests.get(feed_url, headers=HEADERS, timeout=20)
            feed = feedparser.parse(rss_res.content)
            print(f"Found {len(feed.entries)} entries in {feed_name}")

            for entry in feed.entries[:20]:
                raw_link = entry.get("link", "").strip()
                raw_title = entry.get("title", "").strip()

                if not raw_link or not raw_title:
                    continue

                # Clean publisher suffix from title (e.g., "Headline - Dinamalar")
                if " - " in raw_title:
                    parts = raw_title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    publisher = parts[1].strip()
                else:
                    title = raw_title
                    publisher = entry.get("source", {}).get("title", "Tamil News")

                if not re.search(r'[\u0B80-\u0BFF]', title):
                    continue

                real_url = resolve_real_url(raw_link)
                if real_url in history or title in history:
                    continue

                print(f"Trying: {title} ({publisher})")
                image_url, paragraphs = extract_full_article(real_url)

                if not image_url or len(paragraphs) < 2:
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
                    <a href="{real_url}" target="_blank" rel="nofollow noopener">{publisher} - முழு செய்தியைப் படிக்க</a>
                </p>
                """

                labels = detect_labels(title, " ".join(paragraphs))
                token = get_access_token()
                post_url = publish_to_blogger(token, title, full_html, labels)

                print(f"SUCCESS! Published to DINADESAM: {post_url}")
                history.append(real_url)
                history.append(title)
                save_history(history)
                posted_something = True
                break

        except Exception as e:
            print(f"Error with {feed_name}: {e}")

    if not posted_something:
        print("No valid article published in this run.")

if __name__ == "__main__":
    main()
