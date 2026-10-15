"""Run every workflow demo against the sample data. Outputs land in ./output."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "workflows"))

import call_router  # noqa: E402
import contract_timeline  # noqa: E402
import delinquency_notices  # noqa: E402
import lead_response  # noqa: E402
import owner_statements  # noqa: E402
import work_order_triage  # noqa: E402

for module in (work_order_triage, delinquency_notices, owner_statements, call_router, contract_timeline, lead_response):
    module.main()

print("\nDone. Open the output/ folder to see every generated file.")
