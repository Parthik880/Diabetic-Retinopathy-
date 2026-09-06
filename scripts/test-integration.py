"""Real offline integration and input failure checks. No clinical claims."""
from pathlib import Path
import sys, json, socket, time
from unittest.mock import patch
from io import BytesIO
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app

sample = ROOT / 'resources/test-images/20170629163635747.jpg'
data = sample.read_bytes()
started = time.monotonic()
# Prove startup and inference do not use the network or silently download weights.
original_connect = socket.socket.connect
def offline_connect(sock, address):
    # Windows asyncio creates its self-pipe with a loopback socket pair.
    if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
        return original_connect(sock, address)
    raise RuntimeError('External network forbidden in offline integration test')
with patch.object(socket.socket, 'connect', offline_connect):
    with TestClient(app) as client:
        health = client.get('/health').json()
        assert set(health['models']) == {'quality', 'grading', 'lesion', 'restoration'}, health
        assert health['device'] == 'cpu' and health['device_name'] == 'CPU', health
        assert health['torch_version_cuda'] is None and health['torch_cuda_available'] is False, health
        assert set(health['model_devices'].values()) == {'cpu'}, health
        assert client.get('/api/history').json()['records'] == []
        identities = {key: id(value) for key, value in app.state.registry.models.items()}

        def analyze_eye(eye):
            queued = client.post('/api/analysis-jobs', files={'file': ('retina.jpg', data, 'image/jpeg')}, data={'eye': eye})
            assert queued.status_code == 202, queued.text
            job_id = queued.json()['job_id']
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                job = client.get(f'/api/analysis-jobs/{job_id}').json()
                if job['state'] in ('COMPLETE', 'RECAPTURE_REQUIRED', 'FAILED'):
                    break
                time.sleep(.1)
            assert job['state'] == 'COMPLETE', job
            result = job['result']
            assert result['state'] == 'COMPLETE' and result['eye'] == eye
            assert result['device'] == 'cpu' and result['device_name'] == 'CPU'
            assert result['invocation_counts'] == {'iqa': 1, 'nafnet': 0, 'grading': 1, 'lesions': 1}
            assert [item['state'] for item in result['state_history']] == [
                'WAITING', 'IQA', 'IQA_GOOD', 'GRADING', 'LESION_ANALYSIS',
                'PREPARING_RESULTS', 'COMPLETE']
            assert abs(sum(result['quality']['probabilities'].values()) - 1) < 1e-5
            assert abs(sum(result['grading']['probabilities']) - 1) < 1e-5
            assert result['grading']['predicted_grade'] in range(5)
            assert result['lesions']['channel_order'] == ['MA', 'HE', 'EX', 'SE']
            assert result['lesions']['logits_shape'] == [1, 4, 768, 768]
            assert result['grading']['device'] == 'cpu' and result['lesions']['device'] == 'cpu'
            assert client.get(result['lesions']['combined_overlay_path']).status_code == 200
            return result

        result = analyze_eye('OS')
        right_result = analyze_eye('OD')
        assert result['run_id'] != right_result['run_id']
        report_destination = ROOT / 'work' / 'test-report-api'
        report_destination.mkdir(exist_ok=True)
        exported = client.post('/api/reports/export', json={
            'destination': str(report_destination),
            'run_id': result['run_id'],
            'session_id': 'cpu-integration-session',
            'patient': {'name': 'CPU Test', 'id': 'LOCAL-TEST', 'age': 1, 'gender': 'Other', 'eye': 'OS',
                        'scan_datetime': '2026-09-05T20:00:00+05:30'},
        })
        assert exported.status_code == 200, exported.text
        report_folder = Path(exported.json()['eye_folder'])
        assert (report_folder / 'report.pdf').is_file()
        assert (report_folder / 'results.json').is_file()
        assert (report_folder / 'original_fundus.jpg').is_file()
        assert (report_folder / 'lesion_overlay.png').is_file()
        assert set(path.name for path in (report_folder / 'masks').glob('*.png')) == {
            'microaneurysm.png', 'hemorrhage.png', 'hard_exudate.png', 'soft_exudate.png'}
        assert b'Grad-CAM' not in (report_folder / 'report.pdf').read_bytes()
        assert client.post('/api/analyze', files={'file': ('bad.jpg', b'not an image')}).status_code == 400
        assert client.post('/api/analyze').status_code == 422
        image = Image.new('RGB', (12, 12)); gif = BytesIO(); image.save(gif, format='GIF')
        assert client.post('/api/analyze', files={'file': ('bad.gif', gif.getvalue())}).status_code == 415
        assert client.post('/api/analyze', files={'file': ('big.jpg', b'x' * (20*1024*1024+1))}).status_code == 413
        cors = client.options('/api/analyze', headers={'Origin': 'http://127.0.0.1:5173', 'Access-Control-Request-Method': 'POST'})
        assert cors.status_code == 200 and cors.headers['access-control-allow-origin'] == 'http://127.0.0.1:5173'
        # Exercise the failure response without replacing any successful prediction.
        with patch.object(app.state.registry.models['quality'], 'predict', side_effect=RuntimeError('controlled failure')):
            assert client.post('/api/analyze', files={'file': ('retina.jpg', data)}).status_code == 500
        # Explicit restoration compatibility smoke at full resolution of a small
        # test derivative. This is separate from the unchanged real-image analysis.
        with Image.open(sample) as original:
            derivative = original.convert('RGB').resize((128, 128))
            buffer = BytesIO(); derivative.save(buffer, format='PNG')
        restored = client.post('/api/restore', files={'file': ('restoration-smoke.png', buffer.getvalue())})
        assert restored.status_code == 200, restored.text
        assert restored.json()['width'] == 128 and restored.json()['quality'] is None
        history_payload = {
            'session_id': 'cpu-integration-session', 'patient_id': 'LOCAL-TEST',
            'patient_name': 'CPU Test', 'patient': {'id': 'cpu-test'},
            'scan_datetime': '2026-09-05T20:00:00+05:30',
            'left_eye': {'available': True, 'result_data': result},
            'right_eye': {'available': True, 'result_data': right_result},
        }
        assert client.post('/api/history/sessions', json=history_payload).status_code == 200
        saved_history = client.get('/api/history').json()['records']
        assert len(saved_history) == 1 and saved_history[0]['session_id'] == 'cpu-integration-session'
        assert identities == {key: id(value) for key, value in app.state.registry.models.items()}
        record = {'health': health, 'results': {'OS': result, 'OD': right_result},
                  'restoration': restored.json(), 'report_folder': str(report_folder),
                  'checks': ['offline startup', 'strict checkpoint loading', 'real inference', 'probabilities', 'lesion shapes',
                             'OS and OD eye isolation', 'empty history on first launch', 'atomic history persistence',
                             'single-page report bundle',
                             'artifact retrieval', 'invalid 400', 'missing 422', 'unsupported 415', 'oversized 413', 'CORS',
                             'inference failure 500', 'restoration-only endpoint does not run IQA', 'model instances reused'],
                  'seconds': time.monotonic() - started}
        (ROOT/'work/integration-test.json').write_text(json.dumps(record, indent=2))
        print(json.dumps({'eyes': {'OS': result['state'], 'OD': right_result['state']},
                          'quality': result['quality'], 'grading': result['grading'],
                          'region_counts': {k: v['num_regions'] for k,v in result['lesions']['lesions'].items()},
                          'checks': record['checks'], 'seconds': record['seconds']}, indent=2))
