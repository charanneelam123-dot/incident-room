"""Generate a static, explicitly labeled replay from the actual Python workflow."""
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from incident_room.agent import Investigator
from incident_room.store import Store
from incident_room.tools import scenarios

out = ROOT/'dist'
(out/'demo').mkdir(parents=True,exist_ok=True)
shutil.copyfile(ROOT/'incident_room/web/index.html',out/'index.html')
with tempfile.TemporaryDirectory() as folder:
    store = Store(Path(folder)/'demo.sqlite')
    for scenario in scenarios():
        run = Investigator(store).investigate(scenario['id'])
        if run['status'] != 'complete':
            raise RuntimeError(run['errors'])
        # Stable demo IDs and deterministic sequence labels; the raw local API retains timestamps.
        run['id'] = 'demo-'+scenario['id']
        for event in run['events']:
            event['time'] = f'step-{event["index"]}'
        run['elapsed_ms'] = None
        (out/'demo'/f'{scenario["id"]}.json').write_text(json.dumps(run,indent=2),encoding='utf-8')
(out/'demo/scenarios.json').write_text(json.dumps([{k:s[k] for k in ('id','title','alert','service')} for s in scenarios()],indent=2),encoding='utf-8')
print('Built static demo from three completed Python investigations.')
