import subprocess
import tempfile
import time
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright, Page

from price.data import save_data_to_json
from price.shared import ProductCategory, RAMType
from price.source.generic import GenericData

BASE_SEARCH_URL = "https://www.tokopedia.com/search"
BASE_PARAMS = {
    "navsource": "home,home",
    "shop_tier": "3#2",
    "srp_component_id": "04.06.00.00",
    "srp_page_id": "",
    "srp_page_title": "",
    "st": "product",
}

TITLE_CLASS = "+tnoqZhn89+NHUA43BpiJg=="
PRICE_CLASS = "urMOIDHH7I0Iy1Dv2oFaNw=="

MAX_SCROLL_ATTEMPTS = 60


def _ram_queries() -> list[str]:
    queries = []
    seen: set[str] = set()
    for rt in RAMType:
        parts = rt.value.split()  # e.g. ["DDR4-3200", "2x16GB"]
        ddr, speed = parts[0].split("-")  # "DDR4", "3200"
        config = parts[1].replace("GB", "").lower()  # "2x16"
        q = f'ram {config} {ddr.lower()} "{speed}Mhz"'
        if q not in seen:
            seen.add(q)
            queries.append(q)
    return queries


def _cpu_queries() -> list[str]:
    queries = []
    # AMD AM4 (Zen 3)
    for tier in ["Ryzen 5", "Ryzen 7", "Ryzen 9"]:
        queries.append(f'processor "{tier}" AM4')
    # AMD AM5 Zen 4
    for tier in ["Ryzen 5", "Ryzen 7", "Ryzen 9"]:
        queries.append(f'processor "{tier}" AM5 7000')
    # AMD AM5 Zen 5
    for tier in ["Ryzen 5", "Ryzen 7", "Ryzen 9"]:
        queries.append(f'processor "{tier}" AM5 9000')
    # Intel Alder Lake (12th gen)
    for tier in ["i3", "i5", "i7", "i9"]:
        queries.append(f'processor intel "{tier}-12" LGA 1700')
    # Intel Raptor Lake (13th/14th gen)
    for tier in ["i3", "i5", "i7", "i9"]:
        queries.append(f'processor intel "{tier}-13" LGA 1700')
        queries.append(f'processor intel "{tier}-14" LGA 1700')
    # Intel Arrow Lake (LGA 1851)
    for tier in ["Core Ultra 5", "Core Ultra 7", "Core Ultra 9"]:
        queries.append(f'processor intel "{tier}" LGA 1851')
    return queries


def _vga_queries() -> list[str]:
    queries = []
    # NVIDIA RTX 30 series
    for model in ["3060", "3060 Ti", "3070", "3070 Ti", "3080", "3080 Ti", "3090", "3090 Ti"]:
        queries.append(f'vga "RTX {model}"')
    # NVIDIA RTX 40 series
    for model in ["4060", "4060 Ti", "4070", "4070 SUPER", "4070 Ti", "4070 Ti SUPER", "4080", "4080 SUPER", "4090"]:
        queries.append(f'vga "RTX {model}"')
    # NVIDIA RTX 50 series
    for model in ["5060", "5060 Ti", "5070", "5070 Ti", "5080", "5090"]:
        queries.append(f'vga "RTX {model}"')
    # AMD Radeon RX 6000 series
    for model in ["6600", "6600 XT", "6650 XT", "6700", "6700 XT", "6750 XT", "6800", "6800 XT", "6900 XT", "6950 XT"]:
        queries.append(f'vga "RX {model}"')
    # AMD Radeon RX 7000 series
    for model in ["7600", "7600 XT", "7700", "7700 XT", "7800", "7800 XT", "7900 GRE", "7900 XT", "7900 XTX"]:
        queries.append(f'vga "RX {model}"')
    # AMD Radeon RX 9000 series
    for model in ["9060 XT", "9070", "9070 XT"]:
        queries.append(f'vga "RX {model}"')
    # Intel Arc
    for model in ["A380", "A750", "A770", "B570", "B580"]:
        queries.append(f'vga "Arc {model}"')
    return queries


def _psu_queries() -> list[str]:
    queries = []
    for rating in ["bronze", "gold", "platinum"]:
        for watt in ["500W", "600W", "700W", "750W", "800W", "850W", "1000W", "1200W", "1500W"]:
            queries.append(f'psu {rating} {watt}')
    return queries


CATEGORY_QUERIES: dict[ProductCategory, list[str]] = {
    ProductCategory.PROCESSOR: _cpu_queries(),
    ProductCategory.MOTHERBOARD: [
        "motherboard am4",
        "motherboard am5",
        "motherboard lga 1700",
        "motherboard lga 1851",
    ],
    ProductCategory.RAM: _ram_queries(),
    ProductCategory.SSD: [
        "ssd nvme m.2",
        "ssd sata 2.5",
    ],
    ProductCategory.HARDDISK: [
        'harddisk internal 3.5"',
    ],
    ProductCategory.VGA: _vga_queries(),
    ProductCategory.PSU: _psu_queries(),
}


def _build_search_url(query: str) -> str:
    params = {**BASE_PARAMS, "q": query}
    return f"{BASE_SEARCH_URL}?{urlencode(params)}"


def _scroll_until_load_more(page: Page):
    for _ in range(MAX_SCROLL_ATTEMPTS):
        page.evaluate("window.scrollBy(0, 500)")
        time.sleep(0.5)

        load_more = page.query_selector("button:has-text('Muat Lebih Banyak')")
        if load_more:
            break

        at_bottom = page.evaluate(
            "() => window.innerHeight + window.scrollY >= document.body.scrollHeight - 100"
        )
        if at_bottom:
            break


def _parse_products(page: Page) -> list[GenericData]:
    data = page.evaluate(
        """
        (classes) => {
            const titles = document.getElementsByClassName(classes.title);
            const prices = document.getElementsByClassName(classes.price);
            const results = [];
            const len = Math.min(titles.length, prices.length);
            for (let i = 0; i < len; i++) {
                results.push({
                    title: titles[i].textContent.trim(),
                    price: prices[i].textContent.trim().replace(/[Rp.]/g, '').trim(),
                });
            }
            return results;
        }
        """,
        {"title": TITLE_CLASS, "price": PRICE_CLASS},
    )
    return [GenericData(title=item["title"], price=item["price"]) for item in data]


def scrape_search(page: Page, query: str) -> list[GenericData]:
    url = _build_search_url(query)
    page.goto(url, wait_until="domcontentloaded")
    time.sleep(2)

    _scroll_until_load_more(page)

    return _parse_products(page)


def main():
    tmpdir = tempfile.mkdtemp(prefix="chrome-debug-")
    proc = subprocess.Popen(
        [
            "google-chrome-stable",
            "--remote-debugging-port=9222",
            f"--user-data-dir={tmpdir}",
        ]
    )
    time.sleep(2)

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            context = browser.contexts[0]
            page = context.new_page()

            for category, queries in CATEGORY_QUERIES.items():
                all_products: list[GenericData] = []
                for query in queries:
                    print(f"Searching: {query}")
                    products = scrape_search(page, query)
                    all_products.extend(products)
                    print(f"  Found {len(products)} products")

                if all_products:
                    save_data_to_json(category, "tokopedia", all_products)
                print(f"{category.value}: OK ({len(all_products)} products)")

            page.close()
            browser.close()
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
