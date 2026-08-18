from dataclasses import dataclass, asdict
from enum import Enum
from typing import Dict, Any, Optional

class AssetClass(str, Enum):
    FOREX = "FOREX"
    METALS = "METALS"
    INDICES = "INDICES"
    CRYPTO = "CRYPTO"

@dataclass
class InstrumentSpecification:
    symbol: str
    asset_class: AssetClass
    tick_size: float
    point_size: float
    pip_size: float
    contract_size: float
    volume_min: float
    volume_max: float
    volume_step: float
    digits: int
    currency: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def get_default_spec(cls, symbol: str) -> "InstrumentSpecification":
        clean_sym = symbol.upper().replace("M", "")

        if "XAU" in clean_sym or "GOLD" in clean_sym:
            return cls(
                symbol=symbol,
                asset_class=AssetClass.METALS,
                tick_size=0.001,
                point_size=0.001,
                pip_size=0.1,
                contract_size=100.0,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
                digits=3,
                currency="USD"
            )
        elif "USTEC" in clean_sym or "NAS100" in clean_sym or "US100" in clean_sym:
            return cls(
                symbol=symbol,
                asset_class=AssetClass.INDICES,
                tick_size=0.01,
                point_size=0.01,
                pip_size=1.0,
                contract_size=1.0,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
                digits=2,
                currency="USD"
            )
        elif "EUR" in clean_sym or "GBP" in clean_sym or "USD" in clean_sym:
            is_jpy = "JPY" in clean_sym
            digits = 3 if is_jpy else 5
            pip_sz = 0.01 if is_jpy else 0.0001
            pt_sz = 0.001 if is_jpy else 0.00001
            return cls(
                symbol=symbol,
                asset_class=AssetClass.FOREX,
                tick_size=pt_sz,
                point_size=pt_sz,
                pip_size=pip_sz,
                contract_size=100000.0,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
                digits=digits,
                currency="USD"
            )
        else:
            return cls(
                symbol=symbol,
                asset_class=AssetClass.FOREX,
                tick_size=0.00001,
                point_size=0.00001,
                pip_size=0.0001,
                contract_size=100000.0,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
                digits=5,
                currency="USD"
            )
