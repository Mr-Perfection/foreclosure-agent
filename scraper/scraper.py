import os
import time
import json
import logging
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from dotenv import load_dotenv
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Import our refactored classes
from captcha_solver import CaptchaSolver
from webdriver_wrapper import WebDriverWrapper

# Configure logging
def setup_logging(log_file="scraper.log"):
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

class SFRecorderScraper:
    """Scraper for SF Recorder Office website"""
    
    def __init__(self, headless=True, download_dir=None, temp_dir="tmp"):
        """Initialize the scraper with browser configuration."""
        self.base_url = "https://recorder.sfgov.org"
        self.download_dir = Path(download_dir) if download_dir else None
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        
        self.driver = self._setup_driver(headless)
        self.browser = WebDriverWrapper(self.driver)
        self.captcha_solver = CaptchaSolver(temp_dir)
    
    def _setup_driver(self, headless):
        """Set up and configure the WebDriver"""
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        
        # Common Chrome options
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Set download directory if provided
        if self.download_dir:
            prefs = {"download.default_directory": str(self.download_dir)}
            chrome_options.add_experimental_option("prefs", prefs)
        
        return webdriver.Chrome(options=chrome_options)
    
    def navigate_to_site(self):
        """Navigate to the initial site and handle redirects."""
        logger.info(f"Navigating to {self.base_url}")
        self.driver.get(self.base_url)
        time.sleep(2)  # Give time for any redirects
        
        current_url = self.driver.current_url
        logger.info(f"Currently at: {current_url}")
        
        # Check if we're at the disclaimer page
        if "disclaimer" in current_url.lower():
            logger.info("Detected disclaimer page")
            self._accept_disclaimer()
        
        try:
            # Click the Sign On link
            self.browser.click_element(
                By.XPATH, "//a[@ng-click='OnSignInClick()']"
            )
            time.sleep(2)  # Wait for page transition
        except TimeoutException:
            logger.error("Timed out waiting for the Sign On link")
            raise
        except Exception as e:
            logger.error(f"Error clicking Sign On link: {str(e)}")
            raise
    
    def _accept_disclaimer(self):
        """Accept the disclaimer by clicking the agree button."""
        try:
            self.browser.click_element(
                By.XPATH, "//input[@type='button' and @value='Agree']"
            )
            time.sleep(2)  # Wait for page transition
        except TimeoutException:
            logger.error("Timed out waiting for the disclaimer agree button")
            raise
        except Exception as e:
            logger.error(f"Error accepting disclaimer: {str(e)}")
            raise
    
    def login(self, email, password):
        """Handle the login process including CAPTCHA."""
        try:
            # Fill in login form
            self.browser.fill_form_field(
                By.CSS_SELECTOR, "input[type='email']", email
            )
            logger.info(f"Entered email: {email}")
            
            self.browser.fill_form_field(
                By.CSS_SELECTOR, "input[type='password']", password
            )
            logger.info("Entered password")
            
            # Handle CAPTCHA
            # TODO: Need better OCR. Sometimes it works, sometimes it doesn't work until I run 5 times.
            self._solve_captcha(max_retries=50)
            
            # Get submit button
            submit_button_selector = "input[type='submit'][value='Login'][ng-click='LogInUser()']"
            submit_button = self.browser.find_element(By.CSS_SELECTOR, submit_button_selector)
            
            # Wait for the button to become enabled (if it's initially disabled)
            if submit_button.get_attribute("disabled"):
                logger.info("Waiting for submit button to be enabled...")
                try:
                    # Wait up to 5 seconds for the button to become enabled
                    WebDriverWait(self.driver, 5).until_not(
                        EC.element_attribute_to_include((
                            By.CSS_SELECTOR, submit_button_selector
                        ), "disabled")
                    )
                    # Get a fresh reference to the button after waiting
                    submit_button = self.browser.find_element(By.CSS_SELECTOR, submit_button_selector)
                except TimeoutException:
                    logger.warning("Submit button remained disabled, attempting to click anyway")
            
            # Click the button
            logger.info("Clicking the login button")
            submit_button.click()
            # Wait for successful login
            self.browser.wait.until(
                EC.url_changes(self.driver.current_url)
            )
            
            logger.info("Login successful")
            
        except TimeoutException:
            logger.error("Timed out during login process")
            raise
        except Exception as e:
            logger.error(f"Error during login: {str(e)}")
            raise
    
    def _solve_captcha(self, max_retries=2):
        """Handle CAPTCHA solving with retry logic"""
        retries = 0
        captcha_img_path = self.temp_dir / "captcha.png"
        
        while retries <= max_retries:
            try:
                # Find and screenshot the CAPTCHA
                captcha_element = self.browser.find_element(
                    By.XPATH, 
                    "/html/body/div/div[2]/div/div/div/div[2]/div/form/div[4]/div/imagetextcaptcha/div/div/div/canvas",
                    wait_for_presence=True
                )
                captcha_element.screenshot(str(captcha_img_path))
                
                # Solve the CAPTCHA
                captcha_text = self.captcha_solver.solve(captcha_img_path, retries)
                logger.info(f"Attempt {retries+1}: Extracted CAPTCHA text: {captcha_text}")
                
                # Enter the CAPTCHA text
                self.browser.fill_form_field(
                    By.CSS_SELECTOR, "input[ng-model='UserDetails.ClientCaptcha']", captcha_text
                )
                
                # Wait a short time for error message to appear if CAPTCHA is wrong
                time.sleep(2)
                
                # Check if CAPTCHA was successful
                try:
                    submit_button = self.browser.find_element(
                        By.CSS_SELECTOR, 
                        "input[type='submit'][value='Login'][ng-click='LogInUser()']"
                    )
                    if submit_button.get_attribute("disabled"):
                        logger.warning(f"CAPTCHA attempt {retries+1} failed. Retrying...")
                        retries += 1
                        # Refresh the CAPTCHA for next attempt
                        self.browser.click_element(
                            By.CSS_SELECTOR, "img[ng-click='drawCanvas()']"
                        )
                        time.sleep(1)  # Wait for new CAPTCHA to load
                    else:
                        logger.info("CAPTCHA successful!")
                        break
                except NoSuchElementException:
                    # No error message found, CAPTCHA was likely successful
                    logger.info("CAPTCHA successful!")
                    break
                
                # If we've reached max retries, log it but don't throw an exception yet
                if retries > max_retries:
                    logger.error(f"Failed to solve CAPTCHA after {max_retries+1} attempts")
                
            except TimeoutException:
                logger.error("Timed out trying to find CAPTCHA")
                raise
            except Exception as e:
                logger.error(f"Error solving CAPTCHA: {str(e)}")
                raise
        
        # Clean up the images
        # self.captcha_solver.cleanup(retries)
    
    def scrape_data(self, save_path=None):
        """
        Scrape data from the website after login.
        This needs to be customized based on what data you want to extract.
        """
        # Not implemented yet.
        return {}
    
    def save_data(self, data, save_path):
        """Save the scraped data to a file."""
        save_path = Path(save_path)
        save_path.parent.mkdir(exist_ok=True)
        
        with open(save_path, 'w') as f:
            json.dump(data, f, indent=4)
        
        logger.info(f"Data saved to {save_path}")
    
    def close(self):
        """Close the browser and clean up."""
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()
            logger.info("Browser closed")


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
        data = scraper.scrape_data()
        
        if data and args.output:
            scraper.save_data(data, args.output)
        
        logger.info("Scraping completed successfully")
        
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
    finally:
        if scraper:
            scraper.close()


if __name__ == "__main__":
    main()