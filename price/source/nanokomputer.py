import httpx
from bs4 import BeautifulSoup

from price.data import save_data_to_json
from price.shared import ProductCategory
from price.source.generic import GenericData

BASE_URL = "https://nanokomputer.com/collections/all"

CATEGORY_PRODUCT_TYPES: dict[ProductCategory, list[str]] = {
    ProductCategory.PROCESSOR: ["Processor"],
    ProductCategory.MOTHERBOARD: ["Motherboard"],
    ProductCategory.RAM: ["Memory"],
    ProductCategory.SSD: ["Storage"],
    ProductCategory.VGA: ["Graphic Card", "Graphics Cards"],
    ProductCategory.PSU: ["PSU"],
}


def _build_url(product_types: list[str], page: int) -> str:
    params = "sort_by=title-ascending&filter.v.availability=1"
    for pt in product_types:
        params += f"&filter.p.product_type={pt.replace(' ', '+')}"
    params += f"&page={page}"
    return f"{BASE_URL}?{params}"


def _parse_page(html: str) -> tuple[list[GenericData], int]:
    soup = BeautifulSoup(html, "html.parser")

    products: list[GenericData] = []
    for card_link in soup.find_all("product-card-link"):
        qa = card_link.find(attrs={"data-product-title": True})
        if not qa:
            continue
        title = qa["data-product-title"]

        price_el = card_link.find("span", class_="price")
        if not price_el:
            continue
        price = price_el.text.strip().replace("Rp", "").replace(".", "").strip()

        detail_el = card_link.find(class_="metafield-multi_line_text_field")
        detail = detail_el.get_text(separator=" ", strip=True) if detail_el else None

        products.append(GenericData(title=title, price=price, detail=detail))

    last_page_el = soup.find(attrs={"last-page": True})
    last_page = int(last_page_el["last-page"]) if last_page_el else 1

    return products, last_page


MAX_RETRIES = 3


def get_products(
    client: httpx.Client, category: ProductCategory
) -> list[GenericData] | None:
    product_types = CATEGORY_PRODUCT_TYPES.get(category)
    if not product_types:
        return []

    page = 1
    all_products: list[GenericData] = []

    while True:
        url = _build_url(product_types, page)
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.get(url)
                response.raise_for_status()
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"{category.value}: RETRY page {page} ({attempt}/{MAX_RETRIES}) ({e})")
                else:
                    print(f"{category.value}: SKIP ({e})")
                    return None

        products, last_page = _parse_page(response.text)
        all_products.extend(products)

        if page >= last_page:
            break
        page += 1

    print(f"{category.value}: OK ({len(all_products)} products)")
    return all_products


def main():
    with httpx.Client() as client:
        for category in CATEGORY_PRODUCT_TYPES:
            products = get_products(client, category)
            if products is not None:
                save_data_to_json(category, "nanokomputer", products)


if __name__ == "__main__":
    main()
