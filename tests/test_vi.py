"""The real Verifiable Intent chain for each scenario.

Needs a clone of agent-intent/verifiable-intent (see vi_runner._find_vi_sdk);
without it the tests are skipped, not failed.
"""

import pytest

from asasked.scenarios import SCENARIOS

vi_runner = pytest.importorskip("asasked.vi_runner", exc_type=SystemExit)


@pytest.mark.parametrize("scn", SCENARIOS, ids=lambda s: s.id)
def test_vi_passes_everything_but_the_control(scn):
    result = vi_runner.run_vi(scn)
    assert result["chain_valid"]
    if scn.expect == "vi_rejects":
        assert not result["constraints_ok"]
        assert result["violations"]
    else:
        assert result["constraints_ok"]
        assert not result["violations"]
