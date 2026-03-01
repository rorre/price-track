import httpx

from price.data import save_data_to_json
from price.shared import ProductCategory
from price.source.generic import GenericData

BASE_URL = "https://www.agres.id/api/shop-products"

CATEGORY_SLUGS: dict[ProductCategory, str] = {
    ProductCategory.PROCESSOR: "processors",
    ProductCategory.MOTHERBOARD: "motherboards",
    ProductCategory.RAM: "memories",
    ProductCategory.SSD: "storages",
    ProductCategory.VGA: "vga-cards",
    ProductCategory.PSU: "power-supplies",
}

MAX_RETRIES = 3
PAGE_LIMIT = 50


def get_products(
    client: httpx.Client, category: ProductCategory
) -> list[GenericData] | None:
    slug = CATEGORY_SLUGS.get(category)
    if not slug:
        return []

    page = 1
    all_products: list[GenericData] = []

    while True:
        params = {
            "category": slug,
            "sort": "newest",
            "page": page,
            "limit": PAGE_LIMIT,
        }
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.get(BASE_URL, params=params)
                response.raise_for_status()
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"{category.value}: RETRY page {page} ({attempt}/{MAX_RETRIES}) ({e})")
                else:
                    print(f"{category.value}: SKIP ({e})")
                    return None

        data = response.json()
        for product in data["products"]:
            price = product.get("discountedPrice") or product["price"]
            all_products.append(
                GenericData(title=product["title"], price=str(price))
            )

        if not data.get("hasMore", False):
            break
        page += 1

    print(f"{category.value}: OK ({len(all_products)} products)")
    return all_products


def main():
    with httpx.Client() as client:
        for category in CATEGORY_SLUGS:
            products = get_products(client, category)
            if products is not None:
                save_data_to_json(category, "agres", products)


if __name__ == "__main__":
    main()
