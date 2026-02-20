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
        patterns = [
            r'Rp[\s\.]*([\d\.,]+)',  # Rp 100.000 (lebih fleksibel)
            r'IDR[\s\.]*([\d\.,]+)',
            r'Total[\s\W]*([\d\.,]+)',
            r'Jumlah[\s\W]*([\d\.,]+)',
            r'Nominal[\s\W]*([\d\.,]+)',
            r'Transfer[\s\W]*([\d\.,]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Take the first match (usually the largest amount)
                amount_str = matches[0]
                
                # Fix Parsing Angka (CRITICAL - BCA/E-Wallet)
                # Logic: Split at the last dot (.) if it looks like cents, then regex
                
                # Check for decimal part (e.g., .00)
                if '.' in amount_str:
                    parts = amount_str.rsplit('.', 1)
                    # If the last part is exactly 2 digits, assume it's cents and discard it
                    if len(parts) > 1 and len(parts[1]) == 2 and parts[1].isdigit():
                        amount_str = parts[0]
                
                # Aggressive sanitization: Remove everything except digits
                amount_clean = re.sub(r'[^0-9]', '', amount_str)
                
                try:
                    if amount_clean:
                        return int(amount_clean)
                except ValueError:
                    continue
        
        # If no pattern matches, try to find any number that looks like an amount
        numbers = re.findall(r'\b\d{4,}\b', text)  # Find numbers with 4+ digits
        if numbers:
            try:
                # Filter angka yang terlalu panjang (ID Transaksi biasanya > 12 digit)
                valid_numbers = [int(n) for n in numbers if len(n) < 12]
                if valid_numbers:
                    return max(valid_numbers)
            except ValueError:
                pass
        
        return 0