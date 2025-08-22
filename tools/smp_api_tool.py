import requests
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
    - get_pricing: postcode, service, type (e.g., postcode="LS14ED", service="skip-hire", type="8yd")
    - create_booking_quote: postcode, service, type, firstName, phone
    - take_payment: call_sid, customer_phone, quote_id, amount
    - call_supplier: supplier_phone, supplier_name, booking_ref, message
    """
    base_url: str = Field(default=os.getenv('WASTEKING_BASE_URL', "https://wk-smp-api.azurewebsites.net/"))
    access_token: str = Field(default=os.getenv('WASTEKING_ACCESS_TOKEN', 'your_access_token_here'))
    
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
    
    def _create_wasteking_booking(self):
        """Create booking reference with WasteKing"""
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
                    print(f"✅ Created booking: {booking_ref}")
                    time.sleep(1)
                    return booking_ref
            
            print(f"❌ Failed to create booking: {response.status_code}")
            return None
                
        except Exception as e:
            print(f"❌ Failed to create booking: {str(e)}")
            return None

    def _update_wasteking_booking(self, booking_ref, update_data):
        """Update booking with WasteKing"""
        try:
            headers = {
                "x-wasteking-request": self.access_token,
                "Content-Type": "application/json"
            }
            
            payload = {"bookingRef": booking_ref}
            payload.update(update_data)
            
            update_url = f"{self.base_url}api/booking/update/"
            response = requests.post(
                update_url,
                headers=headers,
                json=payload,
                timeout=20,
                verify=False
            )
            
            if response.status_code in [200, 201]:
                print(f"✅ Updated booking {booking_ref}")
                return response.json()
            else:
                print(f"❌ Failed to update booking: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Failed to update booking {booking_ref}: {str(e)}")
            return None
    
    def _get_pricing(self, postcode: Optional[str] = None, service: Optional[str] = None, 
                    type: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Get pricing using WasteKing API flow"""
        
        # Validate required parameters
        if not postcode:
            return {"success": False, "error": "Missing required parameter: postcode"}
        if not service:
            return {"success": False, "error": "Missing required parameter: service"}
        if not type:
            return {"success": False, "error": "Missing required parameter: type"}
            
        print(f"💰 Getting pricing for {service} {type} in {postcode}")
        
        try:
            # Step 1: Create booking
            booking_ref = self._create_wasteking_booking()
            if not booking_ref:
                return {"success": False, "error": "Failed to create booking"}

            # Step 2: Search payload for WasteKing
            search_payload = {
                "search": {
                    "postCode": postcode,
                    "service": service,
                    "type": type
                }
            }
            
            # Step 3: Get pricing
            response_data = self._update_wasteking_booking(booking_ref, search_payload)
            if not response_data:
                return {"success": False, "error": "No pricing data"}

            quote_data = response_data.get('quote', {})
            price = quote_data.get('price', '0')
            supplier_phone = quote_data.get('supplierPhone', "+447823656907")
            supplier_name = quote_data.get('supplierName', "Default Supplier")
            
            return {
                "success": True,
                "booking_ref": booking_ref,
                "price": price,
                "supplier_phone": supplier_phone,
                "supplier_name": supplier_name,
                "postcode": postcode,
                "service": service,
                "type": type
            }
                
        except Exception as e:
            return {"success": False, "error": f"Pricing request failed: {str(e)}"}
    
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
            # Step 1: Create or get booking
            booking_ref = kwargs.get('booking_ref')
            if not booking_ref:
                booking_ref = self._create_wasteking_booking()
                if not booking_ref:
                    return {"success": False, "error": "Failed to create booking"}

            # Step 2: Update with customer details
            customer_data = {
                "firstName": kwargs.get("firstName", ""),
                "lastName": kwargs.get("lastName", ""),
                "phone": kwargs.get("phone", ""),
                "emailAddress": kwargs.get("emailAddress", ""),
                "postcode": postcode,
                "service": service,
                "type": type
            }
            
            # Update booking with customer data
            response_data = self._update_wasteking_booking(booking_ref, customer_data)
            if not response_data:
                return {"success": False, "error": "Failed to update booking"}

            # Step 3: Generate payment link
            payment_payload = {"action": "quote"}
            payment_response = self._update_wasteking_booking(booking_ref, payment_payload)
            
            if payment_response and payment_response.get('quote', {}).get('paymentLink'):
                payment_link = payment_response['quote']['paymentLink']
                price = payment_response['quote'].get('price', '0')
            else:
                return {"success": False, "error": "No payment link available"}

            return {
                "success": True,
                "booking_ref": booking_ref,
                "payment_link": payment_link,
                "price": price,
                "message": "Booking quote created successfully"
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
        """Send payment SMS via Twilio"""
        try:
            from twilio.rest import Client
            
            # Clean phone number
            if phone.startswith('0'):
                phone = f"+44{phone[1:]}"
            elif phone.startswith('44'):
                phone = f"+{phone}"
            elif not phone.startswith('+'):
                phone = f"+44{phone}"
                
            phone_pattern = r'^\+44\d{9,10}$'
            if not re.match(phone_pattern, phone):
                return {"success": False, "message": "Invalid UK phone number format"}
            
            # Get Twilio credentials
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
            
            message = client.messages.create(
                body=message_body,
                from_=TWILIO_PHONE_NUMBER,
                to=phone
            )
            
            print(f"✅ SMS sent to {phone} for booking {booking_ref}. SID: {message.sid}")
            return {"success": True, "message": "SMS sent successfully", "sms_sid": message.sid}
            
        except Exception as e:
            print(f"❌ Failed to send SMS: {str(e)}")
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
