# tools/sms_tool.py - FIXED VERSION
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
            return {"success": False, "error": "Twilio not available - install twilio package"}
        
        try:
            if action == "send_payment_sms":
                return self._send_payment_sms(**kwargs)
            elif action == "send_booking_confirmation":
                return self._send_booking_confirmation(**kwargs)
            else:
                return {"success": False, "error": f"Unknown SMS action: {action}"}
        except Exception as e:
            print(f"❌ SMS Error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _send_payment_sms(self, phone: str, amount: str, booking_ref: str, payment_link: str) -> Dict[str, Any]:
        """Send payment SMS to customer"""
        
        # Clean and validate phone number
        clean_phone = self._clean_phone_number(phone)
        if not clean_phone['valid']:
            return {"success": False, "error": clean_phone['error']}
        
        if not self.account_sid or not self.auth_token:
            print("⚠️ Twilio credentials not configured - simulating SMS")
            return {
                "success": True,
                "sms_sid": "simulated_sms_123",
                "phone": clean_phone['phone'],
                "amount": amount,
                "simulated": True,
                "message": f"SMS would be sent to {clean_phone['phone']}: Pay £{amount} for booking {booking_ref}"
            }
        
        try:
            client = Client(self.account_sid, self.auth_token)
            
            message_body = f"""🗑️ WasteKing Payment Required

💰 Amount: £{amount}
📋 Reference: {booking_ref}

💳 Pay securely: {payment_link}

Thank you for choosing WasteKing!"""
            
            message = client.messages.create(
                body=message_body,
                from_=self.phone_number,
                to=clean_phone['phone']
            )
            
            print(f"✅ Payment SMS sent to {clean_phone['phone']}")
            
            return {
                "success": True,
                "sms_sid": message.sid,
                "phone": clean_phone['phone'],
                "amount": amount,
                "booking_ref": booking_ref,
                "message_sent": True
            }
            
        except Exception as e:
            print(f"❌ Failed to send payment SMS: {e}")
            return {"success": False, "error": f"SMS sending failed: {str(e)}"}
    
    def _send_booking_confirmation(self, phone: str, booking_ref: str, service: str, **kwargs) -> Dict[str, Any]:
        """Send booking confirmation SMS"""
        
        clean_phone = self._clean_phone_number(phone)
        if not clean_phone['valid']:
            return {"success": False, "error": clean_phone['error']}
        
        if not self.account_sid or not self.auth_token:
            print("⚠️ Twilio credentials not configured - simulating SMS")
            return {
                "success": True,
                "sms_sid": "simulated_confirmation_123",
                "phone": clean_phone['phone'],
                "simulated": True,
                "message": f"Booking confirmation would be sent to {clean_phone['phone']} for {booking_ref}"
            }
        
        try:
            client = Client(self.account_sid, self.auth_token)
            
            postcode = kwargs.get('postcode', '')
            customer_name = kwargs.get('customer_name', 'Customer')
            
            message_body = f"""✅ WasteKing Booking Confirmed

👤 Name: {customer_name}
📋 Reference: {booking_ref}
🚛 Service: {service.title()}
📍 Area: {postcode}

We'll contact you to arrange collection.
Questions? Reply HELP"""
            
            message = client.messages.create(
                body=message_body,
                from_=self.phone_number,
                to=clean_phone['phone']
            )
            
            print(f"✅ Confirmation SMS sent to {clean_phone['phone']}")
            
            return {
                "success": True,
                "sms_sid": message.sid,
                "phone": clean_phone['phone'],
                "booking_ref": booking_ref,
                "confirmation_sent": True
            }
            
        except Exception as e:
            print(f"❌ Failed to send confirmation SMS: {e}")
            return {"success": False, "error": f"SMS sending failed: {str(e)}"}
    
    def _clean_phone_number(self, phone: str) -> Dict[str, Any]:
        """Clean and validate UK phone number"""
        
        if not phone:
            return {"valid": False, "error": "No phone number provided"}
        
        # Remove spaces and non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)
        
        # Handle different UK phone formats
        if cleaned.startswith('07'):
            # 07xxxxxxxxx -> +447xxxxxxxxx
            cleaned = f"+44{cleaned[1:]}"
        elif cleaned.startswith('0'):
            # 0xxxxxxxxxx -> +44xxxxxxxxxx
            cleaned = f"+44{cleaned[1:]}"
        elif not cleaned.startswith('+44'):
            # Assume UK number if no country code
            cleaned = f"+44{cleaned}"
        
        # Validate UK mobile number format
        if not re.match(r'^\+447\d{9}$', cleaned):
            return {
                "valid": False, 
                "error": f"Invalid UK mobile number format: {phone}. Expected format: 07xxxxxxxxx"
            }
        
        return {"valid": True, "phone": cleaned}

# Test function for debugging
def test_sms_tool():
    """Test SMS tool functionality"""
    
    sms_tool = SMSTool(
        account_sid="test_sid",
        auth_token="test_token", 
        phone_number="+447123456789"
    )
    
    # Test payment SMS
    result = sms_tool._run(
        action="send_payment_sms",
        phone="07823656762",
        amount="85.00",
        booking_ref="WK123456",
        payment_link="https://pay.wasteking.co.uk/123456"
    )
    
    print("Payment SMS Test:", result)
    
    # Test confirmation SMS  
    result2 = sms_tool._run(
        action="send_booking_confirmation",
        phone="07823656762",
        booking_ref="WK123456",
        service="skip",
        postcode="LS14ED",
        customer_name="John Smith"
    )
    
    print("Confirmation SMS Test:", result2)

if __name__ == "__main__":
    test_sms_tool()
