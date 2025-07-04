import requests
from bs4 import BeautifulSoup
import time
import os
import re

# Pobieramy webhook z zmiennej środowiskowej
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
if not WEBHOOK_URL:
    print("❌ Nie ustawiono WEBHOOK_URL w zmiennych środowiskowych!")
    exit(1)

OLX_URL = (
    "https://www.olx.pl/elektronika/telefony/smartfony-telefony-komorkowe/gdynia/q-iphone-14/"
    "?search%5Bdist%5D=50"
    "&search%5Bfilter_enum_phonemodel%5D%5B0%5D=iphone-14-pro-max"
    "&search%5Bfilter_enum_phonemodel%5D%5B1%5D=iphone-14-pro"
    "&search%5Bfilter_enum_phonemodel%5D%5B2%5D=iphone-15-pro"
    "&search%5Bfilter_enum_phonemodel%5D%5B3%5D=iphone-15-pro-max"
    "&search%5Bfilter_enum_phonemodel%5D%5B4%5D=iphone-15"
    "&search%5Bfilter_enum_phonemodel%5D%5B5%5D=iphone-14"
    "&search%5Bfilter_enum_phonemodel%5D%5B6%5D=iphone-13"
    "&search%5Bfilter_enum_phonemodel%5D%5B7%5D=iphone-13-mini"
    "&search%5Bfilter_enum_phonemodel%5D%5B8%5D=iphone-13-pro"
    "&search%5Bfilter_enum_phonemodel%5D%5B9%5D=iphone-13-pro-max"
    "&search%5Border%5D=created_at:desc"
)

SEEN_FILE = "seen_ids.txt"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

def load_seen_ids():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            return set(line.strip() for line in f)
    return set()

def save_seen_ids(seen_ids):
    with open(SEEN_FILE, "w") as f:
        for id_ in seen_ids:
            f.write(f"{id_}\n")

def get_offers():
    try:
        r = requests.get(OLX_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception as e:
        print(f"❌ Błąd pobierania strony OLX: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    offers = []

    img_map = {}
    for a in soup.select('a[href^="/d/oferta/"]'):
        href = a.get("href")
        img_tag = a.find("img")
        if img_tag:
            img_url = img_tag.get("src") or img_tag.get("data-src")
            if img_url and not img_url.endswith("no_thumbnail.15f456ec5.svg"):
                srcset = img_tag.get("srcset", "")
                match = re.findall(r'(https?://[^\s,]+)', srcset)
                if match:
                    img_url = match[-1]
                img_map[href] = img_url

    offer_blocks = soup.select('div[data-cy="ad-card-title"]')
    for block in offer_blocks:
        a_tag = block.find("a", href=True)
        if not a_tag:
            continue

        href = a_tag["href"]
        full_link = "https://www.olx.pl" + href
        match = re.search(r"ID(\w+)\.html", href)
        offer_id = match.group(1) if match else None
        if not offer_id:
            continue

        title_tag = a_tag.find("h4")
        title = title_tag.get_text(strip=True) if title_tag else "Brak tytułu"
        if not title or title.lower() == "wyróżnione":
            continue

        price_tag = block.find("p", {"data-testid": "ad-price"})
        price = price_tag.get_text(strip=True) if price_tag else "Brak ceny"
        if price == "Brak ceny":
            continue

        img_url = img_map.get(href)

        offers.append({
            "id": offer_id,
            "title": title,
            "price": price,
            "link": full_link,
            "img_url": img_url
        })

    return offers

def send_to_discord(offer):
    embed = {
        "title": offer["title"],
        "url": offer["link"],
        "description": offer["price"],
        "color": 0x0099ff,
    }
    if offer["img_url"]:
        embed["thumbnail"] = {"url": offer["img_url"]}

    data = {"embeds": [embed]}
    try:
        r = requests.post(WEBHOOK_URL, json=data, timeout=10)
        r.raise_for_status()
        print(f"✅ Wysłano: {offer['title']}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Błąd webhooka: {e}")
        return False

def main():
    seen_ids = load_seen_ids()
    print("⏳ Szukanie nowych ogłoszeń...")
    offers = get_offers()
    print(f"🔎 Znaleziono {len(offers)} ogłoszeń.")

    new_offers = []
    for offer in offers:
        if offer["id"] in seen_ids:
            print("⏹️ Natrafiono na znane ogłoszenie, kończę sprawdzanie.")
            break
        new_offers.append(offer)

    if not new_offers:
        print("ℹ️ Brak nowych ogłoszeń.")
    else:
        for offer in reversed(new_offers):
            print(f"➡️ Nowe ogłoszenie: {offer['title']} ({offer['price']})")
            if send_to_discord(offer):
                seen_ids.add(offer["id"])
                time.sleep(1)

    save_seen_ids(seen_ids)

if __name__ == "__main__":
    while True:
        main()
        print("⏲️ Czekam 5 minut do kolejnego sprawdzenia...\n")
        time.sleep(300)
