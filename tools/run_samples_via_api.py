"""Submit all eight supplied samples concurrently to the running Docker service."""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = 'http://127.0.0.1:8080'
TIMEOUT_SECONDS = 1720
POLL_SECONDS = 2
SAMPLES = [
    ('boxscore_001.csv', 'boxscore.json'),
    ('budget_001.pdf', 'budget_variance.json'),
    ('lease_001.pdf', 'lease_abstraction.json'),
    ('lease_002.docx', 'lease_abstraction.json'),
    ('lease_003.pdf', 'lease_abstraction.json'),
    ('om_001.pdf', 'offering_memorandum.json'),
    ('rentroll_001.xlsx', 'rent_roll_units.json'),
    ('t12_001.xlsx', 'operating_statement_lines.json'),
]


async def main() -> int:
    org_id = f'sample-eval-{uuid.uuid4().hex}'
    headers = {'X-Organization-Id': org_id}
    output_dir = ROOT / 'outputs'
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=httpx.Timeout(240, connect=15)) as client:
        async def submit(filename: str, schema_filename: str):
            file_path = ROOT / 'sample' / 'sample-data-documents' / filename
            schema_path = ROOT / 'sample' / 'schemas' / schema_filename
            if not file_path.is_file():
                raise FileNotFoundError(file_path)
            schema = json.loads(schema_path.read_text(encoding='utf-8'))
            started = time.perf_counter()
            with file_path.open('rb') as handle:
                response = await client.post(
                    f'{BASE_URL}/jobs',
                    headers=headers,
                    data={'schema': json.dumps(schema, ensure_ascii=False)},
                    files={'file': (filename, handle, 'application/octet-stream')},
                )
            elapsed = time.perf_counter() - started
            response.raise_for_status()
            payload = response.json()
            print(f"SUBMITTED {filename}: {payload['job_id']} (POST {elapsed:.2f}s)", flush=True)
            return filename, schema_filename, schema.get('name') or Path(schema_filename).stem, payload['job_id']

        submitted = await asyncio.gather(*(submit(*item) for item in SAMPLES))

        async def wait_for_result(item):
            filename, schema_filename, schema_name, job_id = item
            started = time.monotonic()
            while time.monotonic() - started < TIMEOUT_SECONDS:
                response = await client.get(f'{BASE_URL}/jobs/{job_id}', headers=headers)
                response.raise_for_status()
                payload = response.json()
                status = payload.get('status')
                if status in {'SUCCESS', 'PARTIAL', 'FAILED'}:
                    if status == 'FAILED' or not isinstance(payload.get('result'), dict):
                        raise RuntimeError(f'{filename} failed: {payload.get("error") or payload}')
                    result = payload['result']
                    result['schema'] = schema_name
                    target = output_dir / f'{Path(filename).stem}.json'
                    target.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
                    metadata = result.get('metadata', {})
                    print(
                        f"{status:7s} {filename}: {len(result.get('entries', []))} entries; "
                        f"{metadata.get('latency_ms', 0)/1000:.1f}s extraction; "
                        f"{metadata.get('model_calls', 0)} model calls; saved {target.relative_to(ROOT)}",
                        flush=True,
                    )
                    return status
                await asyncio.sleep(POLL_SECONDS)
            raise TimeoutError(f'{filename} did not reach a terminal state within {TIMEOUT_SECONDS}s')

        statuses = await asyncio.gather(*(wait_for_result(item) for item in submitted))
        print(f'Completed {len(statuses)}/{len(SAMPLES)} jobs: {statuses}', flush=True)
        return 0


if __name__ == '__main__':
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)
