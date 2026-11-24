"""Read-only calculation for external city-day files. Never register an external city."""
from datetime import date
from decimal import Decimal

from ..cities import DEFAULT_MODELS, LEAD_HOURS
from .replay import mean_mm


class TrialError(ValueError):
    """A safe, field-specific message; never include uploaded values."""


def _mm(value, field):
    if type(value) not in (int, float, Decimal):
        raise TrialError(f'{field}：需要非负数值（mm）')
    amount = Decimal(str(value))
    if not amount.is_finite() or not 0 <= amount <= 2000 or amount.as_tuple().exponent < -3:
        raise TrialError(f'{field}：应为 0–2000 mm 的有限数，最多三位小数')
    return amount


def calculate_trial(dataset, threshold: Decimal) -> list[dict]:
    if not isinstance(dataset, dict) or type(dataset.get('schema_version')) is not int or dataset['schema_version'] != 1:
        raise TrialError('schema_version：需要版本 1 的 JSON 模板')
    if type(dataset.get('lead_hours')) is not int or dataset['lead_hours'] != LEAD_HOURS:
        raise TrialError('lead_hours：仅支持提前 24 小时的预报')
    if set(dataset) - {'schema_version', 'lead_hours', 'rows'}:
        raise TrialError('文件包含未知字段，请使用模板')
    rows = dataset.get('rows')
    if not isinstance(rows, list) or not 1 <= len(rows) <= 200:
        raise TrialError('rows：每批需要 1–200 条记录')
    seen, output = set(), []
    for idx, row in enumerate(rows, 1):
        prefix = f'第 {idx} 行'
        if not isinstance(row, dict):
            raise TrialError(f'{prefix}：需要 JSON 对象')
        if set(row) - {'city', 'valid_date', 'models', 'reference_mm', 'reference_type'}:
            raise TrialError(f'{prefix}：未知字段，请与模板列名对照')
        city, day = row.get('city'), row.get('valid_date')
        if not isinstance(city, str) or not 1 <= len(city.strip()) <= 64:
            raise TrialError(f'{prefix} city：请填写 1–64 字的城市名')
        city = city.strip()
        if not city.isprintable():
            raise TrialError(f'{prefix} city：城市名包含不可显示字符')
        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError
        except (TypeError, ValueError):
            raise TrialError(f'{prefix} valid_date：需要有效 UTC 日期 YYYY-MM-DD') from None
        if (city, day) in seen:
            raise TrialError(f'{prefix}：城市和日期重复')
        seen.add((city, day))
        models = row.get('models')
        if not isinstance(models, dict):
            raise TrialError(f'{prefix} models：需要四路预报，参考值不能代替预报')
        values = {name: _mm(models.get(name), f'{prefix} models.{name}') for name in DEFAULT_MODELS}
        if set(models) != set(DEFAULT_MODELS):
            raise TrialError(f'{prefix} models：只接受模板列出的四种模式')
        ref, kind = None, row.get('reference_type')
        if 'reference_mm' in row or 'reference_type' in row:
            if kind not in ('ERA5_PROXY', 'STATION_OBS'):
                raise TrialError(f'{prefix} reference_type：应为 ERA5_PROXY 或 STATION_OBS')
            ref = _mm(row.get('reference_mm'), f'{prefix} reference_mm')
        base, fused = values['ecmwf_ifs025'], mean_mm(list(values.values()))
        output.append(dict(city=city, valid_date=day, models={k: float(v) for k, v in values.items()},
                           baseline_mm=float(base), baseline_hit=base >= threshold,
                           fused_mm=float(fused), fusion_hit=fused >= threshold,
                           reference_mm=float(ref) if ref is not None else None, reference_type=kind,
                           reference_hit=ref >= threshold if ref is not None else None))
    return output
