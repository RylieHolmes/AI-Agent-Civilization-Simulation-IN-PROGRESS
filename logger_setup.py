import logging
import sys

def setup_logger():
    """Configures the root logger to print to the console."""
    logger = logging.getLogger()
    # Set the minimum level of messages to show to DEBUG to get more detailed output
    logger.setLevel(logging.DEBUG) 

    # If handlers are already present, don't add more
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        
        # Create a formatter with a timestamp
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)