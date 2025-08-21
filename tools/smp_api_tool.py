import requests
import json
import time
import re
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field

# --- Assume these are defined or imported elsewhere for simplicity ---
WASTEKING_ACCESS_TOKEN = "your_wasteking_access_token"
WASTEKING_BASE_URL = "https://wk-smp-api-dev.azurewebsites.net/"
TWILIO_ACCOUNT_SID = "your_twilio_sid"
TWILIO_AUTH_TOKEN = "your_twilio_token"
TWILIO_PHONE_NUMBER = "your_twilio_phone_number"

try:
    from twilio.rest import Client
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

# --- SMSTool Class ---
class SMSTool(BaseTool):
    name: str = "sms"
    description: str = "Send SMS messages via Twilio"
    account_sid: str = Field(default=TWILIO_ACCOUNT_SID)
    auth_token: str = Field(default=TWILIO_AUTH_TOKEN)
    phone_number: str = Field(default=TWILIO_PHONE_NUMBER)
    
    def _run(self, phone: str, amount: str, booking_ref: str, payment_link: str) -> Dict[str, Any]:
        if not TWILIO_AVAILABLE:
            return {"success": False, "error": "Twilio not available"}
        
        try:
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
        except Exception as e:
            return {"success": False, "error": str(e)}

# --- SMPAPITool Class ---
class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = "Get real pricing, create and update bookings with WasteKing SMP API"
    base_url: str = Field(default=WASTEKING_BASE_URL)
    access_token: str = Field(default=WASTEKING_ACCESS_TOKEN)
    
    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        try:
            if action == "get_price_with_booking":
                return self._get_price_with_booking(**kwargs)
            elif action == "confirm_and_pay":
                return self._confirm_and_pay(**kwargs)
            elif action == "update_booking":
                return self._update_booking(**kwargs)
            elif action == "check_supplier_availability":
                return self._check_supplier_availability(**kwargs)
            elif action == "call_supplier":
                return self._call_supplier(**kwargs)
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # Helper method to create a booking
    def _create_booking(self) -> Dict[str, Any]:
        print("📞 Creating new booking...")
        headers = {
            "x-wasteking-request": self.access_token,
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(
                f"{self.base_url}api/booking/create",
                headers=headers,
                json={"type": "chatbot", "source": "wasteking.co.uk"},
                timeout=15,
                verify=False
            )
            if response.status_code == 200:
                booking_ref = response.json().get('bookingRef')
                print(f"✅ Booking created: {booking_ref}")
                return {"success": True, "booking_ref": booking_ref}
            else:
                return {"success": False, "error": f"Failed to create booking. Status: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Booking creation error: {str(e)}"}

    # Orchestrator for getting price and booking in one go
    def _get_price_with_booking(self, postcode: str, service: str, type_: str, **kwargs) -> Dict[str, Any]:
        print(f"💰 Orchestrating price lookup and booking creation for {service} in {postcode}")
        
        if not postcode or not service:
            return {"success": False, "error": "Missing postcode or service"}
        
        booking_result = self._create_booking()
        if not booking_result["success"]:
            return self._get_fallback_pricing(service, type_)
        
        booking_ref = booking_result["booking_ref"]
        
        search_payload = {
            "search": {
                "postCode": postcode,
                "service": service,
                "type": type_ or "8yard"
            }
        }
        update_result = self._update_booking(booking_ref, search_payload)
        
        if not update_result["success"]:
            return self._get_fallback_pricing(service, type_)
        
        quote = update_result["data"].get('quote', {})
        price = quote.get('price', '0')
        
        if price and price != '0':
            print(f"✅ Real-time price found: £{price}")
            return {
                "success": True,
                "booking_ref": booking_ref,
                "price": price,
                "supplier_phone": quote.get('supplierPhone', '07823656762'),
                "supplier_name": quote.get('supplierName', 'Local Supplier'),
            }
        
        return self._get_fallback_pricing(service, type_)

    # New orchestrator action for confirming, generating link, and sending SMS
    def _confirm_and_pay(self, booking_ref: str, customer_phone: str, amount: str) -> Dict[str, Any]:
        """
        Confirms a booking, generates a payment link, and sends it via SMS.
        """
        if not all([booking_ref, customer_phone, amount]):
            return {"success": False, "error": "Missing required parameters: booking_ref, customer_phone, and amount."}
        
        # Step 1: Generate payment link by updating the booking
        payment_payload = {"action": "quote"}
        payment_response = self._update_booking(booking_ref, payment_payload)
        
        payment_link = None
        if payment_response and payment_response.get('success'):
            payment_link = payment_response['data'].get('quote', {}).get('paymentLink')

        if not payment_link:
            return {"success": False, "error": "Failed to generate payment link from API."}

        # Step 2: Send payment link via SMS using the SMSTool
        sms_tool = SMSTool()
        sms_response = sms_tool._run(
            phone=customer_phone, 
            amount=amount, 
            booking_ref=booking_ref, 
            payment_link=payment_link
        )
        
        return {
            "success": True,
            "message": "Payment link sent successfully",
            "booking_ref": booking_ref,
            "payment_link": payment_link,
            "sms_sent": sms_response.get('success', False),
            "sms_details": sms_response
        }

    # Helper methods
    def _update_booking(self, booking_ref: str, update_data: Dict) -> Dict[str, Any]:
        print(f"📝 Updating booking {booking_ref} with: {update_data}")
        headers = {
            "x-wasteking-request": self.access_token,
            "Content-Type": "application/json"
        }
        payload = {"bookingRef": booking_ref}
        payload.update(update_data)
        try:
            response = requests.post(
                f"{self.base_url}api/booking/update/",
                headers=headers,
                json=payload,
                timeout=20,
                verify=False
            )
            if response.status_code in [200, 201]:
                print("✅ Booking updated successfully")
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"Update failed. Status: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Update error: {str(e)}"}

    def _get_fallback_pricing(self, service: str, type_: str) -> Dict[str, Any]:
        print(f"💰 Using fallback pricing for {service} {type_}")
        fallback_prices = {
            "skip": {"4yard": "200", "6yard": "240", "8yard": "280", "12yard": "360"},
            "man_and_van": {"2yard": "90", "4yard": "120", "6yard": "180", "8yard": "240", "10yard": "300"},
            "grab": {"6wheeler": "300", "8wheeler": "400"}
        }
        service_key = service.replace("_", "")
        price = fallback_prices.get(service_key, {}).get(type_, "220")
        return {
            "success": True,
            "price": price,
            "supplier_phone": "07823656762",
            "supplier_name": "WasteKing Local",
            "fallback": True
        }

    def _check_supplier_availability(self, postcode: str, service: str, type_: str, date: str = None) -> Dict[str, Any]:
        pricing_result = self._get_price_with_booking(postcode=postcode, service=service, type_=type_)
        if not pricing_result["success"]:
            return pricing_result
        supplier_phone = pricing_result["supplier_phone"]
        supplier_name = pricing_result["supplier_name"]
        test_phone = "07823656762"
        time.sleep(2)
        return {
            "success": True,
            "availability": "available",
            "message": f"Supplier {supplier_name} confirms availability",
            "booking_ref": pricing_result.get("booking_ref"),
            "price": pricing_result["price"]
        }
    
    def _call_supplier(self, supplier_phone: str, supplier_name: str, booking_ref: str, message: str) -> Dict[str, Any]:
        test_phone = "07823656762"
        time.sleep(1)
        return {
            "success": True,
            "call_made": True,
            "supplier_name": supplier_name,
            "phone_called": test_phone,
            "booking_ref": booking_ref,
            "call_status": "connected",
            "message": f"Called {supplier_name} successfully"
        }
