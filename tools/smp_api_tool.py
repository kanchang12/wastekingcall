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
    
    def _get_pricing(self, postcode: str = "", service: str = "", type_: str = "", **kwargs) -> Dict[str, Any]:
        """Get pricing from your working Flask API"""
        print(f"💰 Getting pricing for {service} {type_} in {postcode}")
        
        if not postcode or not service:
            print("❌ Missing required parameters")
            return {"success": False, "error": "Missing postcode or service"}
        
        try:
            # Call your actual working Flask API endpoint
            api_url = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app/api/wasteking-get-price"
            
            payload = {
                "postcode": postcode,
                "service": service,
                "type": type_ or "8yard"
            }
            
            response = requests.post(
                api_url,
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get("success"):
                    print(f"✅ Real pricing from Flask API: {data.get('price')}")
                    return {
                        "success": True,
                        "booking_ref": data.get("booking_ref"),
                        "price": data.get("price"),
                        "supplier_phone": data.get("real_supplier_phone", "07823656762"),
                        "supplier_name": data.get("supplier_name", "Local Supplier"),
                        "postcode": postcode,
                        "service_type": service,
                        "type": type_
                    }
                else:
                    print("❌ Flask API returned failure, using fallback")
                    return self._get_fallback_pricing(service, type_)
            else:
                print(f"❌ Flask API error: {response.status_code}")
                return {"success": False, "error": f"API error: {response.status_code}"}
                
        except Exception as e:
            print(f"❌ Flask API call failed: {str(e)}")
            return {"success": False, "error": f"API call failed: {str(e)}"}

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
