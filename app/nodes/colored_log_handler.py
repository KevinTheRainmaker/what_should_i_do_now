import logging

RESET = '\033[0m'

MAGENTA = '\033[35m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
RED = '\033[31m'

class ColoredLevelFormatter(logging.Formatter):
    BASE_FORMAT_DEBUG = '%(levelname)s %(message)s (%(filename)s:%(lineno)d)'
    BASE_FORMAT_INFO = '%(levelname)s %(message)s'
    BASE_FORMAT_WARNING = '%(levelname)s %(message)s'
    BASE_FORMAT_ERROR = '%(levelname)s %(message)s (%(filename)s:%(lineno)d)'
    BASE_FORMAT_CRITICAL = '%(levelname)s %(message)s (%(filename)s:%(lineno)d)'

    LEVEL_COLORS = {
        logging.DEBUG: MAGENTA,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: RED,
    }

    FORMATS = {
        logging.DEBUG: BASE_FORMAT_DEBUG,
        logging.INFO: BASE_FORMAT_INFO,
        logging.WARNING: BASE_FORMAT_WARNING,
        logging.ERROR: BASE_FORMAT_ERROR,
        logging.CRITICAL: BASE_FORMAT_CRITICAL,
    }

    def format(self, record):
        orig_levelname = record.levelname
        color = self.LEVEL_COLORS.get(record.levelno, '')
        record.levelname = f"{color}{orig_levelname}:{RESET}"
        fmt = self.FORMATS.get(record.levelno, self._style._fmt)
        formatter = logging.Formatter(fmt)
        result = formatter.format(record)
        record.levelname = orig_levelname

        return result

class ColoredLogHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__()
        self.setLevel(logging.DEBUG)
        self.setFormatter(ColoredLevelFormatter())