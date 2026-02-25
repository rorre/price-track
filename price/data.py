from collections import defaultdict

from price.shared import ProductCategory
from price.source.generic import GenericData
import json
from pathlib import Path
from datetime import date


def save_data_to_json(category: ProductCategory, source: str, data: list[GenericData]):  # noqa: F821
    date_str = date.today().isoformat()

    output_dir = Path("data") / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{source}_{category.value}.json"

    with open(output_file, "w") as f:
        json.dump([item.dict() for item in data], f, indent=4)


def load_all_data(dt: date) -> dict[ProductCategory, list[GenericData]]:
    data_dir = Path("data") / dt.isoformat()
    all_data: dict[ProductCategory, list[GenericData]] = defaultdict(list)

    for file in data_dir.glob("*.json"):
        source_category = file.stem  # e.g. "rakitan_processor"
        cat = ProductCategory(source_category.split("_")[-1])
        with open(file) as f:
            items = json.load(f)
            all_data[cat].extend([GenericData(**item) for item in items])

    return all_data
