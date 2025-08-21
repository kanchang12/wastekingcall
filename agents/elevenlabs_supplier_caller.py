import requests
import json
from typing import Dict, Any, Optional

class ElevenLabsSupplierCaller:
    def __init__(self, elevenlabs_api_key: str, agent_id: str, agent_phone_number_id: str):
        self.api_key = elevenlabs_api_key
        self.agent_id = agent_id
        self.agent_phone_number_id = agent_phone_number_id
        self.base_url = "https://api.elevenlabs.io/v1"
        
    def make_outbound_call(self, to_number: str, conversation_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make an outbound call using ElevenLabs Conversational AI via Twilio
        
        Args:
            to_number: Phone number to call (e.g., "+44987654321")
            conversation_data: Optional data to pass to the conversation agent
        
        Returns:
            Dict with success status, conversation_id, and callSid
        """
        headers = {
            "Accept": "application/json",
            "xi-api-key": self.api_key,
            "Content-Type": "application/json"
        }
        
        payload = {
            "agent_id": self.agent_id,
            "agent_phone_number_id": self.agent_phone_number_id,
            "to_number": to_number
        }
        
        if conversation_data:
            payload["conversation_initiation_client_data"] = conversation_data
        
        try:
            response = requests.post(
                f"{self.base_url}/convai/twilio/outbound-call",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                return {
                    "success": result.get("success", False),
                    "message": result.get("message", ""),
                    "conversation_id": result.get("conversation_id"),
                    "call_sid": result.get("callSid"),
                    "status_code": 200
                }
            else:
                return {
                    "success": False,
                    "error": f"API error: {response.status_code} - {response.text}",
                    "status_code": response.status_code
                }
                
        except Exception as e:
            return {
                "success": False,
                "error": f"Request failed: {str(e)}",
                "status_code": 0
            }
    
    def call_supplier_for_availability(self, supplier_phone: str, service_type: str, postcode: str, date: str) -> Dict[str, Any]:
        """
        Call supplier to check availability for specific service
        """
        conversation_data = {
            "purpose": "availability_check",
            "service_type": service_type,
            "postcode": postcode,
            "requested_date": date,
            "caller": "WasteKing_automated_system"
        }
        
        return self.make_outbound_call(supplier_phone, conversation_data)
    
    def call_supplier_from_smp_response(self, smp_response: Dict[str, Any], booking_details: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call supplier using phone number from SMP API response
        """
        if not smp_response.get('success'):
            return {
                "success": False,
                "error": "SMP API response failed, cannot get supplier number"
            }
        
        supplier_phone = smp_response.get('supplier_phone')
        if not supplier_phone:
            return {
                "success": False,
                "error": "No supplier phone number in SMP response"
            }
        
        # Create conversation data with booking info
        conversation_data = {
            "purpose": "booking_confirmation",
            "service_type": smp_response.get('service_type'),
            "postcode": smp_response.get('postcode'),
            "price": smp_response.get('price'),
            "booking_ref": smp_response.get('booking_ref'),
            "customer_name": booking_details.get('customer_name'),
            "customer_contact": booking_details.get('customer_contact'),
            "caller": "WasteKing_automated_system"
        }
        
        print(f"🔥 Calling supplier {supplier_phone} with ElevenLabs")
        return self.make_outbound_call(supplier_phone, conversation_data)

# Usage example:
# 1. Get pricing and supplier phone from SMP API
# smp_tool = SMPAPITool(base_url="https://wk-smp-api-dev.azurewebsites.net/", access_token="your_token")
# smp_response = smp_tool._run(action="get_pricing", postcode="LS14ED", service="man_and_van", type_="8yard")
# 
# 2. Call supplier using ElevenLabs with the phone number from SMP
# caller = ElevenLabsSupplierCaller("your_elevenlabs_api_key", "your_agent_id", "your_phone_number_id")
# booking_details = {"customer_name": "Kanjan", "customer_contact": "07823656762"}
# call_result = caller.call_supplier_from_smp_response(smp_response, booking_details)
