"""
Basic structured-ish logging setup.

Every security-relevant or officer-decision event is logged through the
`sentry_id.audit` logger so it can be shipped to a SIEM in a real
deployment. In the prototype it just writes to stdout.
"""
import logging
import sys


def configure_logging() -> None:
    root = logging.getLogger()
    if root.handlers:
        # Already configured (e.g. reload) — avoid duplicate handlers.
        return

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
    root.setLevel(logging.INFO)


audit_logger = logging.getLogger("sentry_id.audit")
