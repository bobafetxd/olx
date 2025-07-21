import requests
from bs4 import BeautifulSoup
import time
import os
import re

WEBHOOK_URL = "https://discord.com/api/webhooks/1390754661614747698/CRsoN48f5kQyxvq3DEG9kY-9eJVwA9M1WN_oJZhU_Wt4vGIb_LO74BXpyDO617baJndJ"

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
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


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

    # Mapowanie zdjęć
    img_map = {}
    for a in soup.select('a[href^="/d/oferta/"]'):
        href = a.get("href")
        if not href:
            continue

        img_tag = a.find("img")
        if not img_tag:
            continue

        img_url = None
        if img_tag.has_attr("srcset"):
            # Pobieramy najlepszą jakość z srcset
            srcset_urls = [item.strip().split(" ")[0] for item in img_tag["srcset"].split(",")]
            img_url = srcset_urls[-1] if srcset_urls else None
        elif img_tag.has_attr("data-src"):
            img_url = img_tag["data-src"]
        elif img_tag.has_attr("src"):
            img_url = img_tag["src"]

        # Pomijamy puste lub placeholdery
        if img_url and "no_thumbnail" not in img_url and img_url.startswith("http"):
            img_map[href] = img_url


    # Przechodzenie po ogłoszeniach
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

        # Rozmiar z tytułu
        size_match = re.search(r'(\d+\s?GB|\d+\s?TB)', title.upper())
        size = size_match.group(1).replace(" ", "") if size_match else "Nieznany"

        price_tag = block.find("p", {"data-testid": "ad-price"})
        price = price_tag.get_text(strip=True) if price_tag else "Brak ceny"
        if price == "Brak ceny":
            continue

        parent_card = block.find_parent("div", {"data-cy": "l-card"})
        location_tag = parent_card.select_one("p[data-testid='location-date']")
        location_text = location_tag.get_text(strip=True) if location_tag else ""
        if " - " in location_text:
            location, date_posted = location_text.split(" - ", 1)
        else:
            location = location_text
            date_posted = ""

        seller = "Nieznany"
        seller_tag = parent_card.select_one("p:has(svg[aria-label='user'])")
        if seller_tag:
            seller = seller_tag.get_text(strip=True)

        img_url = img_map.get(href)

        offers.append({
            "id": offer_id,
            "title": title,
            "price": price,
            "link": full_link,
            "img_url": img_url,
            "location": location,
            "seller": seller,
            "date": date_posted,
            "size": size,
            "condition": "Używane"
        })

    return offers


def send_to_discord(offer):
    embed = {
        "title": offer["title"],
        "url": offer["link"],
        "color": 0x007bff,
        "fields": [
            {"name": "💰 Cena", "value": offer.get("price", "Brak"), "inline": True},
            {"name": "📦 Rozmiar", "value": offer.get("size", "Brak"), "inline": True},
            {"name": "📱 Stan", "value": offer.get("condition", "Brak"), "inline": True},
            {"name": "🧑 Sprzedawca", "value": offer.get("seller", "Brak"), "inline": True},
            {"name": "📍 Lokalizacja", "value": offer.get("location", "Brak"), "inline": True},
            {"name": "🆔 ID", "value": offer["id"], "inline": True},
            {"name": "🕒 Dodano", "value": offer.get("date", "Brak"), "inline": False},
        ]
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

    new_offers = [offer for offer in offers if offer["id"] not in seen_ids]

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
