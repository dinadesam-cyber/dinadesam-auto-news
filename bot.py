import os
import json
import re
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

# URLs built in parts so browser extensions cannot strip paths
TN_SOURCES = [
    ("https://" + "www.dinamalar.com" + "/news/tamil-nadu-news", "Dinamalar"),
    ("https://" + "www.dailythanthi.com" + "/news/state", "Daily Thanthi")
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
    url = "https://" + "oauth2.googleapis.com" + "/token"
    data = {
        "client_id": os.environ["CLIENT_ID"].strip(),
        "client_secret": os.environ["CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["REFRESH_TOKEN"].strip(),
        "grant_type": "refresh_token"
    }
    res = requests.post(url, data=data, timeout=20)
    if res.status_code != 200:
        print(f"TOKEN ERROR: {res.text}")
    res.raise_for_status()
    return res.json()["access_token"]

def detect_labels(title, body):
    text = (title + " " + body).lower()
    labels = ["Featured","Tamil Nadu", "தமிழ்நாடு"]
    
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

def get_article_links(section_url):
    links = []
    res = requests.get(section_url, headers=HEADERS, timeout=20)
    if res.status_code != 200:
        return links
    soup = BeautifulSoup(res.text, "html.parser")
    
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        txt = a.get_text(" ", strip=True)
        full_url = urljoin(section_url, href)
        
        if len(txt) > 25 and re.search(r'[\u0B80-\u0BFF]', txt):
            if any(char.isdigit() for char in full_url) and full_url.startswith("http"):
                if "/english/" not in full_url.lower() and full_url not in links:
                    links.append(full_url)
    return links[:15]

def extract_full_article(article_url):
    res = requests.get(article_url, headers=HEADERS, timeout=20)
    if res.status_code != 200:
        return "", "", []
    
    soup = BeautifulSoup(res.text, "html.parser")
    
    title = ""
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

    image_url = ""
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        img = og_img["content"].strip()
        if img.startswith("http"):
            image_url = img

    paragraphs = []
    for p in soup.find_all("p"):
        txt = p.get_text(" ", strip=True)
        if len(txt) > 55 and re.search(r'[\u0B80-\u0BFF]', txt):
            junk = ["read also", "மேலும் படிக்க", "subscribe", "whatsapp", "telegram", "copyright", "all rights reserved", "follow us", "advertisement", "cookies", "dinamalar", "dailythanthi"]
            if not any(j in txt.lower() for j in junk):
                if txt not in paragraphs:
                    paragraphs.append(txt)

    return title, image_url, paragraphs[:8]

def publish_to_blogger(token, title, html_content, labels):
    blog_id = os.environ["BLOG_ID"].strip()
    api_url = "https://" + "www.googleapis.com" + f"/blogger/v3/blogs/{blog_id}/posts/"
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
    if res.status_code not in (200, 201):
        print(f"BLOGGER ERROR ({res.status_code}): {res.text}")
    res.raise_for_status()
    return res.json().get("url")

def main():
    history = load_history()
    posted_something = False

    for section_url, source_name in TN_SOURCES:
        if posted_something:
            break
        print(f"Scanning: {source_name}")
        try:
            article_links = get_article_links(section_url)
            for link in article_links:
                if link in history:
                    continue

                title, image_url, paragraphs = extract_full_article(link)
                if not title or not re.search(r'[\u0B80-\u0BFF]', title) or title in history:
                    continue
                if not image_url or len(paragraphs) < 2:
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

                print(f"SUCCESS! Published: {post_url}")
                history.append(link)
                history.append(title)
                save_history(history)
                posted_something = True
                break

        except Exception as e:
            print(f"Error ({source_name}): {e}")

    if not posted_something:
        print("No new valid article posted.")

if __name__ == "__main__":
    main()
