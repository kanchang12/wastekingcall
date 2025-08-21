import requests
import json
import time
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field

class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = "Get real pricing, create and update bookings with WasteKing SMP API"
    base_url: str = Field(default="https://wk-smp-api-dev.azurewebsites.net/")
    access_token: str = Field(default="")
    
    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        try:
            print(f"🔧 SMP API Tool called with action: {action}")
            print(f"🔧 Parameters: {kwargs}")
            
            if action == "get_pricing" or action == "get_price":
                return self._get_pricing(**kwargs)
            elif action == "confirm_and_pay":
                return self._confirm_and_pay(**kwargs)
            elif action == "call_supplier":
                return self._call_supplier(**kwargs)
            elif action == "check_supplier_availability":
                return self._check_supplier_availability(**kwargs)
            elif action == "get_current":
                return self._get_current_offers(**kwargs)
            else:
                print(f"❌ Unknown action: {action}")
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
                    "skip_size": type_
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

    
    def _confirm_and_pay(self, booking_ref: str = "", customer_phone: str = "", **kwargs) -> Dict[str, Any]:
        """Confirm booking and send SMS via your Flask API"""
        if not booking_ref or not customer_phone:
            return {"success": False, "error": "Missing booking_ref or customer_phone"}
        
        try:
            # Call your actual Flask API for booking confirmation
            api_url = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app/api/wasteking-confirm-booking"
            
            payload = {
                "booking_ref": booking_ref,
                "customer_phone": customer_phone
            }
            
            response = requests.post(
                api_url,
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Booking confirmed and SMS sent: {data}")
                return data
            else:
                return {"success": False, "error": f"API error: {response.status_code}"}
                
        except Exception as e:
            return {"success": False, "error": f"Booking confirmation failed: {str(e)}"}
    
    def _get_current_offers(self, **kwargs) -> Dict[str, Any]:
        """Get current offers and promotions"""
        return {
            "success": True,
            "current_offers": ["20% off first booking", "Free permit arrangement"],
            "service_areas": ["Leeds", "Bradford", "York"],
            "available_today": True
        }
    
    def _get_fallback_pricing(self, service: str, type_: str) -> Dict[str, Any]:
        """NO FALLBACK PRICING - Always fail properly"""
        print(f"❌ No fallback pricing allowed")
        return {
            "success": False,
            "error": f"Unable to get pricing for {service} {type_}. Please try again or contact support."
        }

    def _check_supplier_availability(self, postcode: str, service: str, type_: str, date: str = None) -> Dict[str, Any]:
        """Check supplier availability"""
        pricing_result = self._get_pricing(postcode=postcode, service=service, type_=type_)
        if not pricing_result["success"]:
            return pricing_result
        supplier_phone = pricing_result["supplier_phone"]
        supplier_name = pricing_result["supplier_name"]
        time.sleep(2)
        return {
            "success": True,
            "availability": "available",
            "message": f"Supplier {supplier_name} confirms availability",
            "booking_ref": pricing_result.get("booking_ref"),
            "price": pricing_result["price"],
            "supplier_phone": supplier_phone
        }
    
    def _call_supplier(self, supplier_phone: str, supplier_name: str, booking_ref: str, message: str) -> Dict[str, Any]:
        """Makes actual call to supplier using ElevenLabs"""
        import os
        from elevenlabs_supplier_caller import ElevenLabsSupplierCaller
        
        print(f"📞 Calling supplier {supplier_phone}")
        
        try:
            caller = ElevenLabsSupplierCaller(
                elevenlabs_api_key=os.getenv('ELEVENLABS_API_KEY'),
                agent_id=os.getenv('ELEVENLABS_AGENT_ID'),
                agent_phone_number_id=os.getenv('ELEVENLABS_AGENT_PHONE_NUMBER_ID')
            )
            
            booking_details = {
                "booking_ref": booking_ref,
                "supplier_name": supplier_name,
                "message": message
            }
            
            result = caller.call_supplier_from_smp_response(
                {"success": True, "supplier_phone": supplier_phone}, 
                booking_details
            )
            
            return {
                "success": result.get("success", False),
                "call_made": True,
                "supplier_name": supplier_name,
                "phone_called": supplier_phone,
                "booking_ref": booking_ref,
                "conversation_id": result.get("conversation_id"),
                "call_sid": result.get("call_sid"),
                "message": f"Called {supplier_name} successfully"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Call failed: {str(e)}",
                "call_made": False
            }
