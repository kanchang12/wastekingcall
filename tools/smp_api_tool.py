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
    koyeb_url: str = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app"
    
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
            elif action == "create_booking_quote":
                print(f"🔧 SMP API TOOL: Calling _create_booking_quote()")
                result = self._create_booking_quote(**kwargs)
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

    # -------------------------
    # EXACT ORCHESTRATOR FUNCTIONS - COPIED FROM ORCHESTRATOR.PY
    # -------------------------

    def _send_koyeb_webhook(self, url: str, payload: dict, method: str = "POST") -> dict:
        try:
            headers = {"Content-Type": "application/json"}
            if method.upper() == "POST":
                r = requests.post(url, json=payload, headers=headers, timeout=10)
            else:
                r = requests.get(url, params=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            return {"success": False, "error": f"HTTP {r.status_code}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_pricing(self, postcode: str, service: str, type: str) -> Dict[str, Any]:
        """24/7 pricing - always available"""
        url = f"{self.koyeb_url}/api/wasteking-get-price"
        payload = {"postcode": postcode, "service": service, "type": type}
        print(f"🔥 PRICING CALL: {payload}")
        return self._send_koyeb_webhook(url, payload, method="POST")

    def _create_booking_quote(self, type: str, service: str, postcode: str, firstName: str, phone: str, booking_ref: str) -> Dict[str, Any]:
        """24/7 booking - always available"""
        url = f"{self.koyeb_url}/api/wasteking-confirm-booking"
        payload = {
            "booking_ref": booking_ref,
            "postcode": postcode,
            "service": service,
            "type": type,
            "firstName": firstName,
            "phone": phone
        }
        print(f"🔥 BOOKING CALL: {payload}")
        return self._send_koyeb_webhook(url, payload, method="POST")

    # -------------------------
    # AGENT TOOL FUNCTIONS (for AI agents to call)
    # -------------------------
    
    def _take_payment(self, customer_phone: Optional[str] = None, quote_id: Optional[str] = None, 
                     amount: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Payment processing for AI agents"""
        print(f"📱 TAKE_PAYMENT:")
        print(f"   📞 Phone: {customer_phone}")
        print(f"   📋 Quote ID: {quote_id}")
        print(f"   💰 Amount: £{amount}")
        
        if not customer_phone or not quote_id:
            return {"success": False, "error": "Missing phone or quote_id"}
        
        payload = {
            "quote_id": quote_id,
            "customer_phone": customer_phone,
            "amount": amount or "1",
            "call_sid": kwargs.get("call_sid", "")
        }
        
        url = f"{self.koyeb_url}/api/send-payment-sms"
        response = self._send_koyeb_webhook(url, payload, "POST")
        
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
        """Supplier calling for AI agents"""
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
            
            print(f"🔧 SMP API TOOL: Calling supplier via ElevenLabs")
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
