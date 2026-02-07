import argparse
import asyncio
import logging
import sys
import time

from linksync.config import load_config
from linksync.state import open_database
from linksync.sync import run_sync


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync bookmarks between Linkora and Readeck")
    parser.add_argument("--config", type=str, default=None, help="Path to config file")
    parser.add_argument("--interval", type=int, default=None, help="Sync interval in seconds (loop mode)")
    arguments = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    
    try:
        configuration = load_config(arguments.config)
    except Exception as error:
        logging.error(f"Failed to load config: {error}")
        sys.exit(1)
    
    connection = None
    try:
        connection = open_database(configuration.sync.state_db)
        
        if arguments.interval is not None:
            # Loop mode: sync repeatedly with interval.
            try:
                while True:
                    try:
                        asyncio.run(run_sync(configuration, connection))
                    except Exception as error:
                        logging.error(f"Sync failed: {error}")
                    
                    time.sleep(arguments.interval)
            except KeyboardInterrupt:
                logging.info("Shutting down")
                sys.exit(0)
        else:
            # One-shot mode: sync once and exit.
            asyncio.run(run_sync(configuration, connection))
    except Exception as error:
        logging.error(f"Sync failed: {error}")
        sys.exit(1)
    finally:
        if connection is not None:
            connection.close()
    
    sys.exit(0)
