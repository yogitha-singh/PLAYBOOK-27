from pathlib import Path
from ..core.security import ApiError

class ModelStore:
    def __init__(self, d): self.dir = Path(d); self.models = {}

def simulate(*a, **kw):
    raise ApiError(503, "scenario_disabled", "Scenario simulator was removed per requirements.")

PRESETS = []

def explain_player(rec, reliability_params, role):
    pri = rec.get("PRI", 50)
    return {"formula": "PRI = 50 + 10*mean(z_level, z_delta, z_consistency)", "components": [], "check_sum": pri, "PRI": pri}
