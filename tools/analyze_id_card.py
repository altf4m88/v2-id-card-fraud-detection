import os
import base64
import logging
import json
import io
from typing import Dict, Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from PIL import Image

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pydantic Schema for Tool Input ---
class AnalyzeIdCardInput(BaseModel):
    """Input schema for the ID card analysis tool."""
    image_path: str = Field(description="The file path to the ID card image to be analyzed.")

@tool("analyze_id_card_tool", args_schema=AnalyzeIdCardInput)
def analyze_id_card_tool(image_path: str) -> Dict[str, Any]:
    """
    Analyzes an ID card image using a detailed set of rules for quality, data extraction,
    and positional checks. It returns a dictionary with the analysis outcome.
    """
    if not os.path.exists(image_path):
        logger.error(f"File not found at path: {image_path}")
        return {"status": "error", "error": f"File not found at path: {image_path}"}
    
    print('calling tool')

    # --- Initialize the Gemini Vision Model ---
    try:
        # Using a powerful vision-capable model as requested.
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-preview-05-20",
            thinking_budget=2000,
            temperature=0.2,
            include_thoughts=True,
            verbose=True,
        )
    except Exception as e:
        logger.error(f"Failed to initialize the language model: {e}")
        return {"status": "error", "error": "Could not initialize Gemini model. Check API key."}

    # --- Prepare the Image ---
    try:
        with Image.open(image_path) as img:
            byte_arr = io.BytesIO()
            img.convert("RGB").save(byte_arr, format='PNG')
            image_b64 = base64.b64encode(byte_arr.getvalue()).decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to process the image: {e}")
        return {"status": "error", "error": f"Invalid or corrupted image file: {image_path}"}

    # --- Construct the Detailed Prompt ---
    prompt = """
    You are an ID card verification system. Your primary goal is to accurately assess ID card images based on a set of predefined rules.
    You must return a single JSON object with a "status" field and other relevant fields based on the outcome.

    ---
    ### 1. Image Quality Check
    First, **immediately refuse** the image if any of the following issues are detected. If you refuse it, return a JSON with `{"status": "image_quality_failure", "reason": "..."}`.
    * **Incorrect Orientation:** The ID card is upside down or significantly rotated.
    * **Blur:** The image is blurry, making text or features unreadable.
    * **Glare:** There is significant glare obstructing parts of the ID card.
    * **Cropping/Incomplete:** The entire ID card is not visible or parts are cut off.

    ---
    ### 2. ID Card Data Extraction and Validation
    If the image quality is acceptable, proceed with the following checks. **You must extract and validate all specified fields.** If any required field is missing, unreadable, or invalid, **flag as potential fraud**.

    **Required Fields and Validation Rules:**
    * **NIK:** Must be a 16-digit number.
    * **Nama:** Must be present as text.
    * **Tempat/Tgl Lahir:** Must consist of a place (text) followed by a date in `DD-MM-YYYY` format.
    * **Jenis Kelamin:** Must be either "LAKI-LAKI" or "PEREMPUAN".
    * **Gol. Darah:** Must be one of "A", "AB", "B", "O", or "-".
    * **Alamat:** Must be present as text.
    * **RT/RW:** Must be a number with the format `XXX/XXX`.
    * **Kel/Desa:** Must be present as text.
    * **Kecamatan:** Must be present as text.
    * **Agama:** Must be one of: "ISLAM", "PROTESTAN", "KATOLIK", "HINDU", "BUDDHA", "KHONGHUCU", or "KEPERCAYAAN TERHADAP TUHAN YME".
    * **Status Perkawinan:** Must be one of: "BELUM KAWIN", "KAWIN", "CERAI HIDUP", or "CERAI MATI".
    * **Kewarganegaraan:** Must be "WNI" or "WNA".
    * **Berlaku Hingga:** Must be a date in `DD-MM-YYYY` format or "SEUMUR HIDUP".
    * **Place and Date of Creation:** Must be a place and date, located under the face image.
    * **Signature:** A signature must be present on the bottom right.

    ---
    ### 3. Positional Checks
    * **ID Card Face Image:** Must be located on the right side of the ID card.
    * **Place and Date of Creation:** Must be located on the right side, directly under the face image.
    * **Signature:** Must be located on the bottom right of the ID card.

    ---
    ### 4. Output Format
    Based on your analysis, return ONLY a single valid JSON object. Do not include any other text, explanations, or markdown formatting.

    * **If all checks pass:** Return `{"status": "success", "data": { ... all extracted fields ... }}`.
    * **If data/positional checks fail:** Return `{"status": "potential_fraud", "reason": "Specific field or positional check that failed."}`.
    * **If image quality fails:** Return `{"status": "image_quality_failure", "reason": "Specific quality issue like 'Blur' or 'Glare'."}`.
    """

    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
        ]
    )

    # --- Invoke the Model and Parse the Response ---
    try:
        logger.info(f"Sending image '{image_path}' to Gemini for detailed analysis...")
        response = llm.invoke([message])
        logger.info(response)
        response_content = response.content.strip()

        # Clean the response to ensure it is valid JSON
        if response_content.startswith("```json"):
            response_content = response_content[7:-4].strip()

        # Parse the JSON string into a Python dictionary
        result = json.loads(response_content)
        logger.info(f"Successfully received and parsed analysis from model: {result}")
        return result

    except json.JSONDecodeError:
        error_msg = "Failed to parse the model's response as JSON."
        logger.error(f"{error_msg} Raw response: {response_content}")
        return {"status": "error", "error": error_msg, "raw_response": response_content}
    except Exception as e:
        logger.error(f"An unexpected error occurred during model invocation: {e}")
        return {"status": "error", "error": str(e)}