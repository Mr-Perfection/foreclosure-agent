import time
import os
import logging
import argparse
import csv
from datetime import datetime
from pathlib import Path
from selenium.webdriver.common.by import By

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
    parser.add_argument('--csv-output', help='CSV output file path',
                       default=f'data/sf_recorder_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv')
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
    
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    
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
        scraper.click_element(advanced_search_button_selector)

        # Fill in advanced search form
        from_date = "05/07/2025"
        to_date = "05/12/2025"
        scraper.fill_advanced_search_form(from_date, to_date)
        scraper.navigate_to_search()
        # Extract table data
        logger.info("Extracting table data")
        table_data = scrape_search_results_table(scraper)
        # Save to CSV
        if table_data:
            save_to_csv(table_data, args.csv_output)
            import pdb; pdb.set_trace()
            logger.info(f"Saved {len(table_data)} records to CSV: {args.csv_output}")
        else:
            logger.warning("No data was extracted from the table")
        
        logger.info("Scraping completed successfully")
        
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
    finally:
        if scraper:
            # scraper.close()
            pass


def scrape_search_results_table(scraper: SFRecorderScraper):
    """
    Scrape the search results table data
    
    Args:
        scraper: The SFRecorderScraper instance
        
    Returns:
        List of dictionaries containing the scraped data
    """
    # Wait for the table to be visible
    table_selector = "#SearchResultsGrid"
    scraper.browser.wait.until(
        lambda driver: driver.find_element(By.CSS_SELECTOR, table_selector).is_displayed()
    )
    
    # Get all table rows
    rows = scraper.driver.find_elements(By.CSS_SELECTOR, "#SearchResultsGrid tbody tr")
    logger.info(f"Found {len(rows)} rows in the search results table")
    
    results = []
    for row in rows:
        # Extract data from each cell using the driver to find elements
        # Get each cell's text by column position
        cells = row.find_elements(By.TAG_NAME, "td")
        
        # Ensure we have enough cells
        if len(cells) >= 5:  # At least 5 cells per row in the table
            # First cell is form check.
            # Try direct text extraction
            doc_number = cells[1].text.strip()
            doc_date = cells[2].text.strip()
            filing_code = cells[3].text.strip()
            names = cells[4].text.strip()
            
            results.append({
                "document_number": doc_number,
                "document_date": doc_date,
                "filing_code": filing_code,
                "names": names
            })
        else:
            raise Exception(f"Row has fewer than expected cells: {len(cells)}")
    return results


def save_to_csv(data, csv_path):
    """
    Save the scraped data to CSV
    
    Args:
        data: List of dictionaries containing the scraped data
        csv_path: Path to save the CSV file
    """
    if not data:
        return
    
    # Create directory if it doesn't exist
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    
    # Write to CSV
    with open(csv_path, 'w', newline='') as csvfile:
        fieldnames = ["document_number", "document_date", "filing_code", "names"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for row in data:
            writer.writerow(row)


if __name__ == "__main__":
    main()