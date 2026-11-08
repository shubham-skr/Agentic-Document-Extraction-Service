import json
import time
from pathlib import Path

from fastapi.testclient import TestClient


def test_post_returns_quickly_and_job_reaches_terminal_state(tmp_path, monkeypatch):
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, 'database_path', str(tmp_path / 'jobs.sqlite3'))
    monkeypatch.setattr(settings, 'upload_dir', str(tmp_path / 'uploads'))
    monkeypatch.setattr(settings, 'output_dir', str(tmp_path / 'outputs'))

    root = Path(__file__).resolve().parents[1]
    schema = (root / 'sample/schemas/boxscore.json').read_text(encoding='utf-8')
    sample = root / 'sample/sample-data-documents/boxscore_001.csv'

    with TestClient(app) as client:
        started = time.perf_counter()
        with sample.open('rb') as handle:
            response = client.post(
                '/jobs',
                files={'file': ('boxscore_001.csv', handle, 'text/csv')},
                data={'schema': schema},
            )
        post_seconds = time.perf_counter() - started
        assert response.status_code == 202
        assert post_seconds < 2.0
        job_id = response.json()['job_id']

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            poll = client.get(f'/jobs/{job_id}')
            assert poll.status_code == 200
            payload = poll.json()
            if payload['status'] in {'SUCCESS', 'PARTIAL', 'FAILED'}:
                assert payload['status'] == 'SUCCESS', payload
                assert len(payload['result']['entries']) == 10
                return
            time.sleep(0.05)
        raise AssertionError('job did not reach a terminal state within 5 seconds')
