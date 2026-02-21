# utils/ocr_processor.py
import os
import shutil
import pytesseract
from PIL import Image
import cv2
import numpy as np
import io
import aiohttp
import re
from config import Config
import logging

logger = logging.getLogger(__name__)

class OCRProcessor:
    def __init__(self):
        self.config = Config()
        self.available = False
        
        # Set tesseract path from config
        if self.config.TESSERACT_PATH and os.path.exists(self.config.TESSERACT_PATH):
            pytesseract.pytesseract.tesseract_cmd = self.config.TESSERACT_PATH
            self.available = True
        elif shutil.which('tesseract'):
            self.available = True
        else:
            logger.warning(f"Tesseract OCR not found at '{self.config.TESSERACT_PATH}' and not in PATH. OCR features will be disabled.")
    
    async def extract_amount_from_image(self, image_url: str) -> int:
        """
        Extract payment amount from proof image using OCR
        Returns: Amount in integer, or 0 if failed
        """
        if not self.available:
            return 0
            
        try:
            # Download image
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        return 0
                    
                    image_data = await response.read()
            
            # Convert to PIL Image
            image = Image.open(io.BytesIO(image_data))
            
            # Preprocess image for better OCR
            img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
            
            # Apply adaptive thresholding (Better for receipts with uneven lighting)
            thresh = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            
            # Convert back to PIL
            processed_image = Image.fromarray(thresh)
            
            # Use OCR to extract text
            custom_config = r'--oem 3 --psm 6'
            text = pytesseract.image_to_string(processed_image, config=custom_config)
            
            # Find amount in text
            amount = self._extract_amount_from_text(text)
            
            logger.info(f"OCR extracted text: {text[:100]}...")
            logger.info(f"Extracted amount: {amount}")
            
            return amount
            
        except Exception as e:
            logger.error(f"OCR processing error: {e}")
            return 0
    
    def _extract_amount_from_text(self, text: str) -> int:
        """Extract amount from OCR text"""
        # Patterns to find amounts
        # Updated regex to allow spaces within numbers (common OCR issue)
        patterns = [
            r'Rp[\s\.:]*([\d\., ]+)', 
            r'IDR[\s\.:]*([\d\., ]+)',
            r'Total[\s\W]*([\d\., ]+)',
            r'Jumlah[\s\W]*([\d\., ]+)',
            r'Nominal[\s\W]*([\d\., ]+)',
            r'Transfer[\s\W]*([\d\., ]+)',
        ]
        
        candidates = []

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                candidates.append(match)
        
        # Fallback: Find standalone numbers with separators
        fallback_matches = re.findall(r'\b\d{1,3}(?:[\., ]\d{3})+(?:[\.,]\d{1,2})?\b', text)
        candidates.extend(fallback_matches)

        best_amount = 0

        for amount_str in candidates:
            # Cleanup
            clean_str = amount_str.strip()
            if '\n' in clean_str: clean_str = clean_str.split('\n')[0]
            clean_str = clean_str.replace(' ', '')

            # Logic: Split at the last separator to check for cents
            # Priority: Comma (IDR) -> Dot (US/Error)
            
            # 1. Check for Comma Cents (e.g. 10.000,00)
            if ',' in clean_str:
                parts = clean_str.rsplit(',', 1)
                # If suffix is 1 or 2 digits, assume cents and discard
                if len(parts) > 1 and len(parts[1]) <= 2 and parts[1].isdigit():
                    clean_str = parts[0]
            
            # 2. Check for Dot Cents (e.g. 10.000.00 - OCR Error or US)
            # Only discard if exactly 2 digits. 3 digits = thousands.
            if '.' in clean_str:
                parts = clean_str.rsplit('.', 1)
                if len(parts) > 1 and len(parts[1]) == 2 and parts[1].isdigit():
                    clean_str = parts[0]

            # Sanitize to digits only
            final_digits = re.sub(r'[^0-9]', '', clean_str)
            
            try:
                if final_digits:
                    val = int(final_digits)
                    # Filter unrealistic amounts (e.g. 1, 6, 13)
                    # Assuming transactions are usually > 1000, but keeping > 100 to be safe
                    if val > 100:
                        # Heuristic: Prefer larger amounts but filter out dates/IDs (usually very large)
                        if val > best_amount and val < 100000000000:
                            best_amount = val
            except ValueError:
                continue
        
        return best_amount