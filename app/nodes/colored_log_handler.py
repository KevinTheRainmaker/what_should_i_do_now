import logging
# Reset
RESET = '\033[0m'

# Regular Colors
BLACK = '\033[30m'
RED = '\033[31m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
BLUE = '\033[34m'
MAGENTA = '\033[35m'
CYAN = '\033[36m'
WHITE = '\033[37m'

# Bold
BOLD_BLACK = '\033[1;30m'
BOLD_RED = '\033[1;31m'
BOLD_GREEN = '\033[1;32m'
BOLD_YELLOW = '\033[1;33m'
BOLD_BLUE = '\033[1;34m'
BOLD_MAGENTA = '\033[1;35m'
BOLD_CYAN = '\033[1;36m'
BOLD_WHITE = '\033[1;37m'

# Underline
UNDERLINE_BLACK = '\033[4;30m'
UNDERLINE_RED = '\033[4;31m'
UNDERLINE_GREEN = '\033[4;32m'
UNDERLINE_YELLOW = '\033[4;33m'
UNDERLINE_BLUE = '\033[4;34m'
UNDERLINE_MAGENTA = '\033[4;35m'
UNDERLINE_CYAN = '\033[4;36m'
UNDERLINE_WHITE = '\033[4;37m'

# High Intensity
INTENSITY_BLACK = '\033[0;90m'
INTENSITY_RED = '\033[0;91m'
INTENSITY_GREEN = '\033[0;92m'
INTENSITY_YELLOW = '\033[0;93m'
INTENSITY_BLUE = '\033[0;94m'
INTENSITY_MAGENTA = '\033[0;95m'
INTENSITY_CYAN = '\033[0;96m'
INTENSITY_WHITE = '\033[0;97m'

class ColoredLogHandler(logging.StreamHandler):
    def __init__(self):
        super().__init__()
        self.setLevel(logging.DEBUG)
        self.setFormatter(self.__LogFormatter())

    class __LogFormatter(logging.Formatter):
        __FORMAT_DEBUG = '[%(asctime)s] [%(levelname)s] %(message)s (%(filename)s:%(lineno)d)'
        __FORMAT_INFO = '[%(asctime)s] [%(levelname)s] %(message)s'
        __FORMAT_WARNING = '[%(asctime)s] [%(levelname)s] %(message)s'
        __FORMAT_ERROR = '[%(asctime)s] [%(levelname)s] %(message)s'
        __FORMAT_CRITICAL = '[%(asctime)s] [%(levelname)s] %(message)s (%(filename)s:%(lineno)d)'

        FORMATS = {
            logging.DEBUG: MAGENTA + __FORMAT_DEBUG + RESET,
            logging.INFO: GREEN + __FORMAT_INFO + RESET,
            logging.WARNING: YELLOW + __FORMAT_WARNING + RESET,
            logging.ERROR: RED + __FORMAT_ERROR + RESET,
            logging.CRITICAL: RED + __FORMAT_CRITICAL + RESET
        }

        def format(self, record):
            log_fmt = self.FORMATS.get(record.levelno)
            formatter = logging.Formatter(log_fmt)
            return formatter.format(record)