import os
import time
import logging
import argparse
from datetime import datetime
from dotenv import load_dotenv
import pytesseract
from PIL import Image
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("sf_recorder_scraper")

class SFRecorderScraper:
    def __init__(self, headless=True, download_dir=None):
        """Initialize the scraper with browser configuration."""
        self.base_url = "https://recorder.sfgov.org"
        
        # Set up Chrome options
        chrome_options = Options()
        if headless:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Set download directory if provided
        if download_dir:
            prefs = {"download.default_directory": download_dir}
            chrome_options.add_experimental_option("prefs", prefs)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)  # 10 second timeout
        
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
            
        # Click the Sign On link
        try:
            sign_on_link = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//a[@ng-click='OnSignInClick()']"))
            )
            logger.info("Clicking the Sign On link")
            sign_on_link.click()
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
            # Wait for the disclaimer page to load and find the agree button
            agree_button = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, "//input[@type='button' and @value='Agree']"))
            )
            logger.info("Clicking the agree button")
            agree_button.click()
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
            # Wait for login form elements
            email_field = self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='email']"))
            )
            password_field = self.driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            
            # Fill in credentials
            logger.info(f"Entering email: {email}")
            email_field.clear()
            email_field.send_keys(email)
            
            logger.info("Entering password")
            password_field.clear()
            password_field.send_keys(password)
            
            # Handle CAPTCHA - now with retry logic built in
            self._solve_captcha(max_retries=2)

            # Find the submit button with more specific selectors
            submit_button = self.driver.find_element(
                By.CSS_SELECTOR, 
                "input[type='submit'][value='Login'][ng-click='LogInUser()']"
            )
            
            # Wait for the button to become enabled (if it's initially disabled)
            if submit_button.get_attribute("disabled"):
                logger.info("Waiting for submit button to be enabled...")
                try:
                    # Wait up to 5 seconds for the button to become enabled
                    WebDriverWait(self.driver, 5).until_not(
                        EC.element_attribute_to_include((
                            By.CSS_SELECTOR, 
                            "input[type='submit'][value='Login']"
                        ), "disabled")
                    )
                    # Get a fresh reference to the button after waiting
                    submit_button = self.driver.find_element(
                        By.CSS_SELECTOR, 
                        "input[type='submit'][value='Login'][ng-click='LogInUser()']"
                    )
                except TimeoutException:
                    # If still disabled after timeout, try to click it anyway
                    logger.warning("Submit button remained disabled, attempting to click anyway")
            
            # Click the button
            logger.info("Clicking the login button")
            submit_button.click()
            
            # Wait for successful login
            self.wait.until(
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
        """
        Handle CAPTCHA by taking a screenshot, using OCR, and filling in the result.
        Will retry up to max_retries times if an incorrect CAPTCHA message appears.
        """
        retries = 0
        
        while retries <= max_retries:
            try:
                # Find the CAPTCHA image
                captcha_img = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "/html/body/div/div[2]/div/div/div/div[2]/div/form/div[4]/div/imagetextcaptcha/div/div/div/canvas"))
                )
                
                # Take screenshot of the CAPTCHA
                captcha_img.screenshot("captcha.png")
                
                # Open the image and apply preprocessing
                img = Image.open("captcha.png")
                
                # Convert to grayscale
                img = img.convert('L')
                
                # Apply threshold to create binary image
                threshold = 180  # Slightly lower threshold to capture more detail
                img = img.point(lambda p: 255 if p > threshold else 0)
                
                # Increase size more significantly for better recognition
                img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
                
                # Enhance contrast
                from PIL import ImageEnhance
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(2.0)  # Increase contrast
                
                # Save preprocessed image for debugging
                img.save(f"captcha_processed_{retries}.png")
                
                # Try multiple OCR configurations and combine results
                configs = [
                    '--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 300',
                    '--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 300',
                    '--psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 300'
                ]
                
                results = []
                for config in configs:
                    text = pytesseract.image_to_string(img, config=config)
                    text = ''.join(c for c in text if c.isalnum())
                    if text:
                        results.append(text)
                
                # If we have multiple results, choose the most common one or the longest
                if results:
                    if len(set(results)) == 1:
                        captcha_text = results[0]
                    else:
                        # Choose the most frequent result, or the longest if tied
                        from collections import Counter
                        counter = Counter(results)
                        most_common = counter.most_common()
                        if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
                            # If tied frequency, choose the longer text
                            captcha_text = max(results, key=len)
                        else:
                            captcha_text = most_common[0][0]
                else:
                    # Fallback to basic OCR if all configs failed
                    captcha_text = pytesseract.image_to_string(
                        img,
                        config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 300'
                    )
                    captcha_text = ''.join(c for c in captcha_text if c.isalnum())
                
                # Apply custom post-processing for common mistakes
                # captcha_text = captcha_text.replace('o', 'O').replace('0', 'O')
                # captcha_text = captcha_text.replace('G', '6').replace('S', '5')
                # captcha_text = captcha_text.replace('B', '8').replace('I', '1')
                # captcha_text = captcha_text.replace('Z', '2')
                
                # Make sure we have the expected length (typically 6 characters)
                expected_length = 6  # Adjust if your CAPTCHAs have a different length
                if len(captcha_text) > expected_length:
                    captcha_text = captcha_text[:expected_length]
                
                logger.info(f"Attempt {retries+1}: Extracted CAPTCHA text: {captcha_text}")
                
                # Find and fill in the CAPTCHA input field
                captcha_input = self.driver.find_element(
                    By.CSS_SELECTOR, "input[ng-model='UserDetails.ClientCaptcha']"
                )
                captcha_input.clear()
                captcha_input.send_keys(captcha_text)
                # Wait a short time for error message to appear if CAPTCHA is wrong
                time.sleep(2)
                
                # Check if error message is displayed
                try:
                    submit_button = self.driver.find_element(
                        By.CSS_SELECTOR, 
                        "input[type='submit'][value='Login'][ng-click='LogInUser()']"
                    )
                    if submit_button.get_attribute("disabled"):
                        logger.warning(f"CAPTCHA attempt {retries+1} failed. Retrying...")
                        retries += 1
                        # Need to refresh the CAPTCHA for next attempt
                        refresh_button = self.driver.find_element(
                            By.CSS_SELECTOR, "img[ng-click='drawCanvas()']"
                        )
                        refresh_button.click()
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
            
            # Clean up the images (uncomment for production)
            # for i in range(retries):
            #     if os.path.exists(f"captcha_processed_{i}.png"):
            #         os.remove(f"captcha_processed_{i}.png")
            # if os.path.exists("captcha.png"):
            #     os.remove("captcha.png")
    
    def scrape_data(self, save_path=None):
        """
        Scrape data from the website after login.
        This needs to be customized based on what data you want to extract.
        """
        try:
            # Wait for the main content to load
            main_content = self.wait.until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(@class, 'main-content')]"))
            )
            
            # Example: Extract table data
            # Modify these selectors based on the actual structure of the site
            tables = self.driver.find_elements(By.TAG_NAME, "table")
            
            all_data = []
            
            for i, table in enumerate(tables):
                logger.info(f"Processing table {i+1}/{len(tables)}")
                
                # Extract headers
                headers = [th.text for th in table.find_elements(By.TAG_NAME, "th")]
                
                # Extract rows
                rows = []
                for tr in table.find_elements(By.TAG_NAME, "tr")[1:]:  # Skip header row
                    row_data = [td.text for td in tr.find_elements(By.TAG_NAME, "td")]
                    rows.append(row_data)
                
                table_data = {
                    "headers": headers,
                    "rows": rows
                }
                
                all_data.append(table_data)
            
            # Save data if path provided
            if save_path:
                self._save_data(all_data, save_path)
            
            return all_data
            
        except TimeoutException:
            logger.error("Timed out waiting for main content")
            raise
        except Exception as e:
            logger.error(f"Error scraping data: {str(e)}")
            raise
    
    def _save_data(self, data, save_path):
        """Save the scraped data to a file."""
        import json
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        # Save as JSON
        with open(save_path, 'w') as f:
            json.dump(data, f, indent=4)
        
        logger.info(f"Data saved to {save_path}")
    
    def close(self):
        """Close the browser and clean up."""
        if self.driver:
            self.driver.quit()
            logger.info("Browser closed")


def main():
    """Main function to run the scraper."""
    parser = argparse.ArgumentParser(description='SF Recorder Office Scraper')
    parser.add_argument('--email', help='Login email')
    parser.add_argument('--password', help='Login password')
    parser.add_argument('--headless', action='store_true', help='Run in headless mode')
    parser.add_argument('--output', help='Output file path', default=f'data/sf_recorder_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    
    args = parser.parse_args()
    
    # Load environment variables from .env file
    load_dotenv()
    
    # Use command line args or environment variables
    email = args.email or os.getenv('SF_RECORDER_EMAIL')
    password = args.password or os.getenv('SF_RECORDER_PASSWORD')
    
    if not email or not password:
        logger.error("Email and password are required. Provide them via command line arguments or .env file")
        return
    
    scraper = None
    try:
        # Create download directory
        download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(download_dir, exist_ok=True)
        
        # Initialize and run scraper
        scraper = SFRecorderScraper(headless=args.headless, download_dir=download_dir)
        scraper.navigate_to_site()
        scraper.login(email, password)
        # data = scraper.scrape_data(save_path=args.output)
        
        logger.info("Scraping completed successfully")
        
    except Exception as e:
        logger.error(f"Scraping failed: {str(e)}")
    finally:
        if scraper:
            scraper.close()


if __name__ == "__main__":
    main()