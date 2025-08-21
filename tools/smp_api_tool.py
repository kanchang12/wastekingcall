import requests
import json
import os
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field
from agents.elevenlabs_supplier_caller import ElevenLabsSupplierCaller

class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = "WasteKing API for pricing, booking quotes, payment processing, and supplier calling"
    base_url: str = Field(default="https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app/api/")
    
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
    
    def _get_pricing(self, postcode: str, service: str, type: str, **kwargs) -> Dict[str, Any]:
        """Get pricing from wasteking-get-price endpoint"""
        print(f"💰 Getting pricing for {service} {type} in {postcode}")
        
        if not all([postcode, service, type]):
            return {"success": False, "error": "Missing required fields: postcode, service, type"}
        
        try:
            payload = {
                "postcode": postcode,
                "service": service,
                "type": type,
                # Optional fields
                "address1": kwargs.get("address1", ""),
                "imageUrl": kwargs.get("imageUrl", ""),
                "firstName": kwargs.get("firstName", ""),
                "address2": kwargs.get("address2", ""),
                "lastName": kwargs.get("lastName", ""),
                "supplement_code": kwargs.get("supplement_code", ""),
                "elevenlabs_conversation_id": kwargs.get("elevenlabs_conversation_id", ""),
                "call_sid": kwargs.get("call_sid", ""),
                "addressPostcode": kwargs.get("addressPostcode", ""),
                "addressCity": kwargs.get("addressCity", ""),
                "collection": kwargs.get("collection", ""),
                "placement": kwargs.get("placement", ""),
                "notes": kwargs.get("notes", ""),
                "agent_name": kwargs.get("agent_name", ""),
                "date": kwargs.get("date", ""),
                "supplement_qty": kwargs.get("supplement_qty", ""),
                "phone": kwargs.get("phone", ""),
                "time": kwargs.get("time", ""),
                "addressCounty": kwargs.get("addressCounty", ""),
                "emailAddress": kwargs.get("emailAddress", "")
            }
            
            response = requests.post(
                f"{self.base_url}wasteking-get-price",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Pricing response: {data}")
                return data
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": f"Pricing request failed: {str(e)}"}
    
    def _create_booking_quote(self, type: str, service: str, postcode: str, **kwargs) -> Dict[str, Any]:
        """Create booking quote with payment link"""
        print(f"📋 Creating booking quote for {service} {type} in {postcode}")
        
        if not all([type, service, postcode]):
            return {"success": False, "error": "Missing required fields: type, service, postcode"}
        
        try:
            payload = {
                "type": type,
                "service": service,
                "postcode": postcode,
                # Optional fields
                "firstName": kwargs.get("firstName", ""),
                "time": kwargs.get("time", ""),
                "phone": kwargs.get("phone", ""),
                "lastName": kwargs.get("lastName", ""),
                "elevenlabs_conversation_id": kwargs.get("elevenlabs_conversation_id", ""),
                "discount_applied": kwargs.get("discount_applied", False),
                "call_sid": kwargs.get("call_sid", ""),
                "emailAddress": kwargs.get("emailAddress", ""),
                "extra_items": kwargs.get("extra_items", ""),
                "date": kwargs.get("date", "")
            }
            
            response = requests.post(
                f"{self.base_url}wasteking-confirm-booking",
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Booking quote created: {data}")
                return data
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": f"Booking quote failed: {str(e)}"}
    
    def _take_payment(self, call_sid: str, customer_phone: str, quote_id: str, amount: str, **kwargs) -> Dict[str, Any]:
        """Send payment link to customer"""
        print(f"💳 Taking payment for quote {quote_id}, amount £{amount}")
        
        if not all([call_sid, customer_phone, quote_id, amount]):
            return {"success": False, "error": "Missing required fields: call_sid, customer_phone, quote_id, amount"}
        
        try:
            payload = {
                "call_sid": call_sid,
                "customer_phone": customer_phone,
                "quote_id": quote_id,
                "amount": amount,
                "elevenlabs_conversation_id": kwargs.get("elevenlabs_conversation_id", "")
            }
            
            response = requests.post(
                f"{self.base_url}wasteking-confirm-booking",
                json=payload,
                timeout=20
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Payment link sent: {data}")
                return data
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": f"Payment processing failed: {str(e)}"}
    
    def _call_supplier(self, supplier_phone: str, supplier_name: str, booking_ref: str, message: str, **kwargs) -> Dict[str, Any]:
        """Makes actual call to supplier using ElevenLabs"""
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
    
    def _check_supplier_availability(self, postcode: str, service: str, type_: str, date: str = None, **kwargs) -> Dict[str, Any]:
        """Check supplier availability and call them if needed"""
        # First get pricing to get supplier details
        pricing_result = self._get_pricing(postcode=postcode, service=service, type_=type_, **kwargs)
        
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
