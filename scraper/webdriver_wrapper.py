import time
import logging
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from typing import Optional, Union

logger = logging.getLogger("sf_recorder_scraper")

class WebDriverWrapper:
    """Wrapper for Selenium WebDriver to simplify common browser operations"""
    
    def __init__(self, driver: WebDriver, timeout: int = 10):
        """
        Initialize the WebDriver wrapper
        
        Args:
            driver: Selenium WebDriver instance
            timeout: Default timeout in seconds for wait operations
        """
        self.driver = driver
        self.wait = WebDriverWait(driver, timeout)
    
    def find_element(self, by: str, value: str, 
                    wait_for_clickable: bool = False,
                    wait_for_presence: bool = False) -> WebElement:
        """
        Find an element with optional waiting conditions
        
        Args:
            by: Selenium locator type (By.ID, By.CSS_SELECTOR, etc.)
            value: Locator value to find the element
            wait_for_clickable: Whether to wait until the element is clickable
            wait_for_presence: Whether to wait until the element is present in DOM
            
        Returns:
            The found WebElement
            
        Raises:
            TimeoutException: If element not found within timeout period
        """
        if wait_for_clickable:
            return self.wait.until(EC.element_to_be_clickable((by, value)))
        elif wait_for_presence:
            return self.wait.until(EC.presence_of_element_located((by, value)))
        else:
            return self.driver.find_element(by, value)
    
    def click_element(self, by: str, value: str, 
                     wait_for_clickable: bool = True, wait_for_presence: bool = True) -> WebElement:
        """
        Find and click an element
        
        Args:
            by: Selenium locator type
            value: Locator value to find the element
            wait_for_clickable: Whether to wait until the element is clickable
            wait_for_presence: Whether to wait until the element is present in DOM
            
        Returns:
            The clicked WebElement
            
        Raises:
            TimeoutException: If element not found or not clickable within timeout
        """
        element = self.find_element(by, value, wait_for_clickable=wait_for_clickable, wait_for_presence=wait_for_presence)
        element.click()
        return element
    
    def fill_form_field(self, by: str, value: str, text: str, 
                       clear_first: bool = True) -> WebElement:
        """
        Fill a form field with text
        
        Args:
            by: Selenium locator type
            value: Locator value to find the element
            text: Text to enter into the field
            clear_first: Whether to clear the field before entering text
            
        Returns:
            The WebElement of the form field
            
        Raises:
            TimeoutException: If element not found within timeout period
        """
        element = self.find_element(by, value, wait_for_presence=True)
        if clear_first:
            element.clear()
            time.sleep(0.5)  # Short delay after clearing
        element.send_keys(text)
        return element 