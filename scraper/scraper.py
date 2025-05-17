import time
import os
import logging
import argparse
import csv
from datetime import datetime
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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
        to_date = "05/17/2025"
        scraper.fill_advanced_search_form(from_date, to_date)
        scraper.navigate_to_search()

        scraper.click_element("//a[@id='ddlDocsPerPage']",By.XPATH)
        logger.info("Clicked on dropdown for results per page.")
        
        scraper.click_element("//a[@id='ddlDocsPerPage']/ul/li[5]",By.XPATH)
        logger.info("Selected 100 results per page.")
        
        WebDriverWait(scraper.driver, 20).until(
            lambda driver: driver.find_element(By.XPATH, "//input[@id='hdnDocsPerPage']").get_attribute("value").strip() == "100"
        )
        logger.info("Confirmed 100 results per page is set.")
        
        all_table_data = scrape_all_pages(scraper)
        
        if all_table_data:
            save_to_csv(all_table_data, args.csv_output)
            logger.info(f"Saved {len(all_table_data)} records from all pages to CSV: {args.csv_output}")
        else:
            logger.warning("No data was extracted from any page.")
        
        logger.info("Scraping completed successfully.")
        
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}", exc_info=True)
    finally:
        if scraper:
            scraper.close()


def scrape_all_pages(scraper: SFRecorderScraper) -> list:
    """
    Scrapes table data from all pages.
    
    Args:
        scraper: The SFRecorderScraper instance.
        
    Returns:
        A list of all records scraped from all pages.
    """
    all_records = []
    page_num = 1
    
    while True:
        logger.info(f"Scraping page {page_num}...")
        
        # Wait for the table to be ready on the current page
        try:
            WebDriverWait(scraper.driver, 20).until(
                EC.presence_of_element_located((By.ID, "SearchResultsGrid"))
            )
            # Add a small delay to ensure content is fully rendered, if necessary
            time.sleep(2) # Adjust as needed, or use more specific wait conditions
        except TimeoutException:
            logger.error(f"Timeout waiting for search results table on page {page_num}.")
            break

        current_page_records = scrape_search_results_table(scraper)
        if current_page_records:
            all_records.extend(current_page_records)
            logger.info(f"Scraped {len(current_page_records)} records from page {page_num}.")
        else:
            logger.info(f"No records found on page {page_num}.")

        # Try to find the active "Next page" button
        try:
            next_page_button_xpath = "//a[@title='Next page' and not(contains(@class, 'inactive')) and @ng-click]"
            next_page_button = WebDriverWait(scraper.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, next_page_button_xpath))
            )
            # Store a reference to an element on the current page to check for staleness later
            # This helps ensure the page has actually navigated
            old_table_id = scraper.driver.find_element(By.ID, "SearchResultsGrid").id
            
            next_page_button.click()
            logger.info(f"Clicked 'Next page' to go to page {page_num + 1}.")

            # Wait for the page to navigate and the table to refresh
            WebDriverWait(scraper.driver, 20).until(
                EC.staleness_of(scraper.driver.find_element(By.ID, old_table_id))
            )
            WebDriverWait(scraper.driver, 20).until(
                EC.presence_of_element_located((By.ID, "SearchResultsGrid"))
            )
            # Optional: wait for a specific element inside the table to confirm new data, e.g., the first row.

        except (TimeoutException, NoSuchElementException):
            logger.info("No active 'Next page' button found or timed out. Assuming end of results.")
            break # Exit loop if no active next button or it's not clickable
            
        page_num += 1
        if page_num > 50: # Safety break to prevent infinite loops during development
            logger.warning("Reached maximum page limit (50). Stopping pagination.")
            break
            
    return all_records


def scrape_search_results_table(scraper: SFRecorderScraper) -> list:
    """
    Scrape the search results table data from the CURRENTLY DISPLAYED page.
    
    Args:
        scraper: The SFRecorderScraper instance
        
    Returns:
        List of dictionaries containing the scraped data from the current page.
    """
    results = []
    try:
        # This function assumes the table #SearchResultsGrid is already loaded and visible
        rows = scraper.driver.find_elements(By.CSS_SELECTOR, "#SearchResultsGrid tbody tr")
        logger.info(f"Found {len(rows)} rows in the current page's search results table")
        
        if not rows:
            logger.info("No rows found in table on this page.")
            return results

        for i, row in enumerate(rows):
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                # The HTML structure provided previously has 5 visible data cells,
                # plus potentially hidden ones. The ng-show column is usually first if visible.
                # Based on Untitled-1, the visible data columns are:
                # 1. Document Number
                # 2. Document Date
                # 3. SearchFilingCode
                # 4. Names
                # 5. Purchase (icon)
                # If the first ng-show column for report selection is hidden, data starts at cells[0]
                # If it's visible, data starts at cells[1].
                # Let's check number of cells to be safer.

                # Assuming the checkbox column (ng-show="IsReportViewEnable && DisplayReportView") is hidden as per example
                # Then: doc_number=cells[0], doc_date=cells[1], filing_code=cells[2], names=cells[3]
                
                # Corrected indexing based on the provided HTML where data cells are 0, 1, 2, 3
                # after the initial hidden checkbox cell if it exists.
                # If that hidden cell is counted by find_elements, then indices are 1,2,3,4.
                # The example HTML shows 6 th elements, but the first two `ng-show` are hidden.
                # `idcolumn` (doc num), `datecolumn`, `min_names` (filing code), `min_names name_wid_th` (names)
                # This implies 4 main data columns visible in the example.
                
                # The user's previous successful scrape used cells[1] for doc_number.
                # This suggests there's always a cell at index 0 (maybe the hidden checkbox placeholder)
                
                expected_min_cells = 5 # Based on user's previous code: checkbox, doc_number, doc_date, filing_code, names
                                       # OR doc_number, doc_date, filing_code, names, purchase_icon
                
                if len(cells) >= 4: # Check for at least 4 data cells
                    # From Untitled-1, the first visible td is doc number.
                    # If the first column `ng-show` is truly hidden and not picked by `find_elements`,
                    # then cell indices would be 0, 1, 2, 3 for the four data points.
                    # User code was cells[1], cells[2], cells[3], cells[4] -> this implies there's a cell[0]
                    # Let's try to be more robust by looking for specific content or classes if simple indexing fails
                    
                    # Sticking to user's last working indexing: cells[1] to cells[4] for data
                    # This assumes cells[0] is the checkbox column whether hidden or not.
                    if len(cells) < 5: # Need at least 5 cells for indices 1-4
                        logger.warning(f"Row {i+1} has only {len(cells)} cells. Expected at least 5. Skipping row.")
                        # You might want to print cell texts here for debugging:
                        # for k, cell_debug in enumerate(cells):
                        #     logger.debug(f"Cell {k} text: '{cell_debug.text.strip()[:50]}'")
                        continue

                    doc_number_text = cells[1].text.strip()
                    doc_date_text = cells[2].text.strip()
                    filing_code_text = cells[3].text.strip() # This corresponds to "SearchFilingCode"
                    names_text = cells[4].text.strip()      # This corresponds to "Names"

                    # Sometimes, the text might be inside a div or another element within the td
                    # If direct .text is empty, try finding a div.
                    if not doc_number_text and cells[1].find_elements(By.TAG_NAME, "div"):
                        doc_number_text = cells[1].find_element(By.TAG_NAME, "div").text.strip()
                    if not doc_date_text and cells[2].find_elements(By.TAG_NAME, "div"):
                        doc_date_text = cells[2].find_element(By.TAG_NAME, "div").text.strip()
                    if not filing_code_text and cells[3].find_elements(By.TAG_NAME, "div"):
                        filing_code_text = cells[3].find_element(By.TAG_NAME, "div").text.strip()
                    if not names_text and cells[4].find_elements(By.TAG_NAME, "div"):
                        names_text = cells[4].find_element(By.TAG_NAME, "div").text.strip()
                    
                    results.append({
                        "document_number": doc_number_text,
                        "document_date": doc_date_text,
                        "filing_code": filing_code_text,
                        "names": names_text
                    })
                else:
                    logger.warning(f"Row {i+1} has fewer than 4 data cells ({len(cells)} found). Skipping row.")
                    # Log cell content for debugging
                    # for k_debug, cell_debug in enumerate(cells):
                    #    logger.debug(f"Row {i+1}, Cell {k_debug} HTML: {cell_debug.get_attribute('outerHTML')[:100]}")


            except Exception as e_row:
                logger.error(f"Error processing row {i+1} on current page: {str(e_row)}", exc_info=False) # Set exc_info=True for more details
                # Log cell content for debugging
                # try:
                #    for k_debug, cell_debug in enumerate(cells):
                #        logger.debug(f"Failed Row {i+1}, Cell {k_debug} HTML: {cell_debug.get_attribute('outerHTML')[:100]}")
                # except NameError: # cells might not be defined if error was before
                #    pass
                continue # Skip to next row
                
    except Exception as e_table:
        logger.error(f"Error finding or processing table rows on current page: {str(e_table)}", exc_info=True)

    return results


def save_to_csv(data: list, csv_path: str):
    """
    Save the scraped data to CSV
    
    Args:
        data: List of dictionaries containing the scraped data
        csv_path: Path to save the CSV file
    """
    if not data:
        logger.warning("No data provided to save_to_csv.")
        return
    
    # Ensure directory exists
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ["document_number", "document_date", "filing_code", "names"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for row in data:
            writer.writerow(row)
    logger.info(f"Data successfully saved to {csv_path}")


if __name__ == "__main__":
    main()