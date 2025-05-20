import time
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver

# Import our refactored classes
from captcha_solver import CaptchaSolver
from webdriver_wrapper import WebDriverWrapper

logger = logging.getLogger("sf_recorder_scraper")

class SFRecorderScraper:
    """Scraper for San Francisco Recorder Office website to extract property records"""
    
    def __init__(self, headless: bool = True, download_dir: Optional[str] = None, temp_dir: str = "tmp"):
        """
        Initialize the SF Recorder scraper
        
        Args:
            headless: Whether to run the browser in headless mode
            download_dir: Directory to save downloaded files
            temp_dir: Directory for temporary files like CAPTCHA images
        """
        self.base_url = "https://recorder.sfgov.org"
        self.download_dir = Path(download_dir) if download_dir else None
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
        
        self.driver = self._setup_driver(headless)
        self.browser = WebDriverWrapper(self.driver)
        self.captcha_solver = CaptchaSolver(temp_dir)
    
    def _setup_driver(self, headless: bool) -> WebDriver:
        """
        Set up and configure the Selenium WebDriver
        
        Args:
            headless: Whether to run the browser in headless mode
            
        Returns:
            Configured WebDriver instance
        """
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
    
    def navigate_to_site(self) -> None:
        """
        Navigate to the initial site and handle any redirects or disclaimers
        
        Raises:
            TimeoutException: If site navigation takes too long
        """
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
    
    def _accept_disclaimer(self) -> None:
        """
        Accept the site disclaimer by clicking the agree button
        
        Raises:
            TimeoutException: If disclaimer acceptance takes too long
        """
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
    
    def login(self, email: str, password: str) -> None:
        """
        Handle the login process including CAPTCHA solving
        
        Args:
            email: User email for login
            password: User password for login
            
        Raises:
            TimeoutException: If login process takes too long
            Exception: For any other errors during login
        """
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
            
            # # Handle CAPTCHA
            import pdb; pdb.set_trace()
            # self._solve_captcha(max_retries=50)
            
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
    
    def _solve_captcha(self, max_retries: int = 2) -> None:
        """
        Handle CAPTCHA solving with retry logic
        
        Args:
            max_retries: Maximum number of times to retry CAPTCHA solving
            
        Raises:
            TimeoutException: If CAPTCHA locating takes too long
            Exception: For any other errors during CAPTCHA solving
        """
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
        self.captcha_solver.cleanup(retries)

    def click_element(self, selector: str, by: By = By.CSS_SELECTOR) -> None:
        """
        Navigate to a page by clicking on a button or link
        
        Args:
            selector: CSS selector for the element to click
        """
        self.browser.click_element(by, selector)

    def _clear_date_field(self, field_name: str) -> None:
        """
        Clear a date input field by sending a fixed number of backspaces
        
        Args:
            field_name: The name attribute of the input field to clear
        """
        input_field_css_selector = f"input[name='{field_name}']"
        field = self.browser.find_element(
            By.CSS_SELECTOR, input_field_css_selector, wait_for_presence=True
        )
        
        # Send fixed number of backspaces
        backspace_count = 10
        for _ in range(backspace_count):
            field.send_keys("\b")      # Backspace
        # Verify field is empty
        current_value = self.driver.execute_script(
            f"return document.querySelector(\"{input_field_css_selector}\").value;"
        )
        if current_value:
            logger.warning(f"Field {field_name} still not empty after clearing. Current value: '{current_value}'")
        
        return field

    def fill_advanced_search_form(self, from_date: str, to_date: str) -> None:
        """
        Fill the advanced search form with date range
        
        Args:
            from_date: Starting date in MM/DD/YYYY format
            to_date: Ending date in MM/DD/YYYY format
        """
        time.sleep(1)
        # Close any open datetime pickers
        self.driver.execute_script("""
            // Hide all datetime pickers to prevent them from interfering with input
            document.querySelectorAll('.datetimepicker').forEach(picker => picker.style.display = 'none');
        """)
        # Clear and fill from date field
        from_field = self._clear_date_field("fromDocDate")
        from_field.send_keys(from_date)
        logger.info(f"Entered from date: {from_date}")
        # Close any open datetime pickers
        self.driver.execute_script("""
            // Hide all datetime pickers to prevent them from interfering with input
            document.querySelectorAll('.datetimepicker').forEach(picker => picker.style.display = 'none');
        """)
        # Clear and fill to date field
        to_field = self._clear_date_field("toDocDate")
        to_field.send_keys(to_date)
        logger.info(f"Entered to date: {to_date}")
        
        # Close any open datetime pickers
        self.driver.execute_script("""
            // Hide all datetime pickers to prevent them from interfering with input
            document.querySelectorAll('.datetimepicker').forEach(picker => picker.style.display = 'none');
        """)
    
    def navigate_to_search(self) -> None:
        """
        Click the search button and ensure redirection to search results page
        
        Raises:
            TimeoutException: If navigation to search results takes too long
            Exception: For any other errors during search navigation
        """
        try:
            # First, try clicking directly on the element to trigger any attached events
            search_button = self.browser.find_element(
                By.CSS_SELECTOR, "button#btnSearch", wait_for_presence=True
            )
            logger.info("Found search button, attempting to click")
            # Try to execute the Angular function directly (aria-hidden is set to true so direct click fails)
            try:
                self.driver.execute_script("angular.element(document.getElementById('btnSearch')).scope().Search();")
                logger.info("Executed Angular Search() function")
            except Exception as e:
                logger.warning(f"Angular function execution failed: {str(e)}")
            
            # Wait for URL to change to search results
            try:
                WebDriverWait(self.driver, 100).until(
                    lambda driver: "searchResult" in driver.current_url
                )
                logger.info(f"Successfully navigated to search results: {self.driver.current_url}")
            except TimeoutException:
                logger.warning("Timed out waiting for redirect to search results page")
                raise Exception("Failed to navigate to search results page")
            
        except Exception as e:
            logger.error(f"Error in search navigation: {str(e)}")
            raise
        
    def scrape_data(self, save_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Scrape data from the website after login
        
        Args:
            save_path: Optional path to save scraped data
            
        Returns:
            Dictionary containing the scraped data
        """
        # Not implemented yet.
        return {}
    
    def save_data(self, data: Dict[str, Any], save_path: str) -> None:
        """
        Save the scraped data to a JSON file
        
        Args:
            data: Dictionary containing scraped data
            save_path: Path to save the file
        """
        save_path = Path(save_path)
        save_path.parent.mkdir(exist_ok=True)
        
        with open(save_path, 'w') as f:
            json.dump(data, f, indent=4)
        
        logger.info(f"Data saved to {save_path}")
    
    def close(self) -> None:
        """Close the browser and clean up resources"""
        if hasattr(self, 'driver') and self.driver:
            self.driver.quit()
            logger.info("Browser closed") 