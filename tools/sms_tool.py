import requests
import json
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field

class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = "WasteKing API for pricing, booking quotes, and payment processing"
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
