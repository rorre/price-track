#!/usr/bin/env bash
set -euo pipefail

./fetch-all.sh
uv run python generate_site.py --exclude=tokopedia
echo "hwprice.rorre.me" > _site/CNAME
wrangler pages deploy _site --project-name=hwprice
