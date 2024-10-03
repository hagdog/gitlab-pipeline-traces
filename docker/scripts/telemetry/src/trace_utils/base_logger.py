import logging
import os
import sys

# Root logger
log = logging.getLogger(__name__)


def debug_per_environment():
    """Determine if debugging is enabled via the environment"""
    debug_var = os.environ.get("CI_TRACE_EXPORT_DEBUG", 0)

    try:
        return int(debug_var) > 0
    except (TypeError, ValueError):
        if debug_var:
            if debug_var.lower() == "true":
                return True
            else:
                return False
        else:
            return False


def get_logger(name, level=logging.INFO):
    """Provide a logger for a module."""
    global log
    format_str = "%(asctime)s [%(levelname)s] %(name)s #%(lineno)s:  %(message)s"
    if debug_per_environment():
        level = logging.DEBUG

    # The first caller of this function initializes
    # logging for this execution space.
    if not len(log.handlers):
        logging.basicConfig(level=level, format=format_str)
        formatter = logging.Formatter()
        logging_stdout = logging.StreamHandler(sys.stdout)
        logging_stdout.setFormatter(formatter)
        logging_stdout.setLevel(level)

        log.addHandler(logging_stdout)
        log.setLevel(level)

    # Modules pulled in as dependencies known to be noisy at logging.INFO.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)

    module_logger = logging.getLogger(name)
    module_logger.setLevel(level)

    return module_logger
