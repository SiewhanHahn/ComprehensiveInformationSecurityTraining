"""Rebuild the 1–7 October demonstration fixture; not part of the frozen experiment."""
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

from backend.app.cities import DEFAULT_MODELS

OUT = Path(__file__).resolve().parents[1] / 'frontend/public/trial'
START = date(2026, 10, 1)
QUERY = dict(latitude='32.06', longitude='118.79', timezone='GMT', start_date=str(START), end_date='2026-10-07')


def fetch(endpoint, **params):
    url = endpoint + '?' + urlencode({**QUERY, **params})
    with urlopen(url, timeout=45) as response:
        raw = response.read()
    return json.loads(raw, parse_float=Decimal), {'url': url, 'sha256_response': sha256(raw).hexdigest()}


def totals(payload, name):
    hourly = payload['hourly']
    expected = [f'{START + timedelta(days=n // 24)}T{n % 24:02}:00' for n in range(7 * 24)]
    values = hourly[name]
    if (hourly['time'] != expected or payload['utc_offset_seconds'] != 0 or
            payload['hourly_units'][name] != 'mm' or len(values) != len(expected) or
            any(v is None or not Decimal(v).is_finite() or v < 0 for v in values)):
        raise ValueError(f'{name}: incomplete/mismatched UTC hours or units; do not publish sample')
    return [float(sum(values[i:i + 24])) for i in range(0, len(expected), 24)]


def main():
    fc, fq = fetch('https://previous-runs-api.open-meteo.com/v1/forecast', hourly='precipitation_previous_day1',
                   models=','.join(DEFAULT_MODELS))
    era, eq = fetch('https://archive-api.open-meteo.com/v1/archive', hourly='precipitation', models='era5')
    daily = {model: totals(fc, 'precipitation_previous_day1_' + model) for model in DEFAULT_MODELS}
    ref = totals(era, 'precipitation')
    rows = [dict(city='南京', valid_date=str(START + timedelta(days=i)), models={m: v[i] for m, v in daily.items()},
                 reference_mm=ref[i], reference_type='ERA5_PROXY') for i in range(7)]
    source = dict(attribution='Weather data by Open-Meteo; ECMWF, NOAA GFS, DWD ICON, ECCC GEM; ERA5 (Copernicus/ECMWF).',
                  license='https://creativecommons.org/licenses/by/4.0/', city='南京', latitude=32.06, longitude=118.79,
                  retrieved_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  hours_per_day=24, unit='mm', aggregation='UTC day sum of 24 hourly values per source; no imputation.',
                  queries=[fq, eq])
    OUT.mkdir(exist_ok=True, parents=True)
    for name, obj in [('nanjing', dict(schema_version=1, lead_hours=24, rows=rows)), ('nanjing-source', source)]:
        (OUT / f'{name}.json').write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
