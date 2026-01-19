from main import ScrabbleBot
from mastodon import Mastodon
import logging

# Configure logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestReply")

def run_test():
    bot = ScrabbleBot()

    logger.info("Setting up bot...")
    if not bot.setup():
        logger.error("Bot setup failed. Check your credentials and configuration.")
        return

    logger.info(f"Fetching latest post from @{bot.bt_account_name}...")
    statuses = bot.mastodon.account_statuses(bot.bt_account_id, limit=1)
    
    if not statuses:
        logger.warning("No posts found for the target account.")
        return

    latest_status = statuses[0]
    logger.info(f"Processing latest status ID: {latest_status['id']}")
    logger.info(f"Content: {latest_status['content']}")

    # Force processing by bypassing the state check
    # We set last_bt_id to 0 so the current status_id > 0
    bot.last_bt_id = 0
    
    bot.process_status(latest_status, is_mention=False)
    logger.info("Test run completed.")

if __name__ == "__main__":
    run_test()
