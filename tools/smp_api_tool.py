import requests
import json
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field

class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = "Get real pricing and create bookings with WasteKing SMP API"
    base_url: str = Field(default="https://wk-smp-api-dev.azurewebsites.net/")
    access_token: str = Field(default="")
    
    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        try:
            if action == "create_booking":
                return self._create_booking()
            elif action == "get_pricing":
                return self._get_pricing(**kwargs)
            elif action == "update_booking":
                return self._update_booking(**kwargs)
            else:
                return {"success": False, "error": "Unknown action"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def _create_booking(self) -> Dict[str, Any]:
        headers = {
            "x-wasteking-request": self.access_token,
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{self.base_url}api/booking/create",
            headers=headers,
            json={"type": "chatbot", "source": "wasteking.co.uk"},
            timeout=15
        )
        
        if response.status_code == 200:
            return {"success": True, "booking_ref": response.json().get('bookingRef')}
        return {"success": False, "error": f"HTTP {response.status_code}"}
    
    def _get_pricing(self, postcode: str, service: str, type_: str, booking_ref: str = None) -> Dict[str, Any]:
        if not booking_ref:
            booking_result = self._create_booking()
            if not booking_result["success"]:
                return booking_result
            booking_ref = booking_result["booking_ref"]
        
        search_payload = {
            "bookingRef": booking_ref,
            "search": {
                "postCode": postcode,
                "service": service,
                "type": type_
            }
        }
        
        headers = {
            "x-wasteking-request": self.access_token,
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{self.base_url}api/booking/update/",
            headers=headers,
            json=search_payload,
            timeout=20
        )
        
        if response.status_code in [200, 201]:
            data = response.json()
            quote = data.get('quote', {})
            return {
                "success": True,
                "booking_ref": booking_ref,
                "price": quote.get('price', '0'),
                "supplier_phone": quote.get('supplierPhone'),
                "supplier_name": quote.get('supplierName'),
                "quote_data": quote
            }
        
        return {"success": False, "error": f"HTTP {response.status_code}"}
    
    def _update_booking(self, booking_ref: str, update_data: Dict) -> Dict[str, Any]:
        headers = {
            "x-wasteking-request": self.access_token,
            "Content-Type": "application/json"
        }
        
        payload = {"bookingRef": booking_ref}
        payload.update(update_data)
        
        response = requests.post(
            f"{self.base_url}api/booking/update/",
            headers=headers,
            json=payload,
            timeout=20
        )
        
        if response.status_code in [200, 201]:
            return {"success": True, "data": response.json()}
        return {"success": False, "error": f"HTTP {response.status_code}"}
