import json
from typing import Generator

from pydantic import BaseModel

from price.shared import ProductCategory, ProductInfo, result_to_product_info


class GenericData(BaseModel):
    title: str
    price: str
    detail: str | None = None


def get_all_data(
    data: list[GenericData], category: ProductCategory
) -> Generator[ProductInfo, object, None]:
    for item in data:
        if x := result_to_product_info(
            name=item.title + " " + (item.detail or ""),
            category=category,
            price=int(item.price.replace("Rp", "").replace(".", "").strip()),
        ):
            yield x


def get_from_json(fname: str, category: ProductCategory):
    with open(fname, "r") as f:
        data = json.load(f)

    generic_data_list = [GenericData(**item) for item in data]
    return list(get_all_data(generic_data_list, category))
