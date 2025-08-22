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
    description: str = """WasteKing API for pricing, booking quotes, payment processing, and supplier calling."""
    koyeb_url: str = Field(default_factory=lambda: os.getenv('KOYEB_URL', 'https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app'))
    
    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        print(f"\n🔧 ==================== SMP API TOOL CALLED ====================")
        print(f"🔧 ACTION: {action}")
        print(f"🔧 PARAMETERS: {json.dumps(kwargs, indent=2)}")
        print(f"🔧 KOYEB URL: {self.koyeb_url}")
        
        try:
            print(f"🔧 SMP API TOOL: Routing to action handler...")
            if action == "get_pricing":
                print(f"🔧 SMP API TOOL: Calling _get_pricing()")
                result = self._get_pricing(**kwargs)
            elif action == "create_booking_quote1":
                print(f"🔧 SMP API TOOL: Calling _create_booking_quote1()")
                result = self._create_booking_quote1(**kwargs)
            elif action == "take_payment":
                print(f"🔧 SMP API TOOL: Calling _take_payment()")
                result = self._take_payment(**kwargs)
            elif action == "call_supplier":
                print(f"🔧 SMP API TOOL: Calling _call_supplier()")
                result = self._call_supplier(**kwargs)
            else:
                print(f"❌ SMP API TOOL: Unknown action: {action}")
                result = {"success": False, "error": f"Unknown action: {action}"}
            
            print(f"🔧 TOOL RESULT:")
            print(f"🔧 {json.dumps(result, indent=2)}")
            print(f"🔧 ==================== SMP API TOOL FINISHED ====================\n")
            
            return result
            
        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            print(f"❌ SMP API TOOL ERROR: {error_result}")
            print(f"🔧 ==================== SMP API TOOL FAILED ====================\n")
            return error_result
    
    def _send_koyeb_webhook(self, url, data_payload, method="POST"):
        try:
            print(f"🔄 SMP API TOOL: Sending {method} to: {url}")
            print(f"🔄 Payload: {json.dumps(data_payload, indent=2)}")
            print(f"🔧 SMP API TOOL: TOOL CALL - requests.{method.lower()}()")
            
            if method.upper() == "GET":
                response = requests.get(url, params=data_payload, timeout=30)
            else:
                response = requests.post(url, json=data_payload, timeout=30)
            
            print(f"🔄 Response status: {response.status_code}")
            print(f"🔄 Response text: {response.text}")
            
            if response.status_code in [200, 201]:
                try:
                    return response.json()
                except json.JSONDecodeError:
                    return {"success": False, "error": f"Invalid JSON: {response.text}"}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _get_pricing(self, postcode: Optional[str] = None, service: Optional[str] = None, 
                    type: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        
        print(f"💰 GET_PRICING:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   🚛 Service: {service}")
        print(f"   📦 Type: {type}")
        
        if not postcode or not service or not type:
            return {"success": False, "error": "Missing required parameters"}
        
        # Clean postcode
        postcode = postcode.upper().strip().replace(' ', '')
        print(f"   📍 Clean Postcode: {postcode}")
        
        payload = {"postcode": postcode, "service": service, "type": type}
        url = f"{self.koyeb_url}/api/wasteking-get-price"
        
        # Try POST first
        response = self._send_koyeb_webhook(url, payload, "POST")
        
        # If POST fails, try GET
        if not response.get("success"):
            response = self._send_koyeb_webhook(url, payload, "GET")
        
        if response.get("success"):
            return {
                "success": True,
                "booking_ref": response.get('booking_ref'),
                "price": response.get('price'),
                "real_supplier_phone": os.getenv('SUPPLIER_PHONE', '+44XXXXXXXXXX'),
                "supplier_name": os.getenv('SUPPLIER_NAME', 'Local Supplier'),
                "postcode": postcode,
                "service": service,
                "type": type
            }
        
        return {"success": False, "message": "No pricing available"}
    
    def _create_booking_quote1(self, **kwargs) -> Dict[str, Any]:
        
        print(f"📋 CREATE_BOOKING_QUOTE:")
        print(f"   👤 Name: {kwargs.get('firstName')}")
        print(f"   📞 Phone: {kwargs.get('phone')}")
        print(f"   📍 Postcode: {kwargs.get('postcode')}")
        print(f"   🚛 Service: {kwargs.get('service')}")
        
        required = ['postcode', 'service', 'type', 'firstName', 'phone', 'booking_ref']
        for field in required:
            if not kwargs.get(field):
                return {"success": False, "error": f"Missing: {field}"}
        
        # Clean postcode
        postcode = kwargs['postcode'].upper().replace(" ", "").strip()
        
        data_payload = {
            "booking_ref": kwargs.get("booking_ref"),
            "postcode": postcode,
            "service": kwargs.get("service"),
            "type": kwargs.get("type"),
            "firstName": kwargs.get("firstName"),
            "phone": kwargs.get("phone"),
            "lastName": kwargs.get("lastName", ""),
            "email": kwargs.get("emailAddress", ""),
            "date": kwargs.get("date", ""),
            "time": kwargs.get("time", "")
        }
        
        url = f"{self.koyeb_url}/api/wasteking-confirm-booking"
        
        # Try POST first
        response = self._send_koyeb_webhook(url, data_payload, "POST")
        
        # If POST fails, try GET
        if not response.get("success"):
            response = self._send_koyeb_webhook(url, data_payload, "GET")
        
        if response.get("success"):
            return {
                "success": True,
                "message": "Booking confirmed",
                "booking_ref": response.get('booking_ref'),
                "payment_link": response.get('payment_link'),
                "final_price": response.get('price'),
                "customer_phone": kwargs.get("phone")
            }
        
        return {"success": False, "message": "Booking failed"}
    
    def _take_payment(self, customer_phone: Optional[str] = None, quote_id: Optional[str] = None, 
                     amount: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        
        print(f"📱 TAKE_PAYMENT:")
        print(f"   📞 Phone: {customer_phone}")
        print(f"   📋 Quote ID: {quote_id}")
        print(f"   💰 Amount: £{amount}")
        
        if not customer_phone or not quote_id:
            return {"success": False, "error": "Missing phone or quote_id"}
        
        data_payload = {
            "quote_id": quote_id,
            "customer_phone": customer_phone,
            "amount": amount or "1",
            "call_sid": kwargs.get("call_sid", "")
        }
        
        url = f"{self.koyeb_url}/api/send-payment-sms"
        response = self._send_koyeb_webhook(url, data_payload, "POST")
        
        if response.get("status") == "success":
            return {
                "success": True,
                "message": "Payment link sent",
                "booking_ref": quote_id,
                "payment_link": response.get("payment_link_used"),
                "final_price": response.get("amount", amount),
                "customer_phone": customer_phone,
                "sms_sent": True
            }
        
        return {"success": False, "error": "Payment failed"}
    
    def _call_supplier(self, supplier_phone: Optional[str] = None, supplier_name: Optional[str] = None, 
                      booking_ref: Optional[str] = None, message: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        
        print(f"📞 CALL_SUPPLIER:")
        print(f"   📞 Phone: {supplier_phone}")
        print(f"   👤 Name: {supplier_name}")
        print(f"   📋 Ref: {booking_ref}")
        
        if not all([supplier_phone, supplier_name, booking_ref, message]):
            return {"success": False, "error": "Missing required parameters"}
        
        try:
            print(f"🔧 SMP API TOOL: Instantiating ElevenLabsSupplierCaller")
            caller = ElevenLabsSupplierCaller(
                elevenlabs_api_key=os.getenv('ELEVENLABS_API_KEY'),
                agent_id=os.getenv('ELEVENLABS_AGENT_ID'),
                agent_phone_number_id=os.getenv('ELEVENLABS_AGENT_PHONE_NUMBER_ID')
            )
            
            booking_details = {
                "booking_ref": booking_ref,
                "supplier_name": supplier_name,
                "message": message,
                "customer_name": kwargs.get("customer_name", ""),
                "customer_contact": kwargs.get("customer_phone", "")
            }
            
            smp_response = {
                "success": True, 
                "supplier_phone": supplier_phone,
                "service_type": kwargs.get("service", ""),
                "postcode": kwargs.get("postcode", ""),
                "price": kwargs.get("price", ""),
                "booking_ref": booking_ref
            }
            
            print(f"🔧 SMP API TOOL: TOOL CALL - ElevenLabsSupplierCaller.call_supplier_from_smp_response")
            print(f"🔧 TOOL CALL: caller.call_supplier_from_smp_response(smp_response, booking_details)")
            result = caller.call_supplier_from_smp_response(smp_response, booking_details)
            
            return {
                "success": result.get("success", False),
                "call_made": True,
                "supplier_name": supplier_name,
                "phone_called": supplier_phone,
                "booking_ref": booking_ref,
                "conversation_id": result.get("conversation_id"),
                "call_sid": result.get("call_sid"),
                "message": f"Called {supplier_name}"
            }
            
        except Exception as e:
            return {"success": False, "error": f"Call failed: {str(e)}", "call_made": False}
