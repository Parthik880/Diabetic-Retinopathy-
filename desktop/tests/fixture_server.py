"""UI test server: real API/history/PDF export, explicitly synthetic ML output."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app import main
import uvicorn


class FixtureRegistry:
    def health(self):
        return {'ready': True, 'models': [], 'test_fixture': True}


def fixture_analysis(*, original_path, run_id, eye, **kwargs):
    destination = original_path.parent
    result = {
        'run_id': run_id, 'eye': eye, 'state': 'COMPLETE',
        'state_history': [{'state': 'COMPLETE', 'at': '2026-09-13T00:00:00Z'}],
        'invocation_counts': {'iqa': 0, 'nafnet': 0, 'grading': 0, 'lesions': 0},
        'quality': {'quality': 'Good', 'confidence': 0.9, 'probabilities': {'Good': 0.9}},
        'grading': {'predicted_grade': 0, 'confidence': 0.9, 'probabilities': [0.9, 0.025, 0.025, 0.025, 0.025]},
        'lesions': {'lesions': {}, 'combined_overlay_path': None},
        'image_url': f'/artifacts/{run_id}/input.png', 'image_width': 512, 'image_height': 512,
        'device': 'cpu', 'device_name': 'TEST FIXTURE — no model execution',
        'disclaimer': 'Synthetic output for UI testing only.',
        'warnings': ['Synthetic output for UI testing only.'],
    }
    (destination / 'response.json').write_text(json.dumps(result), encoding='utf-8')
    return result


main.ModelRegistry = FixtureRegistry
# The job manager still runs the real API analysis job lifecycle.
main.run_analysis_pipeline = fixture_analysis
uvicorn.run(main.app, host='127.0.0.1', port=int(sys.argv[1]), log_level='warning')
