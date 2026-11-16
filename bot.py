import requests
import feedparser

test_urls = [
    ("Dinamalar", "https://dinamalar.com"),
    ("Daily Thanthi", "https://dailythanthi.com"),
    ("Maalaimalar", "https://maalaimalar.com"),
    ("Vikatan", "https://vikatan.com"),
    ("Polimer", "https://polimernews.com"),
    ("Puthiya Thalaimurai", "https://puthiyathalaimurai.com"),
    ("News18 TN", "https://news18.com"),
    ("Oneindia TN", "https://oneindia.com"),
    ("Google News TN", "https://google.com")
]

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

for name, url in test_urls:
    try:
        r = requests.get(url, headers=headers, timeout=10)
        f = feedparser.parse(r.content)
        print(f"{name} -> HTTP:{r.status_code} | Len:{len(r.text)} | Entries:{len(f.entries)} | Sample:{r.text[:80].replace(chr(10),' ')}")
    except Exception as e:
        print(f"{name} -> ERROR: {e}")
