import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger("sf_recorder_scraper")

class WebDriverWrapper:
    """Wrapper for WebDriver to handle common operations"""
    
    def __init__(self, driver, timeout: int = 10):
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)
    
    def find_element(self, by, value, wait_for_clickable=False, wait_for_presence=False):
        """Find an element with optional waiting conditions"""
        if wait_for_clickable:
            return self.wait.until(EC.element_to_be_clickable((by, value)))
        elif wait_for_presence:
            return self.wait.until(EC.presence_of_element_located((by, value)))
        else:
            return self.driver.find_element(by, value)
    
    def click_element(self, by, value, wait_for_clickable=True):
        """Find and click an element"""
        element = self.find_element(by, value, wait_for_clickable=wait_for_clickable)
        element.click()
        return element
    
    def fill_form_field(self, by, value, text, clear_first=True):
        """Fill a form field"""
        element = self.find_element(by, value, wait_for_presence=True)
        if clear_first:
            element.clear()
        element.send_keys(text)
        return element 