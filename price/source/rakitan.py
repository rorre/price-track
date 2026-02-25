import re

import httpx

from price.data import save_data_to_json
from price.shared import ProductCategory
from price.source.generic import GenericData

OPTION_RE = re.compile(
    r'<option\s+value="[^"]*"[^>]*>\s*(.+?)\s*<br>\s*Rp\.\s*([\d.]+)\s*</option>',
    re.DOTALL,
)

REQ_DATA: dict[ProductCategory, list[dict]] = {
    ProductCategory.PROCESSOR: [{"id": 1, "socket": "", "brand": ""}],
    ProductCategory.MOTHERBOARD: [{"id": 2, "socket": "", "brand": ""}],
    ProductCategory.RAM: [
        {"id": 3, "socket": "", "brand": "", "idproduk": 51620},  # DDR4
        {"id": 3, "socket": "", "brand": "", "idproduk": 55524},  # DDR5
    ],
    ProductCategory.SSD: [{"id": 7, "socket": "", "brand": ""}],
    ProductCategory.HARDDISK: [{"id": 7, "socket": "", "brand": ""}],
    ProductCategory.VGA: [{"id": 4, "socket": "", "brand": ""}],
    ProductCategory.PSU: [{"id": 5, "socket": "", "brand": ""}],
}


MAX_RETRIES = 3


def get_products(client: httpx.Client, category: ProductCategory) -> list[GenericData] | None:
    # curl 'https://rakitan.com/system/ajax/?jsg-content/modules/product/ajax.item.php' --data-raw 'id=4&socket=&brand='
    req_data = REQ_DATA.get(category)
    if not req_data:
        return []

    products: list[GenericData] = []
    for data in req_data:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = client.post(
                    "https://rakitan.com/system/ajax/?jsg-content/modules/product/ajax.item.php",
                    data=data,
                )
                response.raise_for_status()
                break
            except Exception as e:
                if attempt < MAX_RETRIES:
                    print(f"{category.value}: RETRY ({attempt}/{MAX_RETRIES}) ({e})")
                else:
                    print(f"{category.value}: SKIP ({e})")
                    return None

        for match in OPTION_RE.finditer(response.text):
            title = match.group(1).strip()
            price = match.group(2).replace(".", "")
            products.append(GenericData(title=title, price=price))

    print(f"{category.value}: OK ({len(products)} products)")
    return products


def main():
    with httpx.Client() as client:
        for category in ProductCategory:
            products = get_products(client, category)
            if products is not None:
                save_data_to_json(category, "rakitan", products)


if __name__ == "__main__":
    main()
