import logging

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)


logger = logging.getLogger(__name__)


ai_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(
        multiplier=1,
        min=1,
        max=5,
    ),
    before_sleep=before_sleep_log(
        logger,
        logging.WARNING,
    ),
)