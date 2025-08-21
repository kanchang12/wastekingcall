import requests
import json
import time
import re
from typing import Dict, Any, Optional
from langchain.tools import BaseTool
from pydantic import Field

# Note: This code assumes that the required configuration variables and
# other tool classes (like SMSTool) are available in the environment.

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
            elif action == "update_booking":
                return self._update_booking(**kwargs)
            else:
                print(f"❌ Unknown action: {action}")
                return {"success": False, "error": f"Unknown action: {action}"}
        except Exception as e:
            print(f"❌ SMP API Error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _create_booking(self) -> Dict[str, Any]:
        """Helper method: Creates a new booking and returns the booking reference."""
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
                timeout=15,
                verify=False
            )
            if response.status_code == 200:
                booking_ref = response.json().get('bookingRef')
                print(f"✅ Booking created: {booking_ref}")
                return {"success": True, "booking_ref": booking_ref}
            else:
                return {"success": False, "error": f"Failed to create booking. Status: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Booking creation error: {str(e)}"}
    
    def _get_pricing(self, postcode: str = "", service: str = "", type_: str = "", **kwargs) -> Dict[str, Any]:
        """
        Orchestrator: Gets a price by creating a temporary booking and updating it.
        This does NOT confirm the booking.
        """
        print(f"💰 Getting pricing for {service} {type_} in {postcode}")
        
        if not postcode or not service:
            print("❌ Missing required parameters")
            return {"success": False, "error": "Missing postcode or service"}
        
        # Step 1: Create a booking to get a booking reference
        booking_result = self._create_booking()
        if not booking_result["success"]:
            print("❌ Booking creation failed. Falling back to default pricing.")
            return self._get_fallback_pricing(service, type_)
        
        booking_ref = booking_result["booking_ref"]
        
        # Step 2: Update the booking with search details to get a quote
        search_payload = {
            "search": {
                "postCode": postcode,
                "service": service,
                "type": type_ or "8yard"
            }
        }
        update_result = self._update_booking(booking_ref, search_payload)
        
        if not update_result["success"]:
            print("❌ Price update failed. Falling back to default pricing.")
            return self._get_fallback_pricing(service, type_)
        
        quote = update_result["data"].get('quote', {})
        price = quote.get('price', '0')
        
        if price and price != '0':
            print(f"✅ Real-time price found: £{price}")
            return {
                "success": True,
                "booking_ref": booking_ref,
                "price": price,
                "supplier_phone": quote.get('supplierPhone', '07823656762'),
                "supplier_name": quote.get('supplierName', 'Local Supplier'),
                "quote_data": quote
            }
        
        print("⚠️ No real-time price returned. Using fallback.")
        return self._get_fallback_pricing(service, type_)
    
    def _confirm_and_pay(self, booking_ref: str, customer_phone: str, amount: str) -> Dict[str, Any]:
        """
        Orchestrator: Confirms a booking, gets a payment link, and sends it via SMS.
        """
        if not all([booking_ref, customer_phone, amount]):
            return {"success": False, "error": "Missing required parameters."}
        
        print(f"📝 Confirming booking {booking_ref} and sending payment link.")
        
        # Step 1: Generate payment link by updating the booking
        payment_payload = {"action": "quote"}
        payment_response = self._update_booking(booking_ref, payment_payload)
        
        payment_link = None
        if payment_response and payment_response.get('success'):
            payment_link = payment_response['data'].get('quote', {}).get('paymentLink')
        
        if not payment_link:
            return {"success": False, "error": "Failed to generate payment link from API."}
        
        # Step 2: Send payment link via SMS (assumes SMSTool is available)
        sms_tool = SMSTool()  # Assumes SMSTool is correctly defined and imported
        sms_response = sms_tool._run(
            phone=customer_phone, 
            amount=amount, 
            booking_ref=booking_ref, 
            payment_link=payment_link
        )
        
        if not sms_response.get('success'):
            return {"success": False, "error": "Failed to send SMS."}
        
        return {
            "success": True,
            "message": "Booking confirmed and payment link sent successfully.",
            "booking_ref": booking_ref,
            "payment_link": payment_link,
            "sms_details": sms_response
        }
    
    def _update_booking(self, booking_ref: str, update_data: Dict) -> Dict[str, Any]:
        """Updates an existing booking with new data."""
        # This method is used by other internal methods like _get_pricing and _confirm_and_pay.
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
                timeout=20,
                verify=False
            )
            if response.status_code in [200, 201]:
                print("✅ Booking updated successfully")
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"Update failed. Status: {response.status_code}"}
        except Exception as e:
            return {"success": False, "error": f"Update error: {str(e)}"}
    
    def _get_fallback_pricing(self, service: str, type_: str) -> Dict[str, Any]:
        """Fallback pricing when API fails"""
        print(f"💰 Using fallback pricing for {service} {type_}")
        fallback_prices = {
            "skip": {"4yard": "200", "6yard": "240", "8yard": "280", "12yard": "360"},
            "man_and_van": {"2yard": "90", "4yard": "120", "6yard": "180", "8yard": "240", "10yard": "300"},
            "grab": {"6wheeler": "300", "8wheeler": "400"}
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
        """Checks supplier availability via a simulated call."""
        pricing_result = self._get_pricing(postcode=postcode, service=service, type_=type_)
        if not pricing_result["success"]:
            return pricing_result
        supplier_phone = pricing_result["supplier_phone"]
        supplier_name = pricing_result["supplier_name"]
        test_phone = "07823656762"
        time.sleep(2)
        return {
            "success": True,
            "availability": "available",
            "message": f"Supplier {supplier_name} confirms availability",
            "booking_ref": pricing_result.get("booking_ref"),
            "price": pricing_result["price"]
        }
    
    def _call_supplier(self, supplier_phone: str, supplier_name: str, booking_ref: str, message: str) -> Dict[str, Any]:
        """Simulates an actual call to a supplier."""
        test_phone = "07823656762"
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
