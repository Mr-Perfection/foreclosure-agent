import time
import os
import logging
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from dotenv import load_dotenv

from sf_recorder_scraper import SFRecorderScraper

# Configure logging
def setup_logging(log_file: str = "scraper.log", log_level: str = "INFO") -> logging.Logger:
    """
    Configure and set up logging for the application
    
    Args:
        log_file: Path to the log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        
    Returns:
        Logger instance configured for the application
    """
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger("sf_recorder_scraper")

# Create global logger instance with default settings
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
    parser.add_argument('--log-level', help='Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)',
                       default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'])
    
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
        # Update logger level based on command line argument
        logger.setLevel(getattr(logging, args.log_level.upper()))
        logger.info(f"Starting scraper with log level: {args.log_level}")
        
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
        to_date = "05/16/2025"
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
        try:
            WebDriverWait(scraper.driver, 20).until(
                EC.presence_of_element_located((By.ID, "SearchResultsGrid"))
            )
            time.sleep(2) # Allow table content to render fully
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
            next_page_button_clickable = WebDriverWait(scraper.driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, next_page_button_xpath))
            )
            
            # Find an element in the current table to check for staleness after click
            # Using the first row's internalid as a simple reference point if available, or just the table itself.
            try:
                first_row_in_table = scraper.driver.find_element(By.CSS_SELECTOR, "#SearchResultsGrid tbody tr")
                old_element_ref = first_row_in_table
            except NoSuchElementException:
                 logger.warning("Could not find first row for staleness check, using table itself.")
                 old_element_ref = scraper.driver.find_element(By.ID, "SearchResultsGrid")

            next_page_button_clickable.click()
            logger.info(f"Clicked 'Next page' to go to page {page_num + 1}.")

            WebDriverWait(scraper.driver, 20).until(EC.staleness_of(old_element_ref))
            WebDriverWait(scraper.driver, 20).until(
                EC.presence_of_element_located((By.ID, "SearchResultsGrid"))
            )
            # Optional: wait for a specific element inside the table to confirm new data, e.g., the first row.

        except (TimeoutException, NoSuchElementException):
            logger.info("No active 'Next page' button found or timed out. Assuming end of results.")
            break
            
        page_num += 1
        if page_num > 50: # Safety break to prevent infinite loops during development
            logger.warning("Reached maximum page limit (50). Stopping pagination.")
            break
            
    return all_records


def scrape_search_results_table(scraper: SFRecorderScraper) -> list:
    """Scrapes data from current page table, clicks each row for side panel details."""
    page_records = []
    
    try:
        # This function assumes the table #SearchResultsGrid is already loaded and visible
        rows = scraper.driver.find_elements(By.CSS_SELECTOR, "#SearchResultsGrid tbody tr")
        logger.info(f"Found {len(rows)} rows in the current page's search results table")
        if not rows: return []

        for i, row_element in enumerate(rows):
            record = {}
            try:
                cells = row_element.find_elements(By.TAG_NAME, "td")
                if len(cells) < 5:
                    logger.warning(f"Row {i+1} has only {len(cells)} cells. Expected at least 5. Skipping row.")
                    continue

                # 1. Scrape basic data from the main table row
                record['document_number'] = cells[1].text.strip()
                record['document_date'] = cells[2].text.strip()
                record['filing_code_name'] = cells[3].text.strip()
                record['names_table'] = cells[4].text.strip()      # Names summary from main table
                
                logger.info(f"Processing row {i+1}/{len(rows)}: Doc# {record['document_number']}")

                # 2. Click the row (e.g., the document number cell) to open side panel
                # Ensure the cell is clickable and visible
                doc_num_cell_to_click = cells[1]
                # WebDriverWait(scraper.driver, 10).until(EC.element_to_be_clickable(doc_num_cell_to_click))
                doc_num_cell_to_click.click()
                # Explicitly click the "All Info" tab and wait for it to be active
                all_info_tab_xpath = "//li[@aria-controls='hor_1_tab_item-5'][normalize-space()='All Info']"
                all_info_tab_element = WebDriverWait(scraper.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, all_info_tab_xpath))
                )
                all_info_tab_element.click()
                logger.debug(f"Clicked 'All Info' tab for Doc# {record['document_number']}.")
                # 3. Wait for side panel to load and show details for the correct document
                panel_doc_num_xpath = "//div[@class='names_height']//div[@class='form-group'][.//label[normalize-space()='Document Number']]//div[@class='col-sm-6']/div[@contenteditable='false']"
                WebDriverWait(scraper.driver, 20).until(
                    lambda driver: driver.execute_script(
                        "return arguments[0].textContent", 
                        driver.find_element(By.XPATH, panel_doc_num_xpath)
                    ).strip() == record['document_number']
                )
                logger.debug(f"Side panel content confirmed for Doc# {record['document_number']}")
                
                # 4. Extract detailed information from panel
                panel_content_area_xpath = "//div[@class='names_height']"
                panel_element = scraper.driver.find_element(By.XPATH, panel_content_area_xpath)

                try:
                    pages_xpath = ".//div[@class='form-group'][.//label[normalize-space()='Pages']]//div[@class='col-sm-6']/div[@contenteditable='false']"
                    record['pages'] = panel_element.find_element(By.XPATH, pages_xpath).get_attribute('textContent').strip()
                    logger.debug(f"Found pages: {record['pages']}")
                except NoSuchElementException:
                    record['pages'] = None
                    logger.debug(f"Panel - Pages not found for Doc# {record['document_number']}")
                try:
                    # More absolute XPath for filing code, starting from a known stable ancestor or document root
                    # This also assumes panel_element (//div[@class='names_height']) is a reliable ancestor.
                    filing_code_xpath = "//div[@class='names_height']//div[@class='form-group clearfix ng-scope' and .//label[normalize-space()='Filing Code']]//div[@contenteditable='false' and @class='ng-binding']"
                    record['filing_code'] = scraper.driver.find_element(By.XPATH, filing_code_xpath).get_attribute('textContent').strip() # Search from scraper.driver
                    logger.debug(f"Found filing code: {record['filing_code']}")
                except NoSuchElementException:
                    record['filing_code'] = None
                    logger.debug(f"Panel - Filing Code not found for Doc# {record['document_number']}")
                
                record['titles_descriptions'] = []
                try:
                    titles_table_xpath = ".//table[.//th/span[normalize-space(.)='Title(s)']]"
                    titles_table = panel_element.find_element(By.XPATH, titles_table_xpath)
                    titles_rows = titles_table.find_elements(By.XPATH, "./tbody/tr")
                    for tr_title in titles_rows:
                        title_element = tr_title.find_element(By.XPATH, "./td[1]")
                        description_element = tr_title.find_element(By.XPATH, "./td[2]")
                        record['titles_descriptions'].append({
                            "title": title_element.get_attribute('textContent').strip(),
                            "description": description_element.get_attribute('textContent').strip()
                        })
                    logger.debug(f"Found {len(record['titles_descriptions'])} titles/descriptions")
                except NoSuchElementException:
                    logger.debug(f"Panel - Titles/Descriptions table not found for Doc# {record['document_number']}")

                record['party_details'] = [] # Granters and Grantees
                try:
                    names_grid_table_xpath = ".//names-grid//table[.//th[normalize-space(.)='Name Type']]"
                    names_table = panel_element.find_element(By.XPATH, names_grid_table_xpath)
                    names_rows = names_table.find_elements(By.XPATH, "./tbody/tr")
                    for tr_name in names_rows:
                        name_type_elements = tr_name.find_elements(By.XPATH, "./td[1]/span") # Check for span first
                        name_type_element = name_type_elements[0] if name_type_elements else tr_name.find_element(By.XPATH, "./td[1]")
                        name_element = tr_name.find_element(By.XPATH, "./td[2]")
                        record['party_details'].append({
                            "type": name_type_element.get_attribute('textContent').strip(),
                            "name": name_element.get_attribute('textContent').strip()
                        })
                    logger.debug(f"Found {len(record['party_details'])} party details")
                except NoSuchElementException:
                    logger.debug(f"Panel - Names grid (granters/grantees) not found for Doc# {record['document_number']}")
                
                page_records.append(record)

            except TimeoutException as te:
                logger.error(f"Timeout interacting with side panel for Doc# {record.get('document_number', 'N/A')} on row {i+1}: {te}")
                if record.get('document_number'): # If we have basic info, save it
                    page_records.append(record) # Add partially filled record
            except Exception as e_row_panel:
                logger.error(f"Error processing row {i+1} (Doc# {record.get('document_number', 'N/A')}) or its side panel: {str(e_row_panel)}", exc_info=False)
                if record.get('document_number'): # If we have basic info, save its
                    page_records.append(record) # Add partially filled record
                    
    except Exception as e_table:
        logger.error(f"Error finding or processing table rows on current page: {str(e_table)}", exc_info=True)

    return page_records


def save_to_csv(data: list, csv_path: str):
    """Save the scraped data to CSV, serializing complex fields to JSON."""
    if not data:
        logger.warning("No data provided to save_to_csv.")
        return
    
    # Ensure directory exists
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    
    # Define fieldnames including new ones for panel data
    fieldnames = [
        "document_number", "document_date", "filing_code_name", "names_table",
        "pages", "filing_code", "titles_descriptions", "party_details"
    ]
    
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore') # extrasaction='ignore' is safer
        writer.writeheader()
        for record_row in data:
            # Serialize list/dict fields to JSON strings
            if 'titles_descriptions' in record_row and isinstance(record_row['titles_descriptions'], list):
                record_row['titles_descriptions'] = json.dumps(record_row['titles_descriptions'])
            if 'party_details' in record_row and isinstance(record_row['party_details'], list):
                record_row['party_details'] = json.dumps(record_row['party_details'])
            writer.writerow(record_row)
            
    logger.info(f"Data successfully saved to {csv_path}")


if __name__ == "__main__":
    main()