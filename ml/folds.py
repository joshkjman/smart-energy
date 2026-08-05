"""Walk-forward fold boundaries for honest time-series validation.

Expanding window: every fold trains on all history up to train_end, then
tests on the month that follows. A purge of MAX_LEAD days separates them,
because a model fitted at train_end is used to predict targets up to
MAX_LEAD days beyond the moment it is standing at.
"""
import datetime as dt
from dateutil.relativedelta import relativedelta
from typing import Iterator, NamedTuple

HOLDOUT_START = dt.date(2025, 7, 1)
HOLDOUT_END = dt.date(2026, 7, 11)
MAX_LEAD = 7


class Fold(NamedTuple):
    train_end: dt.date    # exclusive
    test_start: dt.date   # inclusive
    test_end: dt.date     # exclusive


def generate_folds(
    holdout_start: dt.date = HOLDOUT_START,
    holdout_end: dt.date = HOLDOUT_END,
    max_lead: int = MAX_LEAD,
) -> Iterator[Fold]:
    """Yield one Fold per test month across the holdout window.

    Guarantees train_end <= test_start - max_lead for every fold.
    """
    # TODO: walk test_start from holdout_start in monthly steps
    # TODO: test_end = one month later, clipped so it never exceeds holdout_end
    # TODO: train_end = test_start - max_lead days
    # TODO: skip / stop on any final stub month too short to be worth scoring
    # TODO: assert the purge invariant before yielding
    delta = relativedelta(months=1)

    test_start = holdout_start
    train_end = test_start - dt.timedelta(days=max_lead)

    while test_end <= holdout_end - delta:
        test_end = test_start + delta

        yield Fold(train_end=train_end, test_start=test_start, test_end=test_end)
    
    

    
