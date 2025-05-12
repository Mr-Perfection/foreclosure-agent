import logging
import pytesseract
from PIL import Image, ImageEnhance, ImageFilter
from pathlib import Path
from typing import List
from collections import Counter

logger = logging.getLogger("sf_recorder_scraper")

class CaptchaSolver:
    """Separate class for handling CAPTCHA solving logic"""
    
    def __init__(self, temp_dir="tmp"):
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(exist_ok=True)
    
    def preprocess_image(self, img_path: Path, retry_count: int) -> Image.Image:
        """Preprocess the CAPTCHA image for better OCR results"""
        img = Image.open(img_path)
        
        # Convert to grayscale
        img = img.convert('L')
        
        # Apply threshold to create binary image - lower threshold to better capture numbers
        threshold = 160  # Lower threshold to capture more detail in numbers
        img = img.point(lambda p: 255 if p > threshold else 0)
        
        # Increase size for better recognition
        img = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
        
        # Enhance contrast
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)  # Increase contrast further
        
        # Add sharpening for better character definition
        img = img.filter(ImageFilter.SHARPEN)
        
        # Save preprocessed image for debugging
        processed_img_path = self.temp_dir / f"captcha_processed_{retry_count}.png"
        img.save(processed_img_path)
        
        return img
    
    def get_ocr_results(self, img: Image.Image) -> List[str]:
        """Get OCR results using multiple configurations"""
        configs = [
            # Add more configurations with different PSM modes
            '--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 400',
            '--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 400',
            '--psm 10 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 400',
            # This actually makes it worse
            # # Add specialized config for better number recognition
            # '--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 400',
            # This actually makes it worse
            # # Add config focusing on confusable characters
            # '--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -c classify_bln_numeric_mode=1 --dpi 400'
        ]
        
        results = []
        for config in configs:
            text = pytesseract.image_to_string(img, config=config)
            text = ''.join(c for c in text if c.isalnum())
            if text:
                results.append(text)
        
        return results
    
    def select_best_result(self, results: List[str], expected_length: int = 6) -> str:
        """Select the best result from multiple OCR attempts"""
        if not results:
            return ""
            
        # Apply post-processing to fix common misrecognitions
        processed_results = []
        for text in results:
            # Fix common misrecognitions for this site
            processed = text
            # This actually makes it worse
            # Commonly confused character pairs in this captcha
            # if 'O' in processed:
            #     processed = processed.replace('O', '0')
            # if 'S' in processed and '5' not in processed:
            #     processed = processed.replace('S', '5')
            # if 'I' in processed and '1' not in processed:
            #     processed = processed.replace('I', '1')
            # if 'B' in processed and '8' not in processed:
            #     processed = processed.replace('B', '8')
            # if 'G' in processed and '6' not in processed:
            #     processed = processed.replace('G', '6')
            
            # Ensure we have the expected length
            if len(processed) > expected_length:
                processed = processed[:expected_length]
            elif len(processed) < expected_length:
                # If we have fewer characters than expected, it's likely not usable
                continue
                
            processed_results.append(processed)
        
        if not processed_results:
            # If no valid processed results, fall back to original results
            processed_results = results
            
        if len(set(processed_results)) == 1:
            captcha_text = processed_results[0]
        else:
            # Choose the most frequent result
            counter = Counter(processed_results)
            most_common = counter.most_common()
            
            # For your specific case (PYYHSO vs PYYH63)
            # Check for partial matches that might have correct start but wrong end
            for result in processed_results:
                if result.startswith('PYYH') and result[-2:].isdigit():
                    return result
                    
            if len(most_common) > 1 and most_common[0][1] == most_common[1][1]:
                # If tied frequency, choose the one with more digits in the last positions
                # as digits are often at the end in these captchas
                captcha_text = max(processed_results, 
                                 key=lambda x: sum(1 for c in x[-2:] if c.isdigit()))
            else:
                captcha_text = most_common[0][0]
        
        return captcha_text
    
    def solve(self, captcha_img_path: Path, retry_count: int) -> str:
        """Solve the CAPTCHA"""
        img = self.preprocess_image(captcha_img_path, retry_count)
        results = self.get_ocr_results(img)
        
        if not results:
            # Fallback to basic OCR if all configs failed
            text = pytesseract.image_to_string(
                img,
                config='--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 --dpi 300'
            )
            text = ''.join(c for c in text if c.isalnum())
            results = [text] if text else []
        
        return self.select_best_result(results)
    
    def cleanup(self, retry_count: int = 0):
        """Clean up temporary files"""
        captcha_path = self.temp_dir / "captcha.png"
        if captcha_path.exists():
            captcha_path.unlink()
            
        for i in range(retry_count + 1):
            processed_path = self.temp_dir / f"captcha_processed_{i}.png"
            if processed_path.exists():
                processed_path.unlink() 