import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, Any

from dotenv import load_dotenv
from pydantic import BaseModel, Field, validator
from langchain_core.tools import tool

# Load environment variables from a .env file
load_dotenv()

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Pydantic Schema for Tool Input ---
class NotifyFraudInput(BaseModel):
    """Input schema for the fraud notification tool."""
    # --- FIX 1: Allow NIK to be optional ---
    nik: Optional[str] = Field(None, description="The identity number (NIK) that was flagged.")
    reason: str = Field(description="The specific reason why fraud is suspected.")
    details: Optional[Dict[str, str]] = Field(None, description="Optional dictionary of submitted details.")

    @validator('details', pre=True)
    def empty_str_to_none(cls, v: Any) -> Any:
        if v == '':
            return None
        return v

@tool("notify_fraud_tool", args_schema=NotifyFraudInput)
def notify_fraud_tool(reason: str, nik: Optional[str] = None, details: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Sends an email notification about a potential fraud attempt with a specific reason."""
    # --- FIX 2: If NIK is None, default it to the string "unknown" ---
    nik = nik or "unknown"

    email_host = os.getenv("EMAIL_HOST")
    email_port = os.getenv("EMAIL_PORT")
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")
    recipient_email = os.getenv("EMAIL_USER") # Sending to self for this example

    if not all([email_host, email_port, email_user, email_pass]):
        error_msg = "Email credentials (HOST, PORT, USER, PASS) are not fully set in the .env file."
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}

    # --- Construct the Email Message ---
    subject = f"🚨 FRAUD ALERT: Suspicious Activity Detected for NIK: {nik}"

    # Build details string if provided
    details_str = ""
    if details:
        for key, value in details.items():
            details_str += f"• {key.replace('_', ' ').title()}: {value}\n"

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; border: 1px solid #ddd; padding: 20px;">
            <div style="background-color: #f8d7da; color: #721c24; padding: 15px; border-radius: 5px; text-align: center;">
                <h1 style="margin: 0;">🚨 FRAUD DETECTION ALERT</h1>
            </div>
            <div style="padding: 20px 0;">
                <h2 style="color: #495057;">Incident Details</h2>
                <p>A potential identity fraud attempt has been detected in our system. Immediate review is required.</p>
                <div style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 15px;">
                    <p><strong>Identity Number (NIK):</strong> {nik}</p>
                    <p><strong>Reason for Flagging:</strong> <strong style="color: #c00;">{reason}</strong></p>
                </div>
                {f'''
                <h3 style="color: #495057; margin-top: 20px;">Submitted Information:</h3>
                <div style="background-color: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; padding: 15px; white-space: pre-wrap;">{details_str}</div>
                ''' if details_str else ''}
                <div style="margin-top: 20px; background-color: #cce5ff; color: #004085; padding: 15px; border-radius: 5px;">
                    <h2 style="margin-top:0;">Action Required</h2>
                    <p>Please investigate this incident immediately and take appropriate action according to security protocols.</p>
                </div>
            </div>
            <div style="text-align: center; color: #6c757d; font-size: 12px; margin-top: 20px;">
                <p><em>This is an automated message from the Security Monitoring System.</em></p>
            </div>
        </div>
    </body>
    </html>
    """

    message = MIMEMultipart()
    message["From"] = f"ID Check Security System <{email_user}>"
    message["To"] = recipient_email
    message["Subject"] = subject
    message.attach(MIMEText(html_body, 'html'))

    # --- Send the Email ---
    try:
        with smtplib.SMTP(email_host, int(email_port)) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.sendmail(email_user, recipient_email, message.as_string())
        logger.info(f"Fraud notification email for NIK {nik} sent successfully.")
        return {"status": "success", "message": f"Fraud notification for NIK {nik} sent."}
    except Exception as e:
        logger.error(f"Failed to send email for NIK {nik}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}