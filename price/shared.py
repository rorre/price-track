from enum import Enum
import re
from typing import Optional
from pydantic import BaseModel

CATEGORIES = ["processor", "motherboard", "ram", "ssd", "harddisk", "vga", "psu"]


class ProductCategory(Enum):
    PROCESSOR = "processor"
    MOTHERBOARD = "motherboard"
    RAM = "ram"
    SSD = "ssd"
    HARDDISK = "harddisk"
    VGA = "vga"
    PSU = "psu"


class Brand(Enum):
    INTEL = "Intel"
    AMD = "AMD"
    NVIDIA = "NVIDIA"


class CPUGeneration(Enum):
    AMD_AM4 = "AM4"
    AMD_AM5_Zen4 = "AM5-Zen4"
    AMD_AM5_Zen5 = "AM5-Zen5"
    Intel_LGA1700_AlderLake = "LGA1700-AlderLake"
    Intel_LGA1700_RaptorLake = "LGA1700-RaptorLake"
    Intel_LGA1851 = "LGA1851"


class RAMType(Enum):
    DDR4_3000_2x8GB = "DDR4-3000 2x8GB"
    DDR4_3000_2x16GB = "DDR4-3000 2x16GB"
    DDR4_3000_2x32GB = "DDR4-3000 2x32GB"
    DDR4_3200_2x8GB = "DDR4-3200 2x8GB"
    DDR4_3200_2x16GB = "DDR4-3200 2x16GB"
    DDR4_3200_2x32GB = "DDR4-3200 2x32GB"
    DDR4_3600_2x8GB = "DDR4-3600 2x8GB"
    DDR4_3600_2x16GB = "DDR4-3600 2x16GB"
    DDR4_3600_2x32GB = "DDR4-3600 2x32GB"
    DDR5_4800_2x8GB = "DDR5-4800 2x8GB"
    DDR5_4800_2x16GB = "DDR5-4800 2x16GB"
    DDR5_4800_2x32GB = "DDR5-4800 2x32GB"
    DDR5_5200_2x8GB = "DDR5-5200 2x8GB"
    DDR5_5200_2x16GB = "DDR5-5200 2x16GB"
    DDR5_5200_2x32GB = "DDR5-5200 2x32GB"
    DDR5_5600_2x8GB = "DDR5-5600 2x8GB"
    DDR5_5600_2x16GB = "DDR5-5600 2x16GB"
    DDR5_5600_2x32GB = "DDR5-5600 2x32GB"
    DDR5_6000_2x8GB = "DDR5-6000 2x8GB"
    DDR5_6000_2x16GB = "DDR5-6000 2x16GB"
    DDR5_6000_2x32GB = "DDR5-6000 2x32GB"


class PSUType(Enum):
    BRONZE = "Bronze"
    GOLD = "Gold"
    PLATINUM = "Platinum"


class PSUPower(Enum):
    W500_799 = "500W - 799W"
    W800_999 = "800W - 999W"
    W1000_1199 = "1000W - 1199W"
    W1200_1499 = "1200W - 1499W"
    W1500_2000 = "1500W - 2000W"


class DiskType(Enum):
    SSD = "SSD"
    HDD = "HDD"


class FormFactor(Enum):
    SATA_25 = '2.5" SATA'
    SATA_35 = '3.5" SATA'
    M2_NVME = "M.2 NVME"


class MotherboardInfo(BaseModel):
    brand: Brand
    chipset: str
    socket: str


class CPUInfo(BaseModel):
    brand: Brand
    generation: CPUGeneration
    cores: int
    threads: int
    base_clock: float
    boost_clock: float


class RAMInfo(BaseModel):
    ram_type: RAMType
    capacity_gb: int
    speed_mhz: int


class GPUInfo(BaseModel):
    brand: Brand
    model: str
    vram_gb: int
    base_clock: float
    boost_clock: float


class PSUInfo(BaseModel):
    psu_type: PSUType
    power: int

    @property
    def power_range(self) -> PSUPower:
        if 500 <= self.power <= 799:
            return PSUPower.W500_799
        elif 800 <= self.power <= 999:
            return PSUPower.W800_999
        elif 1000 <= self.power <= 1199:
            return PSUPower.W1000_1199
        elif 1200 <= self.power <= 1499:
            return PSUPower.W1200_1499
        elif 1500 <= self.power <= 2000:
            return PSUPower.W1500_2000
        else:
            raise ValueError("Power must be between 500W and 2000W.")


class DiskInfo(BaseModel):
    disk_type: DiskType
    capacity_gb: int
    form_factor: FormFactor


class ProductInfo(BaseModel):
    category: ProductCategory
    price: int
    details: DiskInfo | PSUInfo | RAMInfo | CPUInfo | GPUInfo


def _detect_cpu_generation(name: str, brand: Brand) -> Optional[CPUGeneration]:
    if brand == Brand.AMD:
        if "AM5" in name:
            if re.search(r"Ryzen\s+\d+\s+9\d{3}", name):
                return CPUGeneration.AMD_AM5_Zen5
            return CPUGeneration.AMD_AM5_Zen4
        if "AM4" in name:
            return CPUGeneration.AMD_AM4
    elif brand == Brand.INTEL:
        if re.search(r"LGA\s*1851", name):
            return CPUGeneration.Intel_LGA1851
        if re.search(r"LGA\s*1700", name):
            if re.search(r"Raptor", name, re.IGNORECASE):
                return CPUGeneration.Intel_LGA1700_RaptorLake
            # 13th/14th gen → Raptor Lake
            if re.search(r"i\d-1[34]\d{2}", name):
                return CPUGeneration.Intel_LGA1700_RaptorLake
            return CPUGeneration.Intel_LGA1700_AlderLake
    return None


def _parse_cpu_info(name: str) -> Optional[CPUInfo]:
    if "Intel" in name:
        brand = Brand.INTEL
    elif "AMD" in name:
        brand = Brand.AMD
    else:
        return None

    base_match = re.search(r"(\d+\.?\d*)\s*[Gg][Hh]z", name)
    if not base_match:
        return None
    base_clock = float(base_match.group(1))

    boost_match = re.search(r"[Uu]p\s+[Tt]o\s+(\d+\.?\d*)\s*[Gg][Hh]z", name)
    boost_clock = float(boost_match.group(1)) if boost_match else base_clock

    core_match = re.search(r"(\d+)\s*[Cc]ore", name)
    cores = int(core_match.group(1)) if core_match else 0
    threads = cores

    generation = _detect_cpu_generation(name, brand)
    if generation is None:
        return None

    return CPUInfo(
        brand=brand,
        generation=generation,
        cores=cores,
        threads=threads,
        base_clock=base_clock,
        boost_clock=boost_clock,
    )


def _parse_ram_info(name: str) -> Optional[RAMInfo]:
    ddr_match = re.search(r"DDR(\d)", name, re.IGNORECASE)
    if not ddr_match:
        return None
    ddr_version = int(ddr_match.group(1))

    speed_match = re.search(r"(\d{4,5})\s*MHz", name, re.IGNORECASE)
    if speed_match:
        speed_mhz = int(speed_match.group(1))
    else:
        ddr_speed_match = re.search(r"DDR\d[- ](\d{4,5})", name, re.IGNORECASE)
        if ddr_speed_match:
            speed_mhz = int(ddr_speed_match.group(1))
        else:
            pc_match = re.search(r"PC\d?[- ]?(\d{4,6})", name)
            if pc_match:
                pc_value = int(pc_match.group(1))
                speed_mhz = pc_value // 8 if pc_value > 10000 else pc_value
            else:
                return None

    kit_match = re.search(r"\(?(\d+)x(\d+)GB\)?", name, re.IGNORECASE)
    if kit_match:
        kit_count = int(kit_match.group(1))
        kit_size = int(kit_match.group(2))
        kit_config = f"{kit_count}x{kit_size}GB"
        capacity_gb = kit_count * kit_size
    else:
        capacity_match = re.search(r"(\d+)GB", name, re.IGNORECASE)
        if not capacity_match:
            return None
        capacity_gb = int(capacity_match.group(1))
        kit_config = f"1x{capacity_gb}GB"

    ram_type_str = f"DDR{ddr_version}-{speed_mhz} {kit_config}"
    try:
        ram_type = RAMType(ram_type_str)
    except ValueError:
        return None

    return RAMInfo(ram_type=ram_type, capacity_gb=capacity_gb, speed_mhz=speed_mhz)


def _parse_gpu_info(name: str) -> Optional[GPUInfo]:
    if "GeForce" in name or "GTX" in name or "RTX" in name:
        brand = Brand.NVIDIA
    elif "Radeon" in name:
        brand = Brand.AMD
    elif "ARC" in name:
        brand = Brand.INTEL
    else:
        return None

    vram_match = re.search(r"(\d+)\s*GB", name, re.IGNORECASE)
    if not vram_match:
        return None
    vram_gb = int(vram_match.group(1))

    model_match = re.search(
        r"((?:GeForce\s+)?(?:GT|GTX|RTX)\s+\d\S*|Radeon\s+RX\s+\d\S*|ARC\s+\w+)",
        name,
    )
    model = model_match.group(1).strip() if model_match else ""

    return GPUInfo(
        brand=brand, model=model, vram_gb=vram_gb, base_clock=0.0, boost_clock=0.0
    )


def _parse_psu_info(name: str) -> Optional[PSUInfo]:
    watt_match = re.search(r"(\d+)\s*W\b", name)
    if not watt_match:
        return None
    power = int(watt_match.group(1))

    name_upper = name.upper()
    if "PLATINUM" in name_upper:
        psu_type = PSUType.PLATINUM
    elif "GOLD" in name_upper:
        psu_type = PSUType.GOLD
    elif "BRONZE" in name_upper:
        psu_type = PSUType.BRONZE
    else:
        return None

    return PSUInfo(psu_type=psu_type, power=power)


def _parse_disk_info(name: str, category: ProductCategory) -> Optional[DiskInfo]:
    disk_type = DiskType.SSD if category == ProductCategory.SSD else DiskType.HDD

    tb_match = re.search(r"(\d+)\s*TB", name, re.IGNORECASE)
    gb_match = re.search(r"(\d+)\s*GB", name, re.IGNORECASE)
    if tb_match:
        capacity_gb = int(tb_match.group(1)) * 1000
    elif gb_match:
        capacity_gb = int(gb_match.group(1))
    else:
        return None

    name_upper = name.upper()
    if "NVME" in name_upper or "PCIE" in name_upper:
        form_factor = FormFactor.M2_NVME
    elif category == ProductCategory.HARDDISK:
        form_factor = FormFactor.SATA_35
    else:
        form_factor = FormFactor.SATA_25

    return DiskInfo(
        disk_type=disk_type, capacity_gb=capacity_gb, form_factor=form_factor
    )


def result_to_product_info(
    name: str, category: ProductCategory, price: int
) -> Optional[ProductInfo]:
    if category == ProductCategory.PROCESSOR:
        details = _parse_cpu_info(name)
    elif category == ProductCategory.RAM:
        details = _parse_ram_info(name)
    elif category in (ProductCategory.SSD, ProductCategory.HARDDISK):
        details = _parse_disk_info(name, category)
    elif category == ProductCategory.VGA:
        details = _parse_gpu_info(name)
    elif category == ProductCategory.PSU:
        details = _parse_psu_info(name)
    else:
        return None

    if details is None:
        return None

    return ProductInfo(category=category, details=details, price=price)


def get_prices_by_ram_type(products: list[ProductInfo]) -> dict[RAMType, list[int]]:
    from collections import defaultdict

    prices: dict[RAMType, list[int]] = defaultdict(list)
    for item in products:
        if item.category == ProductCategory.RAM and isinstance(item.details, RAMInfo):
            prices[item.details.ram_type].append(item.price)
    return dict(prices)
