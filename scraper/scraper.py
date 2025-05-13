import os
import logging
import argparse
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from sf_recorder_scraper import SFRecorderScraper

# Configure logging
def setup_logging(log_file: str = "scraper.log") -> logging.Logger:
    """
    Configure and set up logging for the application
    
    Args:
        log_file: Path to the log file
        
    Returns:
        Logger instance configured for the application
    """
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("sf_recorder_scraper")

logger = setup_logging()

def parse_arguments():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='SF Recorder Office Scraper')
    parser.add_argument('--email', help='Login email')
    parser.add_argument('--password', help='Login password')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--output', help='Output file path', 
                       default=f'data/sf_recorder_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    parser.add_argument('--temp-dir', help='Directory for temporary files', default='tmp')
    
    return parser.parse_args()


def main():
    """Main function to run the scraper."""
    args = parse_arguments()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Use command line args or environment variables
    email = args.email or os.getenv('SF_RECORDER_EMAIL')
    password = args.password or os.getenv('SF_RECORDER_PASSWORD')
    
    if not email or not password:
        logger.error("Email and password are required. Provide them via command line arguments or .env file")
        return
    
    # Create directories
    download_dir = Path("downloads")
    download_dir.mkdir(exist_ok=True)
    
    temp_dir = Path(args.temp_dir)
    temp_dir.mkdir(exist_ok=True)
    
    scraper = None
    try:
        # Initialize and run scraper
        scraper = SFRecorderScraper(
            headless=args.headless, 
            download_dir=str(download_dir),
            temp_dir=str(temp_dir)
        )
        scraper.navigate_to_site()
        scraper.login(email, password)

        # Navigate to advanced search page
        advanced_search_button_selector = "input[type='button'][value='Advanced Search']"
        scraper.navigate(advanced_search_button_selector)

        # Fill in advanced search form
        from_date = "05/07/2025"
        to_date = "05/12/2025"
        scraper.fill_advanced_search_form(from_date, to_date)
        scraper.navigate_to_search()
        # data = scraper.scrape_data()
        
        # if data and args.output:
        #     scraper.save_data(data, args.output)
        
        logger.info("Scraping completed successfully")
        
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
    finally:
        if scraper:
            # scraper.close()
            pass


if __name__ == "__main__":
    main()