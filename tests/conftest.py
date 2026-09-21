import pandas as pd
import pytest

from tests.appendix import EFFECT_ROWS, THRESHOLD_ROWS


@pytest.fixture
def effects():
    return pd.DataFrame(EFFECT_ROWS, columns=["stratum", "stratum_value", "resource_1", "resource_2"])


@pytest.fixture
def thresholds():
    return pd.DataFrame(THRESHOLD_ROWS, columns=["resource", "resource_level", "threshold"])
