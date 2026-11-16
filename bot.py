import os
import json
import re
import requests
import feedparser
from bs4 import BeautifulSoup

# Verified Tamil News RSS Feeds
RSS_FEEDS = [
    ("https://bbci.co.uk", "BBC News Tamil"),
    ("https://dinamani.com", "Dinamani"),
    ("https://hindutamil.in", "Hindu Tamil Thisai"),
    ("https://oneindia.com", "Oneindia Tamil")
]

HISTORY_FILE = "posted_urls.json"

BROWSER_HEADERS = {
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

def extract_article_data(entry, url):
    image_url = ""
    paragraphs = []

    if "media_content" in entry and len(entry.media_content) > 0:
        image_url = entry.media_content.get("url", "")
    elif "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
        image_url = entry.media_thumbnail.get("url", "")

    try:
        res = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            
            if not image_url:
                og_img = soup.find("meta", property="og:image")
                if og_img and og_img.get("content"):
                    image_url = og_img["content"].strip()

            for p in soup.find_all("p"):
                txt = p.get_text(" ", strip=True)
                if len(txt) > 50 and re.search(r'[\u0B80-\u0BFF]', txt):
                    junk_words = ["read also", "மேலும் படிக்க", "subscribe", "whatsapp", "telegram", "copyright", "all rights reserved", "follow us", "advertisement", "bbc news, தமிழ்"]
                    if not any(jw in txt.lower() for jw in junk_words):
                        if txt not in paragraphs:
                            paragraphs.append(txt)
    except Exception as e:
        print(f"Page fetch note: {e}")

    if len(paragraphs) < 2 and "content" in entry:
        raw_html = entry.content.get("value", "")
        soup_rss = BeautifulSoup(raw_html, "html.parser")
        for p in soup_rss.find_all("p"):
            txt = p.get_text(" ", strip=True)
            if len(txt) > 40 and re.search(r'[\u0B80-\u0BFF]', txt):
                paragraphs.append(txt)

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

    tn_keywords = ["தமிழ்நாடு", "தமிழகம்", "சென்னை", "மதுரை", "கோவை", "திருச்சி", "சேலம்", "நெல்லை", "ஸ்டாலின்", "திமுக", "அதிமுக", "விஜய்", "பாஜக", "வேலூர்", "தஞ்சை", "ஈரோடு", "கன்னியாகுமரி", "தூத்துக்குடி"]

    for feed_url, source_name in RSS_FEEDS:
        if posted_something:
            break
        print(f"Checking feed: {source_name}")
        try:
            rss_res = requests.get(feed_url, headers=BROWSER_HEADERS, timeout=20)
            feed = feedparser.parse(rss_res.content)
            print(f"Found {len(feed.entries)} entries in {source_name}")
            
            for entry in feed.entries[:15]:
                link = entry.get("link", "").strip()
                title = entry.get("title", "").strip()

                if not link or not title or link in history:
                    continue

                if not re.search(r'[\u0B80-\u0BFF]', title):
                    continue

                if "BBC" in source_name:
                    summary_txt = entry.get("summary", "")
                    if not any(k in (title + " " + summary_txt) for k in tn_keywords):
                        continue

                print(f"Extracting: {title}")
                image_url, paragraphs = extract_article_data(entry, link)

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

        except Exception as e:
            print(f"Error with {source_name}: {e}")

    if not posted_something:
        print("No new valid Tamil Nadu article found in this run.")

if __name__ == "__main__":
    main()
