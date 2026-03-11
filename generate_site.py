import json
import re
from pathlib import Path
from datetime import date, datetime
from statistics import median, quantiles
from collections import defaultdict

from price.data import load_all_data
from price.shared import (
    ProductCategory,
    result_to_product_info,
    CPUGeneration,
    CPUInfo,
    PSUInfo,
    DiskInfo,
    DiskType,
    FormFactor,
    RAMType,
    RAMInfo,
)


# ── Chart data collector ──


def collect_chart_data(
    dates,
    medians_by_sub,
    q1_by_sub,
    q3_by_sub,
    subcategory_order,
    section_title,
    show_all=False,
    max_cols=3,
    collected=None,
):
    if show_all:
        active = list(subcategory_order)
    else:
        active = [
            l
            for l in subcategory_order
            if l in medians_by_sub and any(v is not None for v in medians_by_sub[l])
        ]
    if not active:
        return

    charts = []
    for label in active:
        has_data = label in medians_by_sub and any(
            v is not None for v in medians_by_sub[label]
        )
        if has_data:
            vals = medians_by_sub[label]
            q1v = q1_by_sub[label]
            q3v = q3_by_sub[label]
            d = [dt.isoformat() for dt, v in zip(dates, vals) if v is not None]
            m = [round(v, 4) for v in vals if v is not None]
            q1 = [round(q, 4) for q, v in zip(q1v, vals) if v is not None]
            q3 = [round(q, 4) for q, v in zip(q3v, vals) if v is not None]
            charts.append({"label": label, "dates": d, "median": m, "q1": q1, "q3": q3})
        else:
            charts.append(
                {"label": label, "dates": [], "median": [], "q1": [], "q3": []}
            )

    if collected is not None:
        collected.append(
            {
                "title": section_title,
                "charts": charts,
                "cols": min(len(active), max_cols),
            }
        )


# ── Helpers ──


def ram_sort_key(t):
    m = re.match(r"DDR(\d)-(\d+) (\d+)x(\d+)GB", t)
    gen, speed, count, size = int(m[1]), int(m[2]), int(m[3]), int(m[4])
    return (gen, speed, count * size)


def get_cpu_tier(title):
    for pattern, label in [
        (r"Core Ultra 9", "Core Ultra 9"),
        (r"Core Ultra 7", "Core Ultra 7"),
        (r"Core Ultra 5", "Core Ultra 5"),
        (r"Ryzen 9", "Ryzen 9"),
        (r"Ryzen 7", "Ryzen 7"),
        (r"Ryzen 5", "Ryzen 5"),
        (r"i9[- ]|Core i9", "Core i9"),
        (r"i7[- ]|Core i7", "Core i7"),
        (r"i5[- ]|Core i5", "Core i5"),
        (r"i3[- ]|Core i3", "Core i3"),
    ]:
        if re.search(pattern, title, re.IGNORECASE):
            return label
    return None


def format_capacity(capacity_gb):
    if capacity_gb >= 1000:
        return f"{capacity_gb // 1000} TB"
    return f"{capacity_gb} GB"


GPU_MODELS = [
    # RTX 30 series (longer strings first)
    "GeForce RTX 3060 Ti",
    "GeForce RTX 3060",
    "GeForce RTX 3070 Ti",
    "GeForce RTX 3070",
    "GeForce RTX 3080 Ti",
    "GeForce RTX 3080",
    "GeForce RTX 3090 Ti",
    "GeForce RTX 3090",
    # RTX 40 series
    "GeForce RTX 4060 Ti",
    "GeForce RTX 4060",
    "GeForce RTX 4070 Ti SUPER",
    "GeForce RTX 4070 Ti",
    "GeForce RTX 4070 SUPER",
    "GeForce RTX 4070",
    "GeForce RTX 4080 SUPER",
    "GeForce RTX 4080",
    "GeForce RTX 4090",
    # RTX 50 series
    "GeForce RTX 5060 Ti",
    "GeForce RTX 5060",
    "GeForce RTX 5070 Ti",
    "GeForce RTX 5070",
    "GeForce RTX 5080",
    "GeForce RTX 5090",
    # Radeon RX 6000 series (longer strings first)
    "Radeon RX 6600 XT",
    "Radeon RX 6600",
    "Radeon RX 6650 XT",
    "Radeon RX 6700 XT",
    "Radeon RX 6700",
    "Radeon RX 6750 XT",
    "Radeon RX 6800 XT",
    "Radeon RX 6800",
    "Radeon RX 6900 XT",
    "Radeon RX 6950 XT",
    # Radeon RX 7000 series
    "Radeon RX 7600 XT",
    "Radeon RX 7600",
    "Radeon RX 7700 XT",
    "Radeon RX 7700",
    "Radeon RX 7800 XT",
    "Radeon RX 7800",
    "Radeon RX 7900 XTX",
    "Radeon RX 7900 XT",
    "Radeon RX 7900 GRE",
    # Radeon RX 9000 series
    "Radeon RX 9060 XT",
    "Radeon RX 9070 XT",
    "Radeon RX 9070",
    # Intel Arc
    "Arc B580",
    "Arc B570",
    "Arc A770",
    "Arc A750",
    "Arc A380",
]


def get_gpu_category(title):
    title_lower = title.lower()
    for model in GPU_MODELS:
        if model.lower() in title_lower:
            return model
    return None


# ── Stat computation helpers ──


def _append_stats(label, prices, med_d, q1_d, q3_d):
    med_d[label].append(median(prices) / 1e6)
    if len(prices) >= 2:
        qs = quantiles(prices, n=4)
        q1_d[label].append(qs[0] / 1e6)
        q3_d[label].append(qs[2] / 1e6)
    else:
        q1_d[label].append(prices[0] / 1e6)
        q3_d[label].append(prices[0] / 1e6)


def _append_none(label, med_d, q1_d, q3_d):
    med_d[label].append(None)
    q1_d[label].append(None)
    q3_d[label].append(None)


# ── HTML template ──

HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hardware Prices</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3"></script>
<style>
  :root { --bg: #fff; --fg: #222; --card: #fafafa; --border: #ddd; --muted: #888; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #1a1a2e; --fg: #e0e0e0; --card: #16213e; --border: #333; --muted: #999; }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, -apple-system, sans-serif; background: var(--bg); color: var(--fg); padding: 20px; }
  .container { max-width: 1400px; margin: 0 auto; }
  h1 { text-align: center; margin-bottom: 4px; font-size: 1.8rem; }
  .subtitle { text-align: center; color: var(--muted); margin-bottom: 30px; font-size: 0.9rem; }
  .subtitle a { color: var(--muted); }
  h2 { margin-top: 40px; margin-bottom: 16px; padding-bottom: 8px; border-bottom: 2px solid var(--border); font-size: 1.3rem; }
  .grid { display: grid; gap: 16px; }
  .chart-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
  .chart-card h3 { font-size: 0.85rem; margin-bottom: 8px; text-align: center; }
  .chart-card .no-data { display: flex; align-items: center; justify-content: center; height: 200px; color: var(--muted); font-style: italic; }
  .info-box { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px 20px; margin-bottom: 30px; font-size: 0.9rem; line-height: 1.6; }
  .info-box h3 { font-size: 0.95rem; margin-bottom: 8px; }
  .info-box ul { margin: 0; padding-left: 20px; }
  .info-box li { margin-bottom: 2px; }
  .info-box .note { margin-top: 8px; color: var(--muted); font-size: 0.85rem; }
  canvas { width: 100%% !important; }
</style>
</head>
<body>
<div class="container">
  <h1>Hardware Prices</h1>
  <p class="subtitle">Generated on %(generated_on)s &mdash; Created by <a href="https://x.com/ro_rre">@ro_rre</a></p>
  <div class="info-box">
    <h3>Data Sources</h3>
    <ul>
      <li><strong>EnterKomputer</strong></li>
      <li><strong>NanoKomputer</strong></li>
      <li><strong>Rakitan</strong></li>
      <li><strong>Agres</strong> (from 1 March 2026)</li>
      <li><strong>Tokopedia</strong> (from 2 March 2026)</li>
    </ul>
    <p>Other sources may be added in the future.</p>
    <p class="note">Adding new sources may cause visible shifts in median prices on the dates they were introduced.</p>
  </div>
  <div class="info-box">
    <h3>Regarding Tokopedia Prices</h3>
    <p>I am well aware that the price for Tokopedia on the PC and Mobile version is different, where the mobile version is usually cheaper because of discounts.</p>
    <p>Because of it, I must disclose that the price here is <strong>based on the Tokopedia PC version</strong>.</p>
  </div>
  <div class="info-box">
    <h3>Changelog</h3>
    <ul>
      <li><strong>11 March 2026</strong>: Improvement to Tokopedia searches, data is now properly cleaned up before calculation.</li>
    </ul>
  </div>
  %(sections_html)s
</div>
<script>
const SECTIONS = %(sections_json)s;

function isDark() {
  return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function getGridColor() { return isDark() ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.08)'; }
function getTickColor() { return isDark() ? '#aaa' : '#666'; }

function createChart(canvasId, chart) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: chart.dates,
      datasets: [
        {
          label: 'Q3',
          data: chart.q3,
          borderColor: 'transparent',
          backgroundColor: 'rgba(100,149,237,0.15)',
          fill: '+1',
          pointRadius: 0,
          tension: 0.3,
        },
        {
          label: 'Q1',
          data: chart.q1,
          borderColor: 'transparent',
          backgroundColor: 'transparent',
          fill: false,
          pointRadius: 0,
          tension: 0.3,
        },
        {
          label: 'Median',
          data: chart.median,
          borderColor: 'rgb(59,130,246)',
          backgroundColor: 'rgb(59,130,246)',
          borderWidth: 2,
          pointRadius: 4,
          pointHoverRadius: 6,
          fill: false,
          tension: 0.3,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            title: function(items) { return items[0].label; },
            label: function(item) {
              if (item.datasetIndex === 2) return 'Median: ' + item.formattedValue + ' M IDR';
              if (item.datasetIndex === 0) return 'Q3: ' + item.formattedValue + ' M IDR';
              if (item.datasetIndex === 1) return 'Q1: ' + item.formattedValue + ' M IDR';
              return '';
            },
          },
          filter: function(item) { return true; },
        },
      },
      scales: {
        x: {
          type: 'time',
          time: { unit: 'day', tooltipFormat: 'yyyy-MM-dd', displayFormats: { day: 'MM-dd' } },
          grid: { color: getGridColor() },
          ticks: { color: getTickColor(), maxRotation: 45 },
        },
        y: {
          title: { display: true, text: 'Million IDR', color: getTickColor() },
          grid: { color: getGridColor() },
          ticks: { color: getTickColor() },
          beginAtZero: false,
        },
      },
    },
  });
}

let chartIdx = 0;
SECTIONS.forEach(function(section) {
  section.charts.forEach(function(chart) {
    if (chart.dates.length > 0) {
      createChart('chart-' + chartIdx, chart);
    }
    chartIdx++;
  });
});
</script>
</body>
</html>
"""


def main():
    data_dir = Path("data")
    date_dirs = sorted(d.name for d in data_dir.iterdir() if d.is_dir())
    dates = [date.fromisoformat(d) for d in date_dirs]
    all_data_by_date = {}
    for dt in dates:
        raw = load_all_data(dt)
        cleaned = {}
        for cat, items in raw.items():
            seen: set[tuple[str, str]] = set()
            deduped = []
            for item in items:
                price = int(item.price)
                if price <= 0:
                    continue
                key = (item.title.strip().lower(), item.price.strip())
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(item)
            cleaned[cat] = deduped
        all_data_by_date[dt] = cleaned

    collected = []

    # ── RAM ──
    ALL_RAM_LABELS = sorted([rt.value for rt in RAMType], key=ram_sort_key)
    ram_med = defaultdict(list)
    ram_q1 = defaultdict(list)
    ram_q3 = defaultdict(list)
    for dt in dates:
        prods = all_data_by_date[dt].get(ProductCategory.RAM, [])
        prodinfos = [
            result_to_product_info(
                x.title + " " + (x.detail or ""), ProductCategory.RAM, int(x.price)
            )
            for x in prods
        ]
        infos = [
            x for x in prodinfos if x is not None and isinstance(x.details, RAMInfo)
        ]
        prices_by_type: dict[str, list[int]] = defaultdict(list)
        for item in infos:
            prices_by_type[item.details.ram_type.value].append(item.price)
        for label in ALL_RAM_LABELS:
            if label in prices_by_type:
                _append_stats(label, prices_by_type[label], ram_med, ram_q1, ram_q3)
            else:
                _append_none(label, ram_med, ram_q1, ram_q3)
    collect_chart_data(
        dates,
        ram_med,
        ram_q1,
        ram_q3,
        ALL_RAM_LABELS,
        "RAM",
        show_all=True,
        collected=collected,
    )

    # ── CPU ──
    GEN_LABELS = {
        CPUGeneration.AMD_AM4: "Zen 3 (AM4)",
        CPUGeneration.AMD_AM5_Zen4: "Zen 4 (AM5)",
        CPUGeneration.AMD_AM5_Zen5: "Zen 5 (AM5)",
        CPUGeneration.Intel_LGA1700_AlderLake: "Alder Lake (LGA1700)",
        CPUGeneration.Intel_LGA1700_RaptorLake: "Raptor Lake (LGA1700)",
        CPUGeneration.Intel_LGA1851: "Arrow Lake (LGA1851)",
    }
    AMD_CPU_CATEGORIES = [
        "Ryzen 5 Zen 3 (AM4)",
        "Ryzen 7 Zen 3 (AM4)",
        "Ryzen 9 Zen 3 (AM4)",
        "Ryzen 5 Zen 4 (AM5)",
        "Ryzen 7 Zen 4 (AM5)",
        "Ryzen 9 Zen 4 (AM5)",
        "Ryzen 5 Zen 5 (AM5)",
        "Ryzen 7 Zen 5 (AM5)",
        "Ryzen 9 Zen 5 (AM5)",
    ]
    INTEL_CPU_CATEGORIES = [
        "Core i3 Alder Lake (LGA1700)",
        "Core i5 Alder Lake (LGA1700)",
        "Core i7 Alder Lake (LGA1700)",
        "Core i9 Alder Lake (LGA1700)",
        "Core i3 Raptor Lake (LGA1700)",
        "Core i5 Raptor Lake (LGA1700)",
        "Core i7 Raptor Lake (LGA1700)",
        "Core i9 Raptor Lake (LGA1700)",
        "Core Ultra 5 Arrow Lake (LGA1851)",
        "Core Ultra 7 Arrow Lake (LGA1851)",
        "Core Ultra 9 Arrow Lake (LGA1851)",
    ]
    ALL_CPU_CATEGORIES = AMD_CPU_CATEGORIES + INTEL_CPU_CATEGORIES
    cpu_med = defaultdict(list)
    cpu_q1 = defaultdict(list)
    cpu_q3 = defaultdict(list)
    for dt in dates:
        prods = all_data_by_date[dt].get(ProductCategory.PROCESSOR, [])
        prices_by_cpu: dict[str, list[int]] = defaultdict(list)
        for x in prods:
            title = x.title + " " + (x.detail or "")
            info = result_to_product_info(
                title, ProductCategory.PROCESSOR, int(x.price)
            )
            if info is None or not isinstance(info.details, CPUInfo):
                continue
            tier = get_cpu_tier(title)
            if tier is None:
                continue
            gen_label = GEN_LABELS.get(info.details.generation, "")
            label = f"{tier} {gen_label}"
            if label in ALL_CPU_CATEGORIES:
                prices_by_cpu[label].append(info.price)
        for label in ALL_CPU_CATEGORIES:
            if label in prices_by_cpu:
                _append_stats(label, prices_by_cpu[label], cpu_med, cpu_q1, cpu_q3)
            else:
                _append_none(label, cpu_med, cpu_q1, cpu_q3)
    collect_chart_data(
        dates,
        cpu_med,
        cpu_q1,
        cpu_q3,
        AMD_CPU_CATEGORIES,
        "AMD CPU",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        cpu_med,
        cpu_q1,
        cpu_q3,
        INTEL_CPU_CATEGORIES,
        "Intel CPU",
        show_all=True,
        max_cols=4,
        collected=collected,
    )

    # ── PSU ──
    PSU_CATEGORIES = [
        "500W - 799W 80+ Bronze",
        "500W - 799W 80+ Gold",
        "500W - 799W 80+ Platinum",
        "800W - 999W 80+ Bronze",
        "800W - 999W 80+ Gold",
        "800W - 999W 80+ Platinum",
        "1000W - 1199W 80+ Bronze",
        "1000W - 1199W 80+ Gold",
        "1000W - 1199W 80+ Platinum",
        "1200W - 1499W 80+ Gold",
        "1200W - 1499W 80+ Platinum",
        "1500W - 2000W 80+ Gold",
        "1500W - 2000W 80+ Platinum",
    ]
    psu_med = defaultdict(list)
    psu_q1 = defaultdict(list)
    psu_q3 = defaultdict(list)
    for dt in dates:
        prods = all_data_by_date[dt].get(ProductCategory.PSU, [])
        prices_by_psu: dict[str, list[int]] = defaultdict(list)
        for x in prods:
            title = x.title + " " + (x.detail or "")
            info = result_to_product_info(title, ProductCategory.PSU, int(x.price))
            if info is None or not isinstance(info.details, PSUInfo):
                continue
            try:
                power_range = info.details.power_range
            except ValueError:
                continue
            label = f"{power_range.value} 80+ {info.details.psu_type.value}"
            if label in PSU_CATEGORIES:
                prices_by_psu[label].append(info.price)
        for label in PSU_CATEGORIES:
            if label in prices_by_psu:
                _append_stats(label, prices_by_psu[label], psu_med, psu_q1, psu_q3)
            else:
                _append_none(label, psu_med, psu_q1, psu_q3)
    collect_chart_data(
        dates,
        psu_med,
        psu_q1,
        psu_q3,
        PSU_CATEGORIES,
        "PSU",
        show_all=True,
        collected=collected,
    )

    # ── Disk ──
    DISK_TYPE_LABELS = {DiskType.SSD: "Solid State Drive", DiskType.HDD: "Hard Drive"}
    SSD_SATA_CATEGORIES = [
        'Solid State Drive - 2.5" SATA 256 GB',
        'Solid State Drive - 2.5" SATA 512 GB',
        'Solid State Drive - 2.5" SATA 1 TB',
        'Solid State Drive - 2.5" SATA 2 TB',
    ]
    SSD_NVME_CATEGORIES = [
        "Solid State Drive - M.2 NVME 256 GB",
        "Solid State Drive - M.2 NVME 512 GB",
        "Solid State Drive - M.2 NVME 1 TB",
        "Solid State Drive - M.2 NVME 2 TB",
        "Solid State Drive - M.2 NVME 4 TB",
    ]
    HDD_SATA_CATEGORIES = [
        'Hard Drive - 3.5" SATA 1 TB',
        'Hard Drive - 3.5" SATA 2 TB',
        'Hard Drive - 3.5" SATA 4 TB',
        'Hard Drive - 3.5" SATA 6 TB',
        'Hard Drive - 3.5" SATA 8 TB',
        'Hard Drive - 3.5" SATA 10 TB',
        'Hard Drive - 3.5" SATA 12 TB',
        'Hard Drive - 3.5" SATA 16 TB',
    ]
    ALL_DISK_CATEGORIES = (
        SSD_SATA_CATEGORIES + SSD_NVME_CATEGORIES + HDD_SATA_CATEGORIES
    )
    disk_med = defaultdict(list)
    disk_q1 = defaultdict(list)
    disk_q3 = defaultdict(list)
    for dt in dates:
        ssd_prods = all_data_by_date[dt].get(ProductCategory.SSD, [])
        hdd_prods = all_data_by_date[dt].get(ProductCategory.HARDDISK, [])
        prices_by_disk: dict[str, list[int]] = defaultdict(list)
        for cat, prods in [
            (ProductCategory.SSD, ssd_prods),
            (ProductCategory.HARDDISK, hdd_prods),
        ]:
            for x in prods:
                title = x.title + " " + (x.detail or "")
                info = result_to_product_info(title, cat, int(x.price))
                if info is None or not isinstance(info.details, DiskInfo):
                    continue
                d = info.details
                type_label = DISK_TYPE_LABELS[d.disk_type]
                label = f"{type_label} - {d.form_factor.value} {format_capacity(d.capacity_gb)}"
                if label in ALL_DISK_CATEGORIES:
                    prices_by_disk[label].append(info.price)
        for label in ALL_DISK_CATEGORIES:
            if label in prices_by_disk:
                _append_stats(label, prices_by_disk[label], disk_med, disk_q1, disk_q3)
            else:
                _append_none(label, disk_med, disk_q1, disk_q3)
    collect_chart_data(
        dates,
        disk_med,
        disk_q1,
        disk_q3,
        SSD_SATA_CATEGORIES,
        "SSD SATA",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        disk_med,
        disk_q1,
        disk_q3,
        SSD_NVME_CATEGORIES,
        "SSD NVME",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        disk_med,
        disk_q1,
        disk_q3,
        HDD_SATA_CATEGORIES,
        "HDD SATA",
        show_all=True,
        collected=collected,
    )

    # ── GPU ──
    NVIDIA_RTX30_ORDER = [
        "GeForce RTX 3060",
        "GeForce RTX 3060 Ti",
        "GeForce RTX 3070",
        "GeForce RTX 3070 Ti",
        "GeForce RTX 3080",
        "GeForce RTX 3080 Ti",
        "GeForce RTX 3090",
        "GeForce RTX 3090 Ti",
    ]
    NVIDIA_RTX40_ORDER = [
        "GeForce RTX 4060",
        "GeForce RTX 4060 Ti",
        "GeForce RTX 4070",
        "GeForce RTX 4070 SUPER",
        "GeForce RTX 4070 Ti",
        "GeForce RTX 4070 Ti SUPER",
        "GeForce RTX 4080",
        "GeForce RTX 4080 SUPER",
        "GeForce RTX 4090",
    ]
    NVIDIA_RTX50_ORDER = [
        "GeForce RTX 5060",
        "GeForce RTX 5060 Ti",
        "GeForce RTX 5070",
        "GeForce RTX 5070 Ti",
        "GeForce RTX 5080",
        "GeForce RTX 5090",
    ]
    AMD_RX6000_ORDER = [
        "Radeon RX 6600",
        "Radeon RX 6600 XT",
        "Radeon RX 6650 XT",
        "Radeon RX 6700",
        "Radeon RX 6700 XT",
        "Radeon RX 6750 XT",
        "Radeon RX 6800",
        "Radeon RX 6800 XT",
        "Radeon RX 6900 XT",
        "Radeon RX 6950 XT",
    ]
    AMD_RX7000_ORDER = [
        "Radeon RX 7600",
        "Radeon RX 7600 XT",
        "Radeon RX 7700",
        "Radeon RX 7700 XT",
        "Radeon RX 7800",
        "Radeon RX 7800 XT",
        "Radeon RX 7900 GRE",
        "Radeon RX 7900 XT",
        "Radeon RX 7900 XTX",
    ]
    AMD_RX9000_ORDER = [
        "Radeon RX 9060 XT",
        "Radeon RX 9070",
        "Radeon RX 9070 XT",
    ]
    INTEL_ARC_A_ORDER = ["Arc A380", "Arc A750", "Arc A770"]
    INTEL_ARC_B_ORDER = ["Arc B570", "Arc B580"]
    ALL_GPU_ORDER = (
        NVIDIA_RTX30_ORDER
        + NVIDIA_RTX40_ORDER
        + NVIDIA_RTX50_ORDER
        + AMD_RX6000_ORDER
        + AMD_RX7000_ORDER
        + AMD_RX9000_ORDER
        + INTEL_ARC_A_ORDER
        + INTEL_ARC_B_ORDER
    )
    gpu_med = defaultdict(list)
    gpu_q1 = defaultdict(list)
    gpu_q3 = defaultdict(list)
    for dt in dates:
        prods = all_data_by_date[dt].get(ProductCategory.VGA, [])
        prices_by_gpu: dict[str, list[int]] = defaultdict(list)
        for x in prods:
            title = x.title + " " + (x.detail or "")
            model = get_gpu_category(title)
            if model is None:
                continue
            prices_by_gpu[model].append(int(x.price))
        for label in ALL_GPU_ORDER:
            if label in prices_by_gpu:
                _append_stats(label, prices_by_gpu[label], gpu_med, gpu_q1, gpu_q3)
            else:
                _append_none(label, gpu_med, gpu_q1, gpu_q3)
    collect_chart_data(
        dates,
        gpu_med,
        gpu_q1,
        gpu_q3,
        NVIDIA_RTX30_ORDER,
        "NVIDIA RTX 30 Series",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        gpu_med,
        gpu_q1,
        gpu_q3,
        NVIDIA_RTX40_ORDER,
        "NVIDIA RTX 40 Series",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        gpu_med,
        gpu_q1,
        gpu_q3,
        NVIDIA_RTX50_ORDER,
        "NVIDIA RTX 50 Series",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        gpu_med,
        gpu_q1,
        gpu_q3,
        AMD_RX6000_ORDER,
        "Radeon RX 6000 Series",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        gpu_med,
        gpu_q1,
        gpu_q3,
        AMD_RX7000_ORDER,
        "Radeon RX 7000 Series",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        gpu_med,
        gpu_q1,
        gpu_q3,
        AMD_RX9000_ORDER,
        "Radeon RX 9000 Series",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        gpu_med,
        gpu_q1,
        gpu_q3,
        INTEL_ARC_A_ORDER,
        "Intel Arc A Series",
        show_all=True,
        collected=collected,
    )
    collect_chart_data(
        dates,
        gpu_med,
        gpu_q1,
        gpu_q3,
        INTEL_ARC_B_ORDER,
        "Intel Arc B Series",
        show_all=True,
        collected=collected,
    )

    # ── Build HTML ──
    chart_idx = 0
    sections_html_parts = []
    total_charts = 0
    for section in collected:
        sections_html_parts.append(f"<h2>{section['title']}</h2>")
        cols = section["cols"]
        sections_html_parts.append(
            f'<div class="grid" style="grid-template-columns: repeat({cols}, 1fr);">'
        )
        for chart in section["charts"]:
            sections_html_parts.append('<div class="chart-card">')
            sections_html_parts.append(f"<h3>{chart['label']}</h3>")
            if chart["dates"]:
                sections_html_parts.append(
                    f'<div style="position:relative;height:220px;"><canvas id="chart-{chart_idx}"></canvas></div>'
                )
            else:
                sections_html_parts.append(
                    '<div class="no-data">No data available</div>'
                )
            sections_html_parts.append("</div>")
            chart_idx += 1
            total_charts += 1
        sections_html_parts.append("</div>")

    dt_str = datetime.now().isoformat(sep=" ", timespec="seconds")
    html = HTML_TEMPLATE % {
        "generated_on": dt_str,
        "sections_html": "\n  ".join(sections_html_parts),
        "sections_json": json.dumps(collected),
    }

    output_dir = Path("_site")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / "index.html"
    output_path.write_text(html, encoding="utf-8")
    print(
        f"Exported {total_charts} charts across {len(collected)} sections to {output_path}"
    )


if __name__ == "__main__":
    main()
