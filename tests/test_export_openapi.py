import json
import subprocess
import sys


def test_export_openapi(tmp_path):
    out = tmp_path / "openapi.json"
    subprocess.run([sys.executable, "scripts/export_openapi.py", str(out)], check=True)
    doc = json.loads(out.read_text())
    for path in ("/v2/search", "/v2/parcels/{parcel_id}", "/v2/sales", "/v2/market/summary",
                 "/v2/meta", "/v2/neighborhoods", "/v2/owners/top", "/v2/distress/stale-parcels"):
        assert path in doc["paths"], path
