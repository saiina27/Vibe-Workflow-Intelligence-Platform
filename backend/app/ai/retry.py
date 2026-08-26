
import logging

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
    retry_if_exception,
)


logger = logging.getLogger(__name__)


def _should_retry(exception: BaseException) -> bool:
    """
    Retry only transient provider errors.

    Do NOT retry:
        - 413 request too large / TPM request-size rejection
        - 429 rate/quota limit
        - 400 invalid request
        - 401 authentication
        - 403 permission
        - 404 not found
    """

    status_code = getattr(
        exception,
        "status_code",
        None,
    )

    non_retryable_status_codes = {
        400,
        401,
        403,
        404,
        413,
        422,
    }

    if status_code in non_retryable_status_codes:
        return False

    return True


ai_retry = retry(
    retry=retry_if_exception(
        _should_retry
    ),
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
    reraise=True,
)

