from pathlib import Path

import pytest

from verify_offline_qa_target import validate_browser_proof

SHA = 'a' * 40
PROOF = {
    'revision': SHA, 'project': 'weather-course-qa-sample',
    'qa_url': 'http://127.0.0.1:18589', 'mysql_volume': 'weather-course-qa-sample_mysql_data',
    'api_image_id': 'sha256:' + 'b' * 64, 'frontend_image_id': 'sha256:' + 'c' * 64,
}


def test_browser_write_proof_matches_disposable_project_and_local_relay():
    validate_browser_proof(PROOF, PROOF['qa_url'], SHA)
    validate_browser_proof(PROOF | {'test_url': 'http://127.0.0.1:52200'}, 'http://127.0.0.1:52200', SHA)


@pytest.mark.parametrize('proof', [
    PROOF | {'revision': 'd' * 40},
    PROOF | {'project': 'weather-course-demo'},
    PROOF | {'mysql_volume': 'weather-course-demo_mysql_data'},
    PROOF | {'api_image_id': 'weather-course-api:latest'},
    PROOF | {'test_url': 'http://127.0.0.1:18590'},
])
def test_browser_write_proof_rejects_wrong_project_volume_revision_or_url(proof):
    with pytest.raises(ValueError):
        validate_browser_proof(proof, PROOF['qa_url'], SHA)
