from datetime import date
from pathlib import Path
import subprocess
import tempfile
import time
from typing import List

import httpx
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field

from price.data import save_data_to_json
from price.shared import CATEGORIES, ProductCategory, result_to_product_info
from price.source.generic import GenericData

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


MAX_RETRIES = 3


def fetch_simulation(
    client: httpx.Client, category: str, token: str, signature: str
) -> EnterKomputerResponse | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
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
            data = EnterKomputerResponse.model_validate(response.json())
            print(f"{category}: OK ({len(data.result)} products)")
            return data
        except Exception as e:
            if attempt < MAX_RETRIES:
                print(f"{category}: RETRY ({attempt}/{MAX_RETRIES}) ({e})")
            else:
                print(f"{category}: SKIP ({e})")
                return None


def to_generic_data(data: list[Result]) -> list[GenericData]:
    return [
        GenericData(
            title=item.p_name,
            price=str(item.p_prcz[0]),
            detail=item.p_dtls or None,
        )
        for item in data
    ]


def get_all_data(data: list[Result], category: ProductCategory):
    for item in data:
        if x := result_to_product_info(
            name=item.p_name + " " + item.p_dtls,
            category=category,
            price=item.p_prcz[0],
        ):
            yield x


def main():
    token, signature, cookies = get_token_and_cookies()
    headers = {**API_HEADERS, "cookie": cookies}
    with httpx.Client(headers=headers) as client:
        for category in CATEGORIES:
            data = fetch_simulation(client, category, token, signature)
            if data is not None:
                save_data_to_json(
                    ProductCategory(category), "enterkomputer", to_generic_data(data.result)
                )


if __name__ == "__main__":
    main()
