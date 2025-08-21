import re 
from typing import Dict, Any
from langchain.tools import BaseTool
from pydantic import Field

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

class SMSTool(BaseTool):
    name: str = "sms"
    description: str = "Send SMS messages via Twilio"
    account_sid: str = Field(default="")
    auth_token: str = Field(default="")
    phone_number: str = Field(default="")
    
    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        if not TWILIO_AVAILABLE:
            return {"success": False, "error": "Twilio not available"}
        
        try:
            if action == "send_payment_sms":
                return self._send_payment_sms(**kwargs)
            else:
                return {"success": False, "error": "Unknown action"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _send_payment_sms(self, phone: str, amount: str, booking_ref: str, payment_link: str) -> Dict[str, Any]:
        # Clean phone number
        if phone.startswith('0'):
            phone = f"+44{phone[1:]}"
        elif not phone.startswith('+'):
            phone = f"+44{phone}"
        
        if not re.match(r'^\+44\d{9,10}$', phone):
            return {"success": False, "error": "Invalid UK phone number"}
        
        client = Client(self.account_sid, self.auth_token)
        
        message_body = f"""Waste King Payment
Amount: £{amount}
Reference: {booking_ref}

Pay securely: {payment_link}

Thank you!"""
        
        message = client.messages.create(
            body=message_body,
            from_=self.phone_number,
            to=phone
        )
        
        return {
            "success": True,
            "sms_sid": message.sid,
            "phone": phone,
            "amount": amount
        }
