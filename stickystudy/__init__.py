import logging
from pathlib import Path


logging.basicConfig(level = logging.INFO, format = '%(message)s')
LOGGER = logging.getLogger('stickystudy')

PKG_DIR = Path(__file__).parent
DATA_DIR = PKG_DIR / 'data'