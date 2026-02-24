from datetime import date
from pathlib import Path
import subprocess
import tempfile
import time
from typing import List

import httpx
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field

from price.shared import CATEGORIES, ProductCategory, result_to_product_info

SIMULATION_API_URL = "https://enterkomputer.com/jeanne/v2/simulation"
SIMULATION_URL = "https://enterkomputer.com/simulasi/"

API_HEADERS = {
    "accept-language": "en-US,en;q=0.5",
    "origin": "https://enterkomputer.com",
    "referer": "https://enterkomputer.com/simulasi/",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
}


class Result(BaseModel):
    p_code: int = Field(..., alias="PCODE")
    p_name: str = Field(..., alias="PNAME")
    p_prcz: List[int] = Field(..., alias="PPRCZ")
    p_imgz: List[str] | None = Field(..., alias="PIMGZ")
    p_stts: int = Field(..., alias="PSTTS")
    p_dtls: str = Field(..., alias="PDTLS")
    p_best: int = Field(..., alias="PBEST")
    p_link: str = Field(..., alias="PLINK")
    r_type: str = Field(..., alias="RTYPE")

    class Config:
        populate_by_name = True


class EnterKomputerResponse(BaseModel):
    status: bool
    rc: str = Field(..., alias="RC")
    current_page: int = Field(..., alias="currentPage")
    description: str
    total_records: int = Field(..., alias="totalRecords")
    result: List[Result]

    class Config:
        populate_by_name = True


def get_token_and_cookies():
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
            page.goto(SIMULATION_URL, wait_until="domcontentloaded")

            token = page.get_attribute("[data-api-token]", "data-api-token")
            signature = page.get_attribute("[data-api-signature]", "data-api-signature")

            cookies = context.cookies()
            cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)

            page.close()
            browser.close()
    finally:
        proc.terminate()

    if not token or not signature:
        raise ValueError("Failed to retrieve token or signature from the page.")

    return token, signature, cookie_header


def fetch_simulation(
    client: httpx.Client, category: str, token: str, signature: str
) -> EnterKomputerResponse:
    response = client.post(
        SIMULATION_API_URL,
        json={
            "RSTGE": category,
            "MSTGE": category,
            "token": token,
            "signature": signature,
        },
    )
    response.raise_for_status()
    return EnterKomputerResponse.model_validate(response.json())


def get_all_data(data: list[Result], category: ProductCategory):
    for item in data:
        if x := result_to_product_info(
            name=item.p_name + " " + item.p_dtls,
            category=category,
            price=item.p_prcz[0],
        ):
            yield x


def get_from_date(date: date, category: ProductCategory):
    data_path = (
        Path("data") / date.isoformat() / "enterkomputer" / f"{category.value}.json"
    )
    if not data_path.exists():
        raise FileNotFoundError(f"No data found for {date} and category {category}")
    data = EnterKomputerResponse.model_validate_json(data_path.read_text())
    return list(get_all_data(data.result, category))


def main():
    token, signature, cookies = get_token_and_cookies()
    headers = {**API_HEADERS, "cookie": cookies}
    out_dir = Path("data") / date.today().isoformat() / "enterkomputer"
    out_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(headers=headers) as client:
        for category in CATEGORIES:
            data = fetch_simulation(client, category, token, signature)
            print(f"Category: {category}")
            for item in data.result:
                print(f"  Product: {item.p_name}, Price: {item.p_prcz[0]}")

            # save to data/<date>/{category}.json
            (out_dir / f"{category}.json").write_text(data.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
