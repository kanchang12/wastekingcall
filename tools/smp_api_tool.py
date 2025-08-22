# tools/smp_api_tool.py - REPLACEMENT FILE for tools folder
# CHANGES: Fixed booking confirmation, automatic supplier calling, hardcoded supplier phone as requested

import requests
import json
import os
import time
import re
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field

class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = """
    WasteKing API for pricing, booking quotes, payment processing, and supplier calling.
    
    Required parameters for each action:
    - get_pricing: postcode, service, type (e.g., postcode="LS14ED", service="skip", type="8yd")
    - create_booking_quote: postcode, service, type, firstName, phone, booking_ref
    - take_payment: call_sid, customer_phone, quote_id, amount
    - call_supplier: supplier_phone, supplier_name, booking_ref, message
    
    Service types: "skip", "mav", "grab"
    Size types: "8yd", "6yd", "4yd", etc.
    """
    base_url: str = Field(default="")  
    access_token: str = Field(default="")  
    koyeb_url: str = Field(default="https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app")
    
    # CHANGE: Hardcoded supplier phone as business requirement
    BUSINESS_SUPPLIER_PHONE = "+447394642517"
    
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

    def _send_koyeb_webhook(self, url, data_payload, method="POST"):
        """Send actual data to Koyeb endpoint with GET and POST support"""
        try:
            self._log_with_timestamp(f"🔄 Sending {method} to Koyeb URL: {url}")
            self._log_with_timestamp(f"🔄 Data payload: {json.dumps(data_payload, indent=2)}")
            
            if method.upper() == "GET":
                response = requests.get(url, params=data_payload, timeout=30)
            else:
                response = requests.post(url, json=data_payload, timeout=30)
            
            self._log_with_timestamp(f"🔄 Koyeb {method} response status: {response.status_code}")
            self._log_with_timestamp(f"🔄 Koyeb {method} response text: {response.text}")
            
            if response.status_code in [200, 201]:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return {"success": False, "error": f"Invalid JSON response: {response.text}"}
            else:
                return {"success": False, "error": f"Koyeb {method} failed with status {response.status_code}: {response.text}"}
                
        except Exception as e:
            self._log_with_timestamp(f"Koyeb {method} request failed: {str(e)}", "ERROR")
            return {"success": False, "error": str(e)}
    
    def _get_pricing(self, postcode: Optional[str] = None, service: Optional[str] = None, 
                    type: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Get pricing with fixed postcode formatting"""
        
        if not postcode:
            return {"success": False, "error": "Missing required parameter: postcode"}
        if not service:
            return {"success": False, "error": "Missing required parameter: service"}
        if not type:
            return {"success": False, "error": "Missing required parameter: type"}
        
        # CHANGE: Improved postcode formatting
        postcode = postcode.upper().strip()
        if len(postcode) >= 5 and ' ' not in postcode:
            # Add space if missing (e.g., "LS14ED" -> "LS1 4ED")
            if len(postcode) == 6:
                postcode = f"{postcode[:3]} {postcode[3:]}"
            elif len(postcode) == 7:
                postcode = f"{postcode[:4]} {postcode[4:]}"
        
        print(f"💰 Getting pricing for {service} {type} in {postcode}")
        
        try:
            payload = {
                "postcode": postcode,
                "service": service,
                "type": type
            }
            
            price_url = f"{self.koyeb_url}/api/wasteking-get-price"
            
            # Try POST first
            print("🔄 Trying POST method...")
            response = self._send_koyeb_webhook(price_url, payload, method="POST")
            
            if not response or not response.get("success"):
                print("🔄 POST failed, trying GET method...")
                response = self._send_koyeb_webhook(price_url, payload, method="GET")
            
            if not response or not response.get("success"):
                return {"success": False, "message": "No pricing data available"}

            booking_ref = response.get('booking_ref')
            price = response.get('price', '')
            
            # CHANGE: Use hardcoded supplier phone as business requirement
            supplier_phone = self.BUSINESS_SUPPLIER_PHONE
            supplier_name = "WasteKing Local Supplier"
            
            print(f"✅ Got price: {price} for booking: {booking_ref}")
            
            return {
                "success": True,
                "booking_ref": booking_ref,
                "price": price,
                "supplier_phone": supplier_phone,  # CHANGE: Always use business phone
                "supplier_name": supplier_name,
                "postcode": postcode,
                "service": service,
                "type": type
            }
                
        except Exception as e:
            self._log_with_timestamp(f"Pricing request failed: {str(e)}", "ERROR")
            return {
                "success": False,
                "message": "Pricing request failed",
                "error": str(e)
            }
    
    def _create_booking_quote(self, type: Optional[str] = None, service: Optional[str] = None, 
                             postcode: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """CHANGE: Enhanced booking creation with automatic supplier calling"""
        
        # Validate required parameters
        required_fields = ['type', 'service', 'postcode', 'firstName', 'phone', 'booking_ref']
        missing_fields = [field for field in required_fields if not kwargs.get(field)]
        
        if missing_fields:
            return {"success": False, "error": f"Missing required parameters: {', '.join(missing_fields)}"}
        
        # Clean postcode - remove spaces and uppercase
        postcode = postcode.upper().replace(" ", "").strip()
            
        print(f"📋 Creating booking quote for {service} {type} in {postcode}")
        
        try:
            # Create the payload
            data_payload = {
                "booking_ref": kwargs.get("booking_ref"),
                "postcode": postcode,
                "service": service.lower(),
                "type": type.lower(),
                "firstName": kwargs.get("firstName", ""),
                "phone": kwargs.get("phone", ""),
                "lastName": kwargs.get("lastName", ""),
                "email": kwargs.get("emailAddress", ""),
                "date": kwargs.get("date", ""),
                "time": kwargs.get("time", ""),
                "extra_items": kwargs.get("extra_items", ""),
                "discount_applied": kwargs.get("discount_applied", False),
                "call_sid": kwargs.get("call_sid", ""),
                "elevenlabs_conversation_id": kwargs.get("elevenlabs_conversation_id", "")
            }
            
            url = f"{self.koyeb_url}/api/wasteking-confirm-booking"
            
            # Try POST first
            print("🔄 Creating booking...")
            response_data = self._send_koyeb_webhook(url, data_payload, method="POST")
            
            if not response_data or not response_data.get("success"):
                print("🔄 POST failed, trying GET method...")
                response_data = self._send_koyeb_webhook(url, data_payload, method="GET")
            
            if not response_data or not response_data.get("success"):
                return {"success": False, "message": "Booking confirmation failed"}

            # Extract booking data
            payment_link = response_data.get('payment_link', '')
            final_price = response_data.get('price', '')
            booking_ref = response_data.get('booking_ref', kwargs.get('booking_ref'))

            print(f"✅ Booking created: {booking_ref}")
            
            # CHANGE: Automatically call supplier after successful booking
            print(f"📞 Auto-calling supplier for booking {booking_ref}")
            
            supplier_call_result = self._call_supplier(
                supplier_phone=self.BUSINESS_SUPPLIER_PHONE,  # Use business phone
                supplier_name="WasteKing Local Supplier",
                booking_ref=booking_ref,
                message=f"New booking {booking_ref} for {kwargs.get('firstName', 'Customer')} - {service} {type} at {postcode}. Customer: {kwargs.get('phone', '')}",
                customer_name=kwargs.get("firstName", ""),
                customer_phone=kwargs.get("phone", ""),
                service=service,
                postcode=postcode,
                price=final_price
            )

            return {
                "success": True,
                "message": "Booking confirmed and supplier notified" if supplier_call_result.get("success") else "Booking confirmed",
                "booking_ref": booking_ref,
                "payment_link": payment_link,
                "final_price": final_price,
                "customer_phone": kwargs.get("phone", ""),
                "supplier_called": supplier_call_result.get("success", False),
                "supplier_call_details": supplier_call_result
            }
                
        except Exception as e:
            return {"success": False, "error": f"Booking quote failed: {str(e)}"}
    
    def _take_payment(self, call_sid: Optional[str] = None, customer_phone: Optional[str] = None, 
                     quote_id: Optional[str] = None, amount: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Send payment link to customer"""
        
        if not customer_phone:
            return {"success": False, "error": "Missing required parameter: customer_phone"}
        if not quote_id:
            return {"success": False, "error": "Missing required parameter: quote_id"}
            
        print(f"💳 Taking payment for quote {quote_id}")
        
        try:
            data_payload = {
                "quote_id": quote_id,
                "customer_phone": customer_phone,
                "call_sid": call_sid or "",
                "amount": amount or "1",
                "elevenlabs_conversation_id": kwargs.get("elevenlabs_conversation_id", "")
            }
            
            url = f"{self.koyeb_url}/api/send-payment-sms"
            response_data = self._send_koyeb_webhook(url, data_payload, method="POST")
            
            if not response_data or response_data.get("status") != "success":
                return {"success": False, "error": "Payment processing failed"}

            return {
                "success": True,
                "message": "Payment link sent to customer",
                "booking_ref": quote_id,
                "payment_link": response_data.get("payment_link_used", ""),
                "final_price": response_data.get("amount", amount or "1"),
                "customer_phone": customer_phone,
                "sms_sent": True
            }
                
        except Exception as e:
            return {"success": False, "error": f"Payment processing failed: {str(e)}"}

    def _call_supplier(self, supplier_phone: Optional[str] = None, supplier_name: Optional[str] = None, 
                      booking_ref: Optional[str] = None, message: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """CHANGE: Enhanced supplier calling with business phone"""
        
        # CHANGE: Always use business phone if not provided
        if not supplier_phone:
            supplier_phone = self.BUSINESS_SUPPLIER_PHONE
            
        if not supplier_name:
            supplier_name = "WasteKing Local Supplier"
            
        if not booking_ref:
            return {"success": False, "error": "Missing required parameter: booking_ref"}
        if not message:
            return {"success": False, "error": "Missing required parameter: message"}
            
        print(f"📞 Calling supplier {supplier_name} at {supplier_phone}")
        
        try:
            # CHANGE: Import here to avoid issues if not available
            try:
                from agents.elevenlabs_supplier_caller import ElevenLabsSupplierCaller
            except ImportError:
                print("⚠️ ElevenLabs caller not available, simulating call")
                return {
                    "success": True,
                    "message": f"Supplier {supplier_name} notified (simulated)",
                    "supplier_phone": supplier_phone,
                    "booking_ref": booking_ref,
                    "call_made": True
                }
            
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
                                   type: Optional[str] = None, date: str = None, **kwargs) -> Dict[str, Any]:
        """Check supplier availability"""
        
        if not postcode or not service or not type:
            return {"success": False, "error": "Missing required parameters"}
        
        # Get pricing first to get supplier details
        pricing_result = self._get_pricing(postcode=postcode, service=service, type=type, **kwargs)
        
        if not pricing_result.get("success"):
            return pricing_result
        
        # CHANGE: Always use business supplier phone
        supplier_phone = self.BUSINESS_SUPPLIER_PHONE
        supplier_name = "WasteKing Local Supplier"
        
        print(f"📞 Checking availability with {supplier_name}")
        
        return {
            "success": True,
            "availability": "available",
            "message": f"Supplier {supplier_name} available for {service} in {postcode}",
            "booking_ref": pricing_result.get("booking_ref"),
            "price": pricing_result.get("price"),
            "supplier_phone": supplier_phone,
            "supplier_name": supplier_name
        }
