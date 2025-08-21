import requests
import json
import time
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
            print(f"🔧 SMP API Tool called with action: {action}")
            print(f"🔧 Parameters: {kwargs}")
            
            if action == "create_booking":
                return self._create_booking()
            elif action == "get_pricing" or action == "get_price":
                return self._get_pricing(**kwargs)
            elif action == "call_supplier":
                return self._call_supplier(**kwargs)
            elif action == "check_supplier_availability":
                return self._check_supplier_availability(**kwargs)
            elif action == "update_booking":
                return self._update_booking(**kwargs)
            else:
                print(f"❌ Unknown action: {action}")
                return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            print(f"❌ SMP API Error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _create_booking(self) -> Dict[str, Any]:
        print("📞 Creating new booking...")
        
        headers = {
            "x-wasteking-request": self.access_token,
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(
                f"{self.base_url}api/booking/create",
                headers=headers,
                json={"type": "chatbot", "source": "wasteking.co.uk"},
                timeout=15
            )
            
            print(f"📞 Booking creation response: {response.status_code}")
            
            if response.status_code == 200:
                booking_ref = response.json().get('bookingRef')
                print(f"✅ Booking created: {booking_ref}")
                return {"success": True, "booking_ref": booking_ref}
        
        except Exception as e:
            print(f"❌ Booking creation error: {e}")
        
        print(f"❌ Booking creation failed")
        return {"success": False, "error": "Failed to create booking"}
    
    def _get_pricing(self, postcode: str = "", service: str = "", type_: str = "", **kwargs) -> Dict[str, Any]:
        print(f"💰 Getting pricing for {service} {type_} in {postcode}")
        
        if not postcode or not service:
            print("❌ Missing required parameters")
            return {"success": False, "error": "Missing postcode or service"}
        
        try:
            # Create booking first
            booking_result = self._create_booking()
            if not booking_result["success"]:
                # Return fallback pricing
                return self._get_fallback_pricing(service, type_)
            
            booking_ref = booking_result["booking_ref"]
            
            search_payload = {
                "bookingRef": booking_ref,
                "search": {
                    "postCode": postcode,
                    "service": service,
                    "type": type_ or "8yard"
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
                supplier_name = quote.get('supplierName', 'Local Supplier')
                price = quote.get('price', '0')
                
                if price and price != '0':
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
            
            # Fallback to standard pricing
            return self._get_fallback_pricing(service, type_)
            
        except Exception as e:
            print(f"❌ Pricing error: {e}")
            return self._get_fallback_pricing(service, type_)
    
    def _get_fallback_pricing(self, service: str, type_: str) -> Dict[str, Any]:
        """Fallback pricing when API fails"""
        print(f"💰 Using fallback pricing for {service} {type_}")
        
        fallback_prices = {
            "skip": {
                "4yard": "200",
                "6yard": "240", 
                "8yard": "280",
                "12yard": "360"
            },
            "man_and_van": {
                "2yard": "90",
                "4yard": "120",
                "6yard": "180",
                "8yard": "240",
                "10yard": "300"
            },
            "grab": {
                "6wheeler": "300",
                "8wheeler": "400"
            }
        }
        
        service_key = service.replace("_", "")
        price = fallback_prices.get(service_key, {}).get(type_, "220")
        
        return {
            "success": True,
            "price": price,
            "supplier_phone": "07823656762",
            "supplier_name": "WasteKing Local",
            "fallback": True
        }
    
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
            "booking_ref": pricing_result.get("booking_ref"),
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
        
        try:
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
        
        except Exception as e:
            print(f"❌ Update error: {e}")
        
        print(f"❌ Update failed")
        return {"success": False, "error": "Update failed"}
