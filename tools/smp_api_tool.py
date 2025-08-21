import requests
import json
import time
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field

class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = "Get WasteKing pricing and call suppliers. Use when customer asks for prices, costs, or availability. Parameters: postcode (required), service (skip/man_and_van/grab), type_ (4yard/6yard/8yard/12yard)"
    base_url: str = Field(default="https://wk-smp-api-dev.azurewebsites.net/")
    access_token: str = Field(default="")
    
    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        try:
            print(f"🔧 SMP API Tool called with action: {action}")
            print(f"🔧 Parameters: {kwargs}")
            
            if action == "create_booking":
                return self._create_booking()
            elif action == "get_pricing":
                return self._get_pricing(**kwargs)
            elif action == "call_supplier":
                return self._call_supplier(**kwargs)
            elif action == "check_supplier_availability":
                return self._check_supplier_availability(**kwargs)
            elif action == "update_booking":
                return self._update_booking(**kwargs)
            else:
                return {"success": False, "error": "Unknown action"}
        except Exception as e:
            print(f"❌ SMP API Error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _create_booking(self) -> Dict[str, Any]:
        print("📞 Creating new booking...")
        
        headers = {
            "x-wasteking-request": self.access_token,
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{self.base_url}api/booking/create",
            headers=headers,
            json={"type": "Thomas", "source": "wasteking.co.uk"},
            timeout=15
        )
        
        print(f"📞 Booking creation response: {response.status_code}")
        
        if response.status_code == 200:
            booking_ref = response.json().get('bookingRef')
            print(f"✅ Booking created: {booking_ref}")
            return {"success": True, "booking_ref": booking_ref}
        
        print(f"❌ Booking creation failed: HTTP {response.status_code}")
        return {"success": False, "error": f"HTTP {response.status_code}"}

    # Add this to your existing SMPAPITool class
def _run(self, action: str = "get_pricing", postcode: str = "", service: str = "", type_: str = "", **kwargs) -> Dict[str, Any]:
    try:
        print(f"🔧 SMP API Tool called with action: {action}")
        print(f"🔧 Parameters: postcode={postcode}, service={service}, type_={type_}")
        
        if action == "get_pricing" and postcode and service and type_:
            return self._get_pricing(postcode, service, type_)
        elif action == "create_booking":
            return self._create_booking()
        elif action == "call_supplier":
            return self._call_supplier(**kwargs)
        elif action == "check_supplier_availability":
            return self._check_supplier_availability(postcode, service, type_)
        else:
            # Default to get_pricing if parameters provided
            if postcode and service:
                return self._get_pricing(postcode, service, type_ or "8yard")
            return {"success": False, "error": f"Unknown action: {action}"}
    except Exception as e:
        print(f"❌ SMP API Error: {str(e)}")
        return {"success": False, "error": str(e)}
    
    def _get_pricing(self, postcode: str, service: str, type_: str, booking_ref: str = None) -> Dict[str, Any]:
        print(f"💰 Getting pricing for {service} {type_} in {postcode}")
        
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
        
        print(f"💰 Sending pricing request: {search_payload}")
        
        response = requests.post(
            f"{self.base_url}api/booking/update/",
            headers=headers,
            json=search_payload,
            timeout=20
        )
        
        print(f"💰 Pricing response: {response.status_code}")
        
        if response.status_code in [200, 201]:
            data = response.json()
            quote = data.get('quote', {})
            
            # Extract supplier information
            supplier_phone = quote.get('supplierPhone', '07823656762')  # Test number
            supplier_name = quote.get('supplierName', 'Test Supplier')
            price = quote.get('price', '0')
            
            print(f"✅ Price found: £{price}")
            print(f"📱 Supplier: {supplier_name} - {supplier_phone}")
            
            return {
                "success": True,
                "booking_ref": booking_ref,
                "price": price,
                "supplier_phone": supplier_phone,
                "supplier_name": supplier_name,
                "quote_data": quote
            }
        
        print(f"❌ Pricing failed: HTTP {response.status_code}")
        return {"success": False, "error": f"HTTP {response.status_code}"}
    
    def _check_supplier_availability(self, postcode: str, service: str, type_: str, date: str = None) -> Dict[str, Any]:
        """Call supplier to check availability - this runs in background"""
        print(f"📞 Checking supplier availability for {service} {type_} in {postcode}")
        
        # First get pricing to get supplier details
        pricing_result = self._get_pricing(postcode, service, type_)
        
        if not pricing_result["success"]:
            return pricing_result
        
        supplier_phone = pricing_result["supplier_phone"]
        supplier_name = pricing_result["supplier_name"]
        
        # Simulate calling supplier (for testing use hardcoded number)
        test_phone = "07823656762"
        
        print(f"📞 CALLING SUPPLIER: {supplier_name}")
        print(f"📱 Phone: {test_phone}")
        print(f"📞 Checking availability for {date or 'ASAP'}")
        
        # Simulate call delay
        time.sleep(2)
        
        # For testing, return positive availability
        return {
            "success": True,
            "supplier_called": True,
            "supplier_name": supplier_name,
            "supplier_phone": test_phone,
            "availability": "available",
            "message": f"Supplier {supplier_name} confirms availability",
            "booking_ref": pricing_result["booking_ref"],
            "price": pricing_result["price"]
        }
    
    def _call_supplier(self, supplier_phone: str, supplier_name: str, booking_ref: str, message: str) -> Dict[str, Any]:
        """Make actual call to supplier"""
        # For testing, use hardcoded number
        test_phone = "07823656762"
        
        print(f"📞 CALLING SUPPLIER NOW:")
        print(f"📱 Name: {supplier_name}")
        print(f"📱 Phone: {test_phone} (test number)")
        print(f"📋 Booking: {booking_ref}")
        print(f"💬 Message: {message}")
        
        # Simulate call process
        time.sleep(1)
        
        return {
            "success": True,
            "call_made": True,
            "supplier_name": supplier_name,
            "phone_called": test_phone,
            "booking_ref": booking_ref,
            "call_status": "connected",
            "message": f"Called {supplier_name} successfully"
        }
    
    def _update_booking(self, booking_ref: str, update_data: Dict) -> Dict[str, Any]:
        print(f"📝 Updating booking {booking_ref} with: {update_data}")
        
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
        
        print(f"📝 Update response: {response.status_code}")
        
        if response.status_code in [200, 201]:
            print("✅ Booking updated successfully")
            return {"success": True, "data": response.json()}
        
        print(f"❌ Update failed: HTTP {response.status_code}")
        return {"success": False, "error": f"HTTP {response.status_code}"}
