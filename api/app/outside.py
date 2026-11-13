"""Calls that leave the app (a bank, storage, another service): which errors they raise, and one
way to try again.

The standard asks for specific exceptions and for retries with backoff on outside calls. The
errors a network call can raise are listed here once, so a caller catches those and nothing
else; anything outside the list is a bug and should surface as one.
"""

import logging
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

# Assumptions: three tries, waiting 1 s then 2 s. Enough for a blip, short enough for a page.
ATTEMPTS = 3
FIRST_WAIT_SECONDS = 1.0

# What a network call raises: connection, DNS, TLS and timeouts are OSError (urllib's URLError
# and HTTPError among them); a body that isn't what was promised is ValueError.
NETWORK_ERRORS: tuple[type[Exception], ...] = (OSError, ValueError)


def storage_errors() -> tuple[type[Exception], ...]:
    """What reading or writing stored files raises: the local folder's errors, and Azure's when
    its SDK is installed (it is only imported where Blob storage is used)."""
    try:
        from azure.core.exceptions import AzureError
    except ImportError:  # local development without the Azure SDK
        return (*NETWORK_ERRORS, KeyError)
    return (*NETWORK_ERRORS, KeyError, AzureError)


def retry[T](
    call: Callable[[], T],
    *,
    on: tuple[type[Exception], ...] = NETWORK_ERRORS,
    attempts: int = ATTEMPTS,
    first_wait: float = FIRST_WAIT_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `call`; on one of the errors in `on`, wait and try again, doubling the wait each
    time. The last error is raised as it is, for the caller to turn into its own."""
    wait = first_wait
    for attempt in range(1, attempts + 1):
        try:
            return call()
        except on as exc:
            if attempt == attempts:
                raise
            log.warning(
                "Outside call failed (%s), try %s of %s", type(exc).__name__, attempt, attempts
            )
            sleep(wait)
            wait *= 2
    raise AssertionError("unreachable: the loop returns or raises")
