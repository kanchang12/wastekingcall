def _get_pricing(self, postcode: Optional[str] = None, service: Optional[str] = None, 
                    type: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Get pricing - needs firstName and phone for WasteKing"""
        
        # Validate required parameters
        if not postcode:
            return {"success": False, "error": "Missing required parameter: postcode"}
        if not service:
            return {"success": False, "error": "Missing required parameter: service"}
        if not type:
            return {"success": False, "error": "Missing required parameter: type"}
        if not kwargs.get('firstName'):
            return {"success": False, "error": "Missing required parameter: firstName"}
        if not kwargs.get('phone'):
            return {"success": False, "error": "Missing required parameter: phone"}
            
        print(f"💰 Getting pricing for {service} {type} in {postcode}")
        
        try:
            # Create booking
            booking_ref = self._create_wasteking_booking()
            if not booking_ref:
                return {"success": False, "message": "Failed to create booking"}

            # Search payload - needs firstName and phone
            search_payload = {
                "postCode": postcode,
                "service": service,
                "type": type,
                "firstName": kwargs.get('firstName'),
                "phone": kwargs.get('phone')
            }
            
            # Get pricing
            response_data = self._update_wasteking_booking(booking_ref, search_payload)
            if not response_data:
                return {"success": False, "message": "No pricing data"}

            quote_data = response_data.get('quote', {})
            price = quote_data.get('price', '0')
            supplier_phone = quote_data.get('supplierPhone', "+447823656907")
            supplier_name = quote_data.get('supplierName', "Default Supplier")import requests
import json
import os
import time
import re
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field
from agents.elevenlabs_supplier_caller import ElevenLabsSupplierCaller

class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = """
    WasteKing API for pricing, booking quotes, payment processing, and supplier calling.
    
    Required parameters for each action:
    - get_pricing: postcode, service, type (e.g., postcode="[POSTCODE]", service="skip-hire", type="8yd")
    - create_booking_quote: postcode, service, type, firstName, phone
    - take_payment: call_sid, customer_phone, quote_id, amount
    - call_supplier: supplier_phone, supplier_name, booking_ref, message
    """
    base_url: str = Field(default=os.getenv('WASTEKING_BASE_URL', "https://wk-smp-api-dev.azurewebsites.net/"))
    access_token: str = Field(default=os.getenv('WASTEKING_ACCESS_TOKEN', 'fallback_token'))
    
    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        try:
            print(f"🔧 SMP API Tool called with action: {action}")
            print(f"🔧 Parameters: {kwargs}")
            
            if action == "get_pricing":
                return self._get_pricing(**kwargs)
            elif action == "create_booking_quote":
                return self._create_booking_quote(**kwargs)
            elif action == "take_payment":
                return self._take_payment(**kwargs)
            elif action == "call_supplier":
                return self._call_supplier(**kwargs)
            elif action == "check_supplier_availability":
                return self._check_supplier_availability(**kwargs)
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            print(f"❌ SMP API Error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _log_with_timestamp(self, message, level="INFO"):
        """Enhanced logging with timestamps"""
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] [{level}] {message}")

    def _log_error(self, message, error=None):
        """Log errors"""
        if error:
            self._log_with_timestamp(f"ERROR: {message}: {error}", "ERROR")
        else:
            self._log_with_timestamp(f"ERROR: {message}", "ERROR")

    def _create_wasteking_booking(self):
        """Create booking reference - EXACT copy from your Flask code"""
        try:
            headers = {
                "x-wasteking-request": self.access_token,
                "Content-Type": "application/json"
            }
            
            create_url = f"{self.base_url}api/booking/create"
            
            response = requests.post(
                create_url,
                headers=headers,
                json={"type": "chatbot", "source": "wasteking.co.uk"},
                timeout=15,
                verify=False
            )
            
            if response.status_code == 200:
                response_json = response.json()
                booking_ref = response_json.get('bookingRef')
                if booking_ref:
                    self._log_with_timestamp(f"✅ Created booking: {booking_ref}")
                    time.sleep(1)
                    return booking_ref
            
            self._log_with_timestamp(f"❌ Failed to create booking: {response.status_code}")
            return None
                
        except Exception as e:
            self._log_error("Failed to create booking", e)
            return None

    def _update_wasteking_booking(self, booking_ref, update_data):
        """Update booking - EXACT copy from your Flask code"""
        try:
            headers = {
                "x-wasteking-request": self.access_token,
                "Content-Type": "application/json"
            }
            
            payload = {"bookingRef": booking_ref}
            payload.update(update_data)
            
            self._log_with_timestamp(f"🔄 Updating booking {booking_ref} with payload: {json.dumps(payload, indent=2)}")
            
            update_url = f"{self.base_url}api/booking/update/"
            self._log_with_timestamp(f"🔄 Update URL: {update_url}")
            
            response = requests.post(
                update_url,
                headers=headers,
                json=payload,
                timeout=20,
                verify=False
            )
            
            self._log_with_timestamp(f"🔄 Update response status: {response.status_code}")
            self._log_with_timestamp(f"🔄 Update response text: {response.text}")
            
            if response.status_code in [200, 201]:
                self._log_with_timestamp(f"✅ Updated booking {booking_ref}")
                return response.json()
            else:
                self._log_with_timestamp(f"❌ Failed to update booking: {response.status_code}")
                return None
                
        except Exception as e:
            self._log_error(f"Failed to update booking {booking_ref}", e)
            return None
    
    def _get_pricing(self, postcode: Optional[str] = None, service: Optional[str] = None, 
                    type: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Get pricing - EXACT copy from your Flask wasteking_marketplace function"""
        
        # Validate required parameters
        if not postcode:
            return {"success": False, "error": "Missing required parameter: postcode"}
        if not service:
            return {"success": False, "error": "Missing required parameter: service"}
        if not type:
            return {"success": False, "error": "Missing required parameter: type"}
            
        print(f"💰 Getting pricing for {service} {type} in {postcode}")
        
        try:
            # Create booking - EXACT same as your Flask code
            booking_ref = self._create_wasteking_booking()
            if not booking_ref:
                return {"success": False, "message": "Failed to create booking"}

            # Search payload - EXACT same format as your Flask code
            search_payload = {
                "search": {
                    "postCode": postcode,
                    "service": service,
                    "type": type
                }
            }
            
            # Get pricing - EXACT same as your Flask code
            response_data = self._update_wasteking_booking(booking_ref, search_payload)
            if not response_data:
                return {"success": False, "message": "No pricing data"}

            quote_data = response_data.get('quote', {})
            price = quote_data.get('price', '0')
            supplier_phone = quote_data.get('supplierPhone', "+447823656907")
            supplier_name = quote_data.get('supplierName', "Default Supplier")
            
            # Return format - EXACT same as your Flask code
            return {
                "success": True,
                "booking_ref": booking_ref,
                "price": price,
                "real_supplier_phone": supplier_phone,
                "supplier_name": supplier_name,
                "postcode": postcode,
                "service": service,
                "type": type
            }
                
        except Exception as e:
            self._log_error("Marketplace request failed", e)
            return {
                "success": False,
                "message": "Marketplace request failed",
                "error": str(e)
            }
    
    def _create_booking_quote(self, type: Optional[str] = None, service: Optional[str] = None, 
                             postcode: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Create booking quote with payment link"""
        
        # Validate required parameters
        if not type:
            return {"success": False, "error": "Missing required parameter: type"}
        if not service:
            return {"success": False, "error": "Missing required parameter: service"}
        if not postcode:
            return {"success": False, "error": "Missing required parameter: postcode"}
            
        print(f"📋 Creating booking quote for {service} {type} in {postcode}")
        
        try:
            # Get booking ref from kwargs or create new one
            booking_ref = kwargs.get('booking_ref')
            if not booking_ref:
                booking_ref = self._create_wasteking_booking()
                if not booking_ref:
                    return {"success": False, "message": "Failed to create booking"}

            # Payment payload structure as shown in screenshot
            payment_payload = {
                "bookingRef": booking_ref,
                "type": type,
                "service": service,
                "postcode": postcode,
                "firstName": kwargs.get("firstName", ""),
                "phone": kwargs.get("phone", ""),
                "lastName": kwargs.get("lastName", ""),
                "emailAddress": kwargs.get("emailAddress", ""),
                "time": kwargs.get("time", ""),
                "date": kwargs.get("date", ""),
                "extra_items": kwargs.get("extra_items", ""),
                "discount_applied": kwargs.get("discount_applied", False),
                "call_sid": kwargs.get("call_sid", ""),
                "elevenlabs_conversation_id": kwargs.get("elevenlabs_conversation_id", "")
            }
            
            # Remove empty fields
            payment_payload = {k: v for k, v in payment_payload.items() if v}
            
            self._log_with_timestamp(f"📋 Payment payload: {json.dumps(payment_payload, indent=2)}")
            
            # Call WasteKing booking update
            payment_response = self._update_wasteking_booking(booking_ref, payment_payload)
            
            if payment_response and payment_response.get('quote', {}).get('paymentLink'):
                payment_link = payment_response['quote']['paymentLink']
                final_price = payment_response['quote'].get('price', '0')
            else:
                return {"success": False, "message": "No payment link available"}

            return {
                "success": True,
                "message": "Booking confirmed",
                "booking_ref": booking_ref,
                "payment_link": payment_link,
                "final_price": final_price,
                "customer_phone": kwargs.get("phone", "")
            }
                
        except Exception as e:
            return {"success": False, "error": f"Booking quote failed: {str(e)}"}
    
    def _take_payment(self, call_sid: Optional[str] = None, customer_phone: Optional[str] = None, 
                     quote_id: Optional[str] = None, amount: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Send payment link to customer"""
        
        # Validate required parameters
        if not customer_phone:
            return {"success": False, "error": "Missing required parameter: customer_phone"}
        if not quote_id:
            return {"success": False, "error": "Missing required parameter: quote_id"}
            
        print(f"💳 Taking payment for quote {quote_id}")
        
        try:
            # Generate payment link from WasteKing
            payment_payload = {"action": "quote"}
            payment_response = self._update_wasteking_booking(quote_id, payment_payload)
            
            if payment_response and payment_response.get('quote', {}).get('paymentLink'):
                payment_link = payment_response['quote']['paymentLink']
                final_price = payment_response['quote'].get('price', amount or '50')
            else:
                return {"success": False, "error": "No payment link available"}

            # Send SMS using your existing function
            sms_response = self._send_payment_sms(quote_id, customer_phone, payment_link, str(final_price))
            
            return {
                "success": True,
                "message": "Payment link sent to customer",
                "booking_ref": quote_id,
                "payment_link": payment_link,
                "final_price": final_price,
                "customer_phone": customer_phone,
                "sms_sent": sms_response.get('success', False)
            }
                
        except Exception as e:
            return {"success": False, "error": f"Payment processing failed: {str(e)}"}

    def _send_payment_sms(self, booking_ref: str, phone: str, payment_link: str, amount: str):
        """Send payment SMS via Twilio - EXACT copy from your Flask code"""
        try:
            from twilio.rest import Client
            
            # Clean and format phone number
            if phone.startswith('0'):
                phone = f"+44{phone[1:]}"
            elif phone.startswith('44'):
                phone = f"+{phone}"
            elif not phone.startswith('+'):
                phone = f"+44{phone}"
                
            phone_pattern = r'^\+44\d{9,10}$'
            if not re.match(phone_pattern, phone):
                self._log_with_timestamp(f"❌ Invalid UK phone number format: {phone}")
                return {"success": False, "message": "Invalid UK phone number format"}
            
            # Create SMS message with the final adjusted amount
            TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
            TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
            TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')
            
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            message_body = f"""Waste King Payment
Amount: £{amount}
Reference: {booking_ref}

Pay securely: {payment_link}

After payment, you'll get confirmation.
Thank you!"""
            
            # Send SMS
            message = client.messages.create(
                body=message_body,
                from_=TWILIO_PHONE_NUMBER,
                to=phone
            )
            
            self._log_with_timestamp(f"✅ SMS sent to {phone} for booking {booking_ref} with final amount £{amount}. SID: {message.sid}")
            
            return {"success": True, "message": "SMS sent successfully", "sms_sid": message.sid}
            
        except Exception as e:
            self._log_error("Failed to send payment SMS", e)
            return {"success": False, "message": str(e)}
    
    def _call_supplier(self, supplier_phone: Optional[str] = None, supplier_name: Optional[str] = None, 
                      booking_ref: Optional[str] = None, message: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Makes actual call to supplier using ElevenLabs"""
        
        # Validate required parameters
        if not supplier_phone:
            return {"success": False, "error": "Missing required parameter: supplier_phone"}
        if not supplier_name:
            return {"success": False, "error": "Missing required parameter: supplier_name"}
        if not booking_ref:
            return {"success": False, "error": "Missing required parameter: booking_ref"}
        if not message:
            return {"success": False, "error": "Missing required parameter: message"}
            
        print(f"📞 Calling supplier {supplier_phone}")
        
        try:
            caller = ElevenLabsSupplierCaller(
                elevenlabs_api_key=os.getenv('ELEVENLABS_API_KEY'),
                agent_id=os.getenv('ELEVENLABS_AGENT_ID'),
                agent_phone_number_id=os.getenv('ELEVENLABS_AGENT_PHONE_NUMBER_ID')
            )
            
            # Create booking details for the call
            booking_details = {
                "booking_ref": booking_ref,
                "supplier_name": supplier_name,
                "message": message,
                "customer_name": kwargs.get("customer_name", ""),
                "customer_contact": kwargs.get("customer_phone", "")
            }
            
            # Create SMP response format for the caller
            smp_response = {
                "success": True, 
                "supplier_phone": supplier_phone,
                "service_type": kwargs.get("service", ""),
                "postcode": kwargs.get("postcode", ""),
                "price": kwargs.get("price", ""),
                "booking_ref": booking_ref
            }
            
            result = caller.call_supplier_from_smp_response(smp_response, booking_details)
            
            return {
                "success": result.get("success", False),
                "call_made": True,
                "supplier_name": supplier_name,
                "phone_called": supplier_phone,
                "booking_ref": booking_ref,
                "conversation_id": result.get("conversation_id"),
                "call_sid": result.get("call_sid"),
                "message": f"Called {supplier_name} successfully" if result.get("success") else f"Call failed: {result.get('error', 'Unknown error')}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Call failed: {str(e)}",
                "call_made": False
            }
    
    def _check_supplier_availability(self, postcode: Optional[str] = None, service: Optional[str] = None, 
                                   type_: Optional[str] = None, date: str = None, **kwargs) -> Dict[str, Any]:
        """Check supplier availability and call them if needed"""
        
        # Validate required parameters
        if not postcode:
            return {"success": False, "error": "Missing required parameter: postcode"}
        if not service:
            return {"success": False, "error": "Missing required parameter: service"}
        if not type_:
            return {"success": False, "error": "Missing required parameter: type_"}
            
        # First get pricing to get supplier details
        pricing_result = self._get_pricing(postcode=postcode, service=service, type=type_, **kwargs)
        
        if not pricing_result.get("success"):
            return pricing_result
        
        supplier_phone = pricing_result.get("supplier_phone")
        supplier_name = pricing_result.get("supplier_name")
        
        if not supplier_phone:
            return {"success": False, "error": "No supplier phone number available"}
        
        # Call supplier to check availability
        try:
            caller = ElevenLabsSupplierCaller(
                elevenlabs_api_key=os.getenv('ELEVENLABS_API_KEY'),
                agent_id=os.getenv('ELEVENLABS_AGENT_ID'),
                agent_phone_number_id=os.getenv('ELEVENLABS_AGENT_PHONE_NUMBER_ID')
            )
            
            call_result = caller.call_supplier_for_availability(
                supplier_phone="07823656907",
                service_type=service,
                postcode=postcode,
                date=date or "ASAP"
            )
            
            return {
                "success": call_result.get("success", False),
                "availability": "checking" if call_result.get("success") else "unavailable",
                "message": f"Called {supplier_name} to check availability",
                "booking_ref": pricing_result.get("booking_ref"),
                "price": pricing_result.get("price"),
                "supplier_phone": supplier_phone,
                "supplier_name": supplier_name,
                "conversation_id": call_result.get("conversation_id"),
                "call_sid": call_result.get("call_sid")
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Availability check failed: {str(e)}",
                "booking_ref": pricing_result.get("booking_ref"),
                "price": pricing_result.get("price"),
                "supplier_phone": supplier_phone
            }
