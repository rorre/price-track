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


CATEGORY_QUERIES: dict[ProductCategory, list[str]] = {
    ProductCategory.PROCESSOR: [
        "processor amd ryzen am4",
        "processor amd ryzen am5",
        "processor intel lga 1700",
        "processor intel lga 1851",
    ],
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
    ProductCategory.VGA: [
        "vga nvidia geforce rtx",
        "vga amd radeon rx",
        "vga intel arc",
    ],
    ProductCategory.PSU: [
        "psu bronze",
        "psu gold",
        "psu platinum",
    ],
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
