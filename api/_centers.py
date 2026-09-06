"""Verified center coordinates; never infer jurisdiction from proximity."""
import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / 'data' / 'welfare-centers.json'

def load_centers():
    return json.loads(DATA.read_text(encoding='utf-8'))['centers']

def center_for_destination(value):
    return next((c for c in load_centers() if value in (c['area'], c['name'], c['address'])), None)

def administrative_center(area):
    if not re.search(r'화성(?:특례)?시', area):
        return None
    tokens = area.split()
    return next((c for c in load_centers() if c['area'] in tokens), None)
