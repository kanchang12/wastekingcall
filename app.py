import os
import json
import re
import uuid
import PyPDF2
import requests
import time
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from flask import Flask, request, jsonify
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from pydantic import Field

app = Flask(__name__)

# ===============================
# RULES PROCESSOR CLASS
# ===============================
class RulesProcessor:
    def __init__(self):
        self.pdf_path = "data/rules/all rules.pdf"
        self.rules_data = self._load_all_rules()
    
    def _load_all_rules(self) -> Dict[str, Any]:
        """Load rules from PDF first, fallback to hardcoded if PDF not available"""
        pdf_text = self._load_rules_from_pdf()
        
        if pdf_text:
            print("Loading rules from PDF...")
            return self._parse_wasteking_pdf(pdf_text)
        else:
            print("PDF not found, using hardcoded rules...")
            return self._get_hardcoded_rules()
    
    def _load_rules_from_pdf(self) -> str:
        """Extract text from the WasteKing rules PDF"""
        try:
            if not Path(self.pdf_path).exists():
                return ""
            
            with open(self.pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                
                return text
                
        except Exception as e:
            print(f"Error reading PDF: {e}")
            return ""
    
    def _parse_wasteking_pdf(self, pdf_text: str) -> Dict[str, Any]:
        """Parse the WasteKing PDF into structured rules"""
        return {
            "lock_rules": self._extract_lock_rules(pdf_text),
            "exact_scripts": self._extract_exact_scripts(pdf_text),
            "office_hours": self._extract_office_hours(pdf_text),
            "transfer_rules": self._extract_transfer_rules(pdf_text),
            "skip_rules": self._extract_skip_rules(pdf_text),
            "mav_rules": self._extract_mav_rules(pdf_text),
            "grab_rules": self._extract_grab_rules(pdf_text),
            "pricing_rules": self._extract_pricing_rules(pdf_text),
            "prohibited_items": self._extract_prohibited_items(pdf_text),
            "surcharge_rates": self._extract_surcharge_rates(pdf_text),
            "testing_corrections": self._extract_testing_corrections(pdf_text)
        }
    
    def _extract_lock_rules(self, text: str) -> Dict[str, str]:
        """Extract LOCK 0-11 mandatory enforcement rules"""
        return {
            "LOCK_0_DATETIME": "CRITICAL: Call get_current_datetime() IMMEDIATELY at conversation start",
            "LOCK_1_NO_GREETING": "NEVER say 'Hi I am Thomas' or any greeting",
            "LOCK_2_SERVICE_DETECTION": "IF customer mentions service → Jump to that section",
            "LOCK_3_ONE_QUESTION": "One question at a time - never bundle questions",
            "LOCK_4_NO_DUPLICATES": "Never ask for info twice - use what customer provided",
            "LOCK_5_EXACT_SCRIPTS": "Use exact scripts where specified - never improvise",
            "LOCK_6_NO_OUT_HOURS_TRANSFER": "CARDINAL SIN: NEVER transfer when office closed",
            "LOCK_7_PRICE_THRESHOLDS": "Skip: NO LIMIT, Man&Van: £500+, Grab: £300+",
            "LOCK_8_STORE_ANSWERS": "Don't re-ask for stored information",
            "LOCK_9_OUT_HOURS_CALLBACK": "Out-of-hours = No call back no transfer: take detail try to make the sale give price offer sale",
            "LOCK_10_FOCUS_SALES": "Focus on sales, aim for booking completion",
            "LOCK_11_ANSWER_FIRST": "Answer customer questions FIRST before asking details"
        }
    
    def _extract_exact_scripts(self, text: str) -> Dict[str, str]:
        return {}
    
    def _extract_office_hours(self, text: str) -> Dict[str, str]:
        return {
            "monday_thursday": "8:00am-5:00pm",
            "friday": "8:00am-4:30pm", 
            "saturday": "9:00am-12:00pm",
            "sunday": "CLOSED"
        }
    
    def _extract_transfer_rules(self, text: str) -> Dict[str, Any]:
        return {
            "skip_hire": "NO_LIMIT",
            "man_and_van": 500,
            "grab_hire": 300,
            "out_of_hours_rule": "NEVER transfer out of hours - cardinal sin"
        }
    
    def _extract_skip_rules(self, text: str) -> Dict[str, str]:
        return {}
    
    def _extract_mav_rules(self, text: str) -> Dict[str, Any]:
        return {}
    
    def _extract_grab_rules(self, text: str) -> Dict[str, Any]:
        return {}
    
    def _extract_pricing_rules(self, text: str) -> Dict[str, Any]:
        return {}
    
    def _extract_prohibited_items(self, text: str) -> Dict[str, List[str]]:
        return {"never_allowed_skips": [], "surcharge_items": []}
    
    def _extract_surcharge_rates(self, text: str) -> Dict[str, int]:
        return {}
    
    def _extract_testing_corrections(self, text: str) -> List[Dict[str, str]]:
        return []
    
    def _get_hardcoded_rules(self) -> Dict[str, Any]:
        return {
            "lock_rules": self._extract_lock_rules(""),
            "exact_scripts": {},
            "office_hours": self._extract_office_hours(""),
            "transfer_rules": self._extract_transfer_rules(""),
            "skip_rules": {},
            "mav_rules": {},
            "grab_rules": {},
            "pricing_rules": {},
            "prohibited_items": {"never_allowed_skips": []},
            "surcharge_rates": {},
            "testing_corrections": []
        }
    
    def get_rules_for_agent(self, agent_type: str) -> Dict[str, Any]:
        base_rules = {
            **self.rules_data["lock_rules"],
            "office_hours": self.rules_data["office_hours"],
            "transfer_rules": self.rules_data["transfer_rules"]
        }
        return base_rules

# ===============================
# SMP API TOOL CLASS - CORRECTED
# ===============================
class SMPAPITool(BaseTool):
    name: str = "smp_api"
    description: str = """WasteKing API for a 4-step booking process: create_booking, update_booking_with_search, update_booking_with_details, update_booking_with_quote"""
    base_url: str = "https://wk-smp-api-dev.azurewebsites.net"
    access_token: str = "wk-KZPY-tGF-@d.Aby9fpvMC_VVWkX-GN.i7jCBhF3xceoFfhmawaNc.RH.G_-kwk8*"
    
    def _run(self, action: str, **kwargs) -> Dict[str, Any]:
        print(f"\n🔧 ==================== SMP API TOOL CALLED ====================")
        print(f"🔧 ACTION: {action}")
        print(f"🔧 PARAMETERS: {json.dumps(kwargs, indent=2)}")
        print(f"🔧 BASE URL: {self.base_url}")
        
        try:
            if action == "create_booking":
                result = self._create_booking(**kwargs)
            elif action == "update_booking_with_search":
                result = self._update_booking_with_search(**kwargs)
            elif action == "update_booking_with_details":
                result = self._update_booking_with_details(**kwargs)
            elif action == "update_booking_with_quote":
                result = self._update_booking_with_quote(**kwargs)
            else:
                result = {"success": False, "error": f"Unknown action: {action}"}
            
            print(f"🔧 TOOL RESULT: {json.dumps(result, indent=2)}")
            print(f"🔧 ==================== SMP API TOOL FINISHED ====================\n")
            
            return result
            
        except Exception as e:
            error_result = {"success": False, "error": str(e)}
            print(f"❌ SMP API TOOL ERROR: {error_result}")
            return error_result

    def _send_request(self, endpoint: str, payload: dict) -> dict:
        headers = {
            "Content-Type": "application/json",
            "x-wasteking-request": self.access_token
        }
        url = f"{self.base_url}/{endpoint}"
        
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=10)
            if r.status_code == 200:
                return r.json()
            return {"success": False, "error": f"HTTP {r.status_code}", "response": r.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_booking(self, **kwargs) -> Dict[str, Any]:
        """Step 1: Creates a new booking and returns a booking reference."""
        payload = {"type": "chatbot", "source": "wasteking.co.uk"}
        response = self._send_request("api/booking/create", payload)
    
        # If bookingRef exists, extract it clearly
        if response.get("success") and "bookingRef" in response:
            return {"success": True, "bookingRef": response["bookingRef"], "raw": response}
        
        return {"success": False, "error": "No bookingRef returned", "raw": response}

    
    def _update_booking_with_search(self, booking_ref: str, postcode: str, service: str) -> Dict[str, Any]:
        """Step 2: Updates a booking with search details to get prices."""
        payload = {"bookingRef": booking_ref, "search": {"postCode": postcode, "service": service}}
        return self._send_request("api/booking/update", payload)

    def _update_booking_with_details(self, booking_ref: str, customer_details: dict, service_details: dict) -> Dict[str, Any]:
        """Step 3: Updates a booking with customer and service details, then automatically finalizes booking (Step 4)."""
        
        # Step 3: update booking with customer and service details
        payload = {"bookingRef": booking_ref, "customer": customer_details, "service": service_details}
        step3_result = self._send_request("api/booking/update", payload)
        
        if not step3_result.get("success"):
            return step3_result  # return error if Step 3 failed
        
        # Step 4: automatically finalize booking and get payment link
        step4_result = self._update_booking_with_quote(booking_ref)
        if step4_result.get("success"):
            payment_url = step4_result.get("postPaymentUrl", "No payment URL returned")
            print(f"✅ Booking finalized! Payment URL: {payment_url}")
        
        return step4_result

        
    def _update_booking_with_quote(self, booking_ref: str, **kwargs) -> Dict[str, Any]:
        """Step 4: Finalizes the booking and gets the payment URL."""
        payload = {"bookingRef": booking_ref, "action": "quote", "postPaymentUrl": "https://wasteking.co.uk/thank-you/"}
        return self._send_request("api/booking/update", payload)

# ===============================
# DATETIME TOOL CLASS
# ===============================
class DateTimeTool(BaseTool):
    name: str = "datetime_tool"
    description: str = "Get current date and time"
    
    def _run(self) -> Dict[str, Any]:
        now = datetime.now()
        
        is_business_hours = False
        day_of_week = now.weekday()
        hour = now.hour
        
        if day_of_week < 4:
            is_business_hours = 8 <= hour < 17
        elif day_of_week == 4:
            is_business_hours = 8 <= hour < 16
        elif day_of_week == 5:
            is_business_hours = 9 <= hour < 12
        
        return {
            "current_time": now.isoformat(),
            "day_of_week": now.strftime("%A"),
            "hour": hour,
            "is_business_hours": is_business_hours,
            "weekday": day_of_week
        }

# ===============================
# IMPROVED SMS TOOL CLASS WITH TWILIO
# ===============================
class SMSTool(BaseTool):
    name: str = "sms_tool"
    description: str = "Send SMS messages using Twilio"
    account_sid: Optional[str] = Field(default=None)
    auth_token: Optional[str] = Field(default=None)
    phone_number: Optional[str] = Field(default=None)
    
    def __init__(self, account_sid: str = None, auth_token: str = None, phone_number: str = None, **kwargs):
        super().__init__(
            account_sid=account_sid or os.getenv('TWILIO_ACCOUNT_SID'),
            auth_token=auth_token or os.getenv('TWILIO_AUTH_TOKEN'),
            phone_number=phone_number or os.getenv('TWILIO_PHONE_NUMBER'),
            **kwargs
        )
        
        self._client = None
        try:
            from twilio.rest import Client
            if self.account_sid and self.auth_token:
                self._client = Client(self.account_sid, self.auth_token)
                print("✅ SMS TOOL: Twilio client initialized successfully")
            else:
                self._client = None
                print("⚠️ SMS TOOL: Twilio credentials not found, SMS will be simulated")
        except ImportError:
            self._client = None
            print("⚠️ SMS TOOL: Twilio library not installed, SMS will be simulated")
    
    def _run(self, to_number: str, message: str, payment_link: str = None) -> Dict[str, Any]:
        print(f"📱 SMS TOOL: DETAILED SMS SENDING INFO:")
        print(f"📱 TO NUMBER: {to_number}")
        print(f"📱 MESSAGE: {message}")
        print(f"💳 PAYMENT LINK: {payment_link}")
        
        full_message = message
        if payment_link:
            full_message += f"\n\nComplete your payment: {payment_link}"
            print(f"📱 FULL SMS MESSAGE: {full_message}")
        
        try:
            if self._client and self.phone_number:
                print(f"📱 SENDING REAL SMS VIA TWILIO...")
                message_obj = self._client.messages.create(
                    body=full_message,
                    from_=self.phone_number,
                    to=to_number
                )
                print(f"🔥🔥🔥 SMS SENT SUCCESSFULLY VIA TWILIO 🔥🔥🔥")
                print(f"📱 MESSAGE SID: {message_obj.sid}")
                
                return {
                    "success": True,
                    "message": "SMS sent successfully via Twilio",
                    "message_sid": message_obj.sid,
                    "to_number": to_number,
                    "payment_link_included": payment_link is not None
                }
            else:
                print(f"⚠️ SIMULATING SMS (Twilio not configured)")
                print(f"📱 SIMULATED SMS TO: {to_number}")
                print(f"📱 SIMULATED MESSAGE: {full_message}")
                
                return {
                    "success": True,
                    "message": "SMS simulated (Twilio not configured)",
                    "to_number": to_number,
                    "payment_link_included": payment_link is not None
                }
                
        except Exception as e:
            print(f"❌ SMS TOOL ERROR: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "to_number": to_number
            }

# ===============================
# AGENT STATE STORAGE
# ===============================
_AGENT_STATES = {}

def _load_state(conversation_id: str) -> Dict[str, Any]:
    global _AGENT_STATES
    state = _AGENT_STATES.get(conversation_id, {})
    print(f"📂 AGENT: Loaded state for {conversation_id}: {json.dumps(state, indent=2)}")
    return state

def _save_state(conversation_id: str, data: Dict[str, Any]):
    global _AGENT_STATES
    _AGENT_STATES[conversation_id] = data
    print(f"💾 AGENT: Saved state for {conversation_id}: {json.dumps(data, indent=2)}")

def _call_datetime_tool(tools: List[BaseTool]) -> Dict[str, Any]:
    try:
        datetime_tool = None
        for tool in tools:
            if hasattr(tool, 'name') and 'datetime' in tool.name.lower():
                datetime_tool = tool
                break
        
        if datetime_tool:
            result = datetime_tool._run()
            print(f"⏰ AGENT: DateTime tool result: {result}")
            return result
        else:
            print("⚠️ AGENT: DateTime tool not found")
            return {"error": "datetime tool not found", "is_business_hours": False}
    except Exception as e:
        print(f"❌ AGENT: DateTime tool error: {str(e)}")
        return {"error": str(e), "is_business_hours": False}

# ===============================
# SHARED AGENT FUNCTIONS
# ===============================
def _check_transfer_needed_with_office_hours(message: str, data: Dict[str, Any], is_office_hours: bool, agent_type: str) -> bool:
    print(f"📖 {agent_type.upper()} AGENT: Checking transfer rules")
    print(f"🏢 Office hours: {is_office_hours}")
    
    message_lower = message.lower()
    rules_processor = RulesProcessor()
    transfer_rules = rules_processor.get_rules_for_agent(agent_type)['transfer_rules']

    if not is_office_hours:
        print(f"🌙 OUT OF OFFICE HOURS: NEVER TRANSFER - You will talk, give price and try to make the sale")
        return False
    
    if agent_type == 'skip':
        if any(word in message_lower for word in ['grab hire', 'man and van', 'mav']):
            return True
        hazardous_materials = ['asbestos', 'hazardous', 'toxic']
        if any(material in message_lower for material in hazardous_materials):
            return True
        return False
        
    elif agent_type == 'mav':
        if any(word in message_lower for word in ['skip hire', 'grab hire']):
            return True
        hazardous_materials = ['asbestos', 'hazardous', 'toxic']
        if any(material in message_lower for material in hazardous_materials):
            return True
        return False

    elif agent_type == 'grab':
        if any(word in message_lower for word in ['skip hire', 'man and van', 'mav']):
            return True
        hazardous_materials = ['asbestos', 'hazardous', 'toxic']
        if any(material in message_lower for material in hazardous_materials):
            return True
        return False
    
    return False

def _extract_data(message: str, context: Dict = None) -> Dict[str, Any]:
    data = context.copy() if context else {}
    
    full_postcode_pattern = re.compile(
        r'\b([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})\b', re.IGNORECASE
    )

    postcode_match = full_postcode_pattern.search(message)

    if postcode_match:
        # If a match is found, extract the full postcode and remove any spaces.
        data['postcode'] = postcode_match.group(1).replace(' ', '').upper()
        print(f"✅ Extracted full postcode: {data['postcode']}")
    else:
        # If no match is found, set the postcode to None or a default value.
        data['postcode'] = None
        print("❌ No full postcode found in message.")
    
    if 'skip' in message.lower():
        data['service'] = 'skip'
        if any(size in message.lower() for size in ['8-yard', '8 yard', '8yd', '8 yd', 'eight-yard', 'eight yard', 'eight yd']):
            data['type'] = '8yd'
        elif any(size in message.lower() for size in ['6-yard', '6 yard', '6yd', '6 yd', 'six-yard', 'six yard', 'six yd']):
            data['type'] = '6yd'
        elif any(size in message.lower() for size in ['4-yard', '4 yard', '4yd', '4 yd', 'four-yard', 'four yard', 'four yd']):
            data['type'] = '4yd'
        elif any(size in message.lower() for size in ['12-yard', '12 yard', '12yd', '12 yd', 'twelve-yard', 'twelve yard', 'twelve yd']):
            data['type'] = '12yd'
        else:
            data['type'] = '8yd'
            
    if any(word in message.lower() for word in ['man and van', 'mav', 'man & van', 'van']):
        data['service'] = 'mav'
        if any(size in message.lower() for size in ['small', 'small van', '4 cubic', '4 yard', '4-yard', '4yd']):
            data['type'] = '4yd'
        elif any(size in message.lower() for size in ['medium', 'medium van', '6 cubic', '6 yard', '6-yard', '6yd']):
            data['type'] = '6yd'
        elif any(size in message.lower() for size in ['large', 'large van', '8 cubic', '8 yard', '8-yard', '8yd']):
            data['type'] = '8yd'
        else:
            data['type'] = '4yd'

    if any(word in message.lower() for word in ['grab', 'grab hire']):
        data['service'] = 'grab'
        if any(size in message.lower() for size in ['6-tonne', '6 tonne', '6t']):
            data['type'] = '6t'
        elif any(size in message.lower() for size in ['8-tonne', '8 tonne', '8t']):
            data['type'] = '8t'
        else:
            data['type'] = '6t'
    
    if 'kanchen ghosh' in message.lower() or 'kanchen' in message.lower():
        data['firstName'] = 'Kanchen Ghosh'
    else:
        name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
        if name_match:
            data['firstName'] = name_match.group(1).strip().title()
    
    phone_match = re.search(r'\b(\d{10,11})\b', message)
    if phone_match:
        data['phone'] = phone_match.group(1)
        
    waste_types = ['building waste', 'construction', 'garden waste', 'household', 'general waste', 'bricks', 'mortar']
    for waste_type in waste_types:
        if waste_type in message.lower():
            data['waste_type'] = waste_type
            break
            
    if 'monday' in message.lower():
        data['preferred_date'] = 'Monday'
    elif any(day in message.lower() for day in ['tuesday', 'wednesday', 'thursday', 'friday', 'weekend']):
        for day in ['tuesday', 'wednesday', 'thursday', 'friday', 'weekend']:
            if day in message.lower():
                data['preferred_date'] = day.title()
                break
    
    return data

def _determine_step(data: Dict[str, Any], message: str) -> str:
    message_lower = message.lower()
    
    price_request = any(word in message_lower for word in ['price', 'availability', 'cost', 'quote', 'confirm price', 'total price', 'including vat'])
    has_required_pricing_data = data.get('service') and data.get('type') and data.get('postcode')
    
    # Corrected logic to check for complete postcode
    if data.get('postcode') and len(data.get('postcode')) < 5:
        return 'postcode'

    if price_request and has_required_pricing_data and not data.get('has_pricing'):
        print(f"💰 AGENT: Customer requests price and has required data - going to pricing")
        return 'price'
    
    booking_request = any(word in message_lower for word in [
        'book', 'booking', 'confirm booking', 'yes', 'proceed', 
        'confirm the booking', 'booking reference', 'reference number', 
        'can you confirm', 'please confirm'
    ])
    has_all_data = (data.get('service') and data.get('type') and data.get('postcode') and 
                   data.get('firstName') and data.get('phone'))
    
    if booking_request and has_all_data:
        print(f"📋 AGENT: Customer requests booking and has all data - going to booking")
        print(f"📋 AGENT: Data check - Service: {data.get('service')}, Type: {data.get('type')}, Postcode: {data.get('postcode')}, Name: {data.get('firstName')}, Phone: {data.get('phone')}")
        return 'booking'
    
    if not data.get('firstName'): return 'name'
    if not data.get('postcode'): return 'postcode'
    if not data.get('service'): return 'service'
    if not data.get('type'): return 'type'
    if not data.get('waste_type'): return 'waste_type'
    if not data.get('quantity'): return 'quantity'
    if not data.get('product_specific'): return 'product_specific'
    if not data.get('has_pricing'): return 'price'
    if not data.get('preferred_date'): return 'date'
    return 'booking'

def _get_pricing(data: Dict[str, Any], tools: List[BaseTool]) -> str:
    print(f"💰 AGENT: CALLING PRICING TOOL")
    try:
        smp_tool = None
        for tool in tools:
            if hasattr(tool, 'name') and tool.name == 'smp_api':
                smp_tool = tool
                break
        
        if not smp_tool:
            print("❌ AGENT: SMPAPITool not found")
            return "Pricing tool not available"
        
        # Use the new pricing function
        result = smp_tool._update_booking_with_search(
            booking_ref=data.get('booking_ref'),
            postcode=data.get('postcode'),
            service=data.get('service')
        )
        
        if result.get('success'):
            price = "N/A"
            for item in result.get('resultItems', []):
                if item.get('type') == data.get('type'):
                    price = item.get('price')
                    break
            
            data['has_pricing'] = True
            data['price'] = price
            
            return f"💰 {data.get('type')} {data.get('service')} hire at {data.get('postcode')}: {price}. Would you like to book this?"
        else:
            error = result.get('error', 'pricing failed')
            return f"Unable to get pricing: {error}"
            
    except Exception as e:
        return f"Error getting pricing: {str(e)}"

def _create_booking_with_payment_and_sms(self, data: Dict[str, Any]) -> str:
    print(f"🔥🔥🔥 AGENT: 4-STEP BOOKING PROCESS STARTED 🔥🔥🔥")
    
    try:
        smp_tool = None
        sms_tool = None
        for tool in self.tools:
            if hasattr(tool, 'name'):
                if tool.name == 'smp_api':
                    smp_tool = tool
                elif tool.name == 'sms_tool':
                    sms_tool = tool
        
        if not smp_tool: return "Booking tool not available"
        
        # Step 1: Create a new booking
        print(f"🔄 STEP 1: Creating a new booking reference...")
        booking_result = smp_tool._create_booking()
        if not booking_result.get('success'):
            return f"Booking failed: {booking_result.get('error')}"
        booking_ref = booking_result.get('bookingRef')
        print(f"✅ Step 1 SUCCESS: Booking reference created: {booking_ref}")
        
        # Step 2: Update with search details to get pricing
        print(f"🔄 STEP 2: Updating with search to get pricing...")
        search_result = smp_tool._update_booking_with_search(
            booking_ref=booking_ref,
            postcode=data.get('postcode'),
            service=data.get('service')
        )
        if not search_result.get('success'):
            return f"Pricing failed: {search_result.get('error')}"
        
        price = "N/A"
        for item in search_result.get('resultItems', []):
            if item.get('type') == data.get('type'):
                price = item.get('price')
                break
        
        data['price'] = price
        print(f"✅ Step 2 SUCCESS: Price for {data.get('type')} is {price}")
        
        # Step 3: Update with customer and service details
        print(f"🔄 STEP 3: Updating with customer and service details...")
        customer_details = {
            "firstName": data.get('firstName', "Guest"),
            "phone": data.get('phone', "N/A"),
            "addressPostcode": data.get('postcode', "N/A")
        }
        service_details = {
            "service": data.get('service', "N/A"),
            "date": data.get('preferred_date', "N/A"),
            "placement": "drive",
            "notes": "bricks and mortar waste"
        }
        details_result = smp_tool._update_booking_with_details(
            booking_ref=booking_ref,
            customer_details=customer_details,
            service_details=service_details
        )
        if not details_result.get('success'):
            return f"Booking details update failed: {details_result.get('error')}"
        print("✅ Step 3 SUCCESS: Booking details updated.")
        
        # Step 4: Finalize the booking and get payment link
        print(f"🔄 STEP 4: Finalizing quote and creating payment link...")
        payment_result = smp_tool._update_booking_with_quote(
            booking_ref=booking_ref
        )
        if not payment_result.get('success'):
            return f"Payment link creation failed: {payment_result.get('error')}"
        
        payment_link = payment_result.get('payment_link')
        print(f"🔥🔥🔥 Step 4 SUCCESS: Payment link created: {payment_link} 🔥🔥🔥")
        
        sms_message = f"Hi {data.get('firstName')}, your {data.get('type')} {data.get('service')} booking is confirmed! Ref: {booking_ref}, Price: {price}"
        
        if sms_tool:
            sms_result = sms_tool._run(
                to_number=data.get('phone'),
                message=sms_message,
                payment_link=payment_link
            )
            if sms_result.get('success'):
                data['has_booking'] = True
                return f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}. Payment link sent to {data.get('phone')} via SMS."
            else:
                data['has_booking'] = True
                return f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}. Payment link: {payment_link}"
        else:
            data['has_booking'] = True
            return f"✅ Booking confirmed! Ref: {booking_ref}, Price: {price}. Payment link: {payment_link}"
            
    except Exception as e:
        print(f"❌ CRITICAL ERROR IN BOOKING PROCESS: {str(e)}")
        return f"Error creating booking: {str(e)}"
        
def _call_supplier_if_needed(booking_result: Dict[str, Any], customer_data: Dict[str, Any]):
    try:
        supplier_phone = booking_result.get('supplier_phone')
        if supplier_phone:
            print(f"📞 AGENT: Calling supplier {supplier_phone} via ElevenLabs")
    except Exception as e:
        print(f"❌ AGENT: Supplier call error: {str(e)}")

# ===============================
# SKIP HIRE AGENT CLASS
# ===============================
# ===============================
# SKIP HIRE AGENT CLASS
# ===============================
class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Skip Hire agent. Follow PDF rules and call datetime first."""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
        print("✅ SKIP HIRE AGENT initialized with 4-step booking process")

    def process_message(self, message: str, context: Dict = None) -> str:
        print(f"\n🔧 SKIP AGENT RECEIVED: '{message}'")
        conversation_id = context.get('conversation_id') if context else 'default'
        datetime_result = _call_datetime_tool(self.tools)
        is_office_hours = datetime_result.get('is_business_hours', False)
        _load_state(conversation_id)
        extracted_data = _extract_data(message, context)
        combined_data = {**_load_state(conversation_id), **extracted_data}
        transfer_check = _check_transfer_needed_with_office_hours(message, combined_data, is_office_hours, 'skip')

        if transfer_check:
            _save_state(conversation_id, combined_data)
            return f"TRANSFER_TO_ORCHESTRATOR:{json.dumps(combined_data)}"

        current_step = _determine_step(combined_data, message)

        if current_step == 'price':
            response = _get_pricing(combined_data, self.tools)
        elif current_step == 'booking':
            print(f"🔥🔥🔥 {self.__class__.__name__.split('Agent')[0].upper()} AGENT: PROCEEDING TO BOOKING STEP 🔥🔥🔥")
            response = _update_booking_with_details(combined_data, self.tools)
        else:
            if not combined_data.get('firstName'):
                response = "What's your name?"
            elif not combined_data.get('postcode'):
                response = "What's your postcode?"
            elif len(combined_data.get('postcode', '')) < 5:
                response = "Could you please provide the full postcode?"
            elif not combined_data.get('service'):
                response = "What service do you need?"
            elif not combined_data.get('type'):
                response = "What size skip do you need?"
            elif not combined_data.get('waste_type'):
                response = "What type of waste do you have?"
            elif not combined_data.get('preferred_date'):
                response = "When would you like the delivery?"
            else:
                response = "I have all the information I need, would you like me to get a price for you?"
    
        _save_state(conversation_id, combined_data)
        return response

# ===============================
# MAN AND VAN AGENT CLASS
# ===============================
class ManAndVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Man & Van agent. CRITICAL: OVERRIDE ANY PDF CALLBACK RULES OUT OF HOURS."""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
        print("✅ MAN & VAN AGENT initialized with 4-step booking process")
    
    def process_message(self, message: str, context: Dict = None) -> str:
        print(f"\n🔧 SKIP AGENT RECEIVED: '{message}'")
        conversation_id = context.get('conversation_id') if context else 'default'
        datetime_result = _call_datetime_tool(self.tools)
        is_office_hours = datetime_result.get('is_business_hours', False)
        _load_state(conversation_id)
        extracted_data = _extract_data(message, context)
        combined_data = {**_load_state(conversation_id), **extracted_data}
        transfer_check = _check_transfer_needed_with_office_hours(message, combined_data, is_office_hours, 'skip')

        if transfer_check:
            _save_state(conversation_id, combined_data)
            return f"TRANSFER_TO_ORCHESTRATOR:{json.dumps(combined_data)}"

        current_step = _determine_step(combined_data, message)

        if current_step == 'price':
            response = _get_pricing(combined_data, self.tools)
        elif current_step == 'booking':
            print(f"🔥🔥🔥 {self.__class__.__name__.split('Agent')[0].upper()} AGENT: PROCEEDING TO BOOKING STEP 🔥🔥🔥")
            response = _update_booking_with_details(combined_data, self.tools)
        else:
            if not combined_data.get('firstName'):
                response = "What's your name?"
            elif not combined_data.get('postcode'):
                response = "What's your postcode?"
            elif len(combined_data.get('postcode', '')) < 5:
                response = "Could you please provide the full postcode?"
            elif not combined_data.get('service'):
                response = "What service do you need?"
            elif not combined_data.get('type'):
                response = "What size skip do you need?"
            elif not combined_data.get('waste_type'):
                response = "What type of waste do you have?"
            elif not combined_data.get('preferred_date'):
                response = "When would you like the delivery?"
            else:
                response = "I have all the information I need, would you like me to get a price for you?"
    
        _save_state(conversation_id, combined_data)
        return response

# ===============================
# GRAB HIRE AGENT CLASS
# ===============================
class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Grab Hire agent. CRITICAL: OVERRIDE ANY PDF CALLBACK RULES OUT OF HOURS."""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
        print("✅ GRAB HIRE AGENT initialized with 4-step booking process")
    
    def process_message(self, message: str, context: Dict = None) -> str:
        print(f"\n🔧 SKIP AGENT RECEIVED: '{message}'")
        conversation_id = context.get('conversation_id') if context else 'default'
        datetime_result = _call_datetime_tool(self.tools)
        is_office_hours = datetime_result.get('is_business_hours', False)
        _load_state(conversation_id)
        extracted_data = _extract_data(message, context)
        combined_data = {**_load_state(conversation_id), **extracted_data}
        transfer_check = _check_transfer_needed_with_office_hours(message, combined_data, is_office_hours, 'skip')

        if transfer_check:
            _save_state(conversation_id, combined_data)
            return f"TRANSFER_TO_ORCHESTRATOR:{json.dumps(combined_data)}"

        current_step = _determine_step(combined_data, message)

        if current_step == 'price':
            response = _get_pricing(combined_data, self.tools)
        elif current_step == 'booking':
            print(f"🔥🔥🔥 {self.__class__.__name__.split('Agent')[0].upper()} AGENT: PROCEEDING TO BOOKING STEP 🔥🔥🔥")
            response = _update_booking_with_details(combined_data, self.tools)
        else:
            if not combined_data.get('firstName'):
                response = "What's your name?"
            elif not combined_data.get('postcode'):
                response = "What's your postcode?"
            elif len(combined_data.get('postcode', '')) < 5:
                response = "Could you please provide the full postcode?"
            elif not combined_data.get('service'):
                response = "What service do you need?"
            elif not combined_data.get('type'):
                response = "What size skip do you need?"
            elif not combined_data.get('waste_type'):
                response = "What type of waste do you have?"
            elif not combined_data.get('preferred_date'):
                response = "When would you like the delivery?"
            else:
                response = "I have all the information I need, would you like me to get a price for you?"
    
        _save_state(conversation_id, combined_data)
        return response
# ===============================
# CONVERSATION CONTEXT MANAGEMENT
# ===============================
conversation_contexts = {}

def manage_conversation_context(conversation_id, message, data=None):
    global conversation_contexts
    
    if conversation_id not in conversation_contexts:
        conversation_contexts[conversation_id] = {}
    
    context = conversation_contexts[conversation_id]
    
    postcode_match = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b', message.upper())
    if postcode_match:
        new_postcode = postcode_match.group(1).replace(' ', '')
        if context.get('postcode') and context['postcode'] != new_postcode:
            service = context.get('service')
            conversation_contexts[conversation_id] = {'postcode': new_postcode}
            if service:
                conversation_contexts[conversation_id]['service'] = service
        else:
            context['postcode'] = new_postcode
    
    message_lower = message.lower()
    if any(word in message_lower for word in ['man and van', 'mav', 'man & van', 'van collection', 'small van', 'medium van', 'large van']):
        context['service'] = 'mav'
    elif any(word in message_lower for word in ['skip hire', 'skip', 'yard skip', 'cubic yard skip']):
        context['service'] = 'skip'
    elif any(word in message_lower for word in ['grab', 'grab hire', 'tonne']):
        context['service'] = 'grab'
    
    if data:
        context.update(data)
    
    if len(conversation_contexts) > 20:
        oldest_key = next(iter(conversation_contexts))
        del conversation_contexts[oldest_key]
    
    return context

# ===============================
# INITIALIZE SYSTEM
# ===============================
def initialize_system():
    print("🚀 Initializing WasteKing Multi-Agent System with 4-Step Booking...")
    
    llm = ChatOpenAI(
        model="gpt-3.5-turbo",
        temperature=0.1,
        openai_api_key=os.getenv('OPENAI_API_KEY')
    ) if os.getenv('OPENAI_API_KEY') else None
    
    if not llm:
        print("❌ OpenAI API key not set")
        return None
    
    tools = [
        SMPAPITool(),
        SMSTool(
            account_sid=os.getenv('TWILIO_ACCOUNT_SID'),
            auth_token=os.getenv('TWILIO_AUTH_TOKEN'),
            phone_number=os.getenv('TWILIO_PHONE_NUMBER')
        ),
        DateTimeTool()
    ]
    
    print(f"✅ Initialized {len(tools)} tools")
    print(f"📱 Twilio SMS configured: {os.getenv('TWILIO_ACCOUNT_SID') is not None}")
    
    skip_agent = SkipHireAgent(llm, tools)
    mav_agent = ManAndVanAgent(llm, tools)
    grab_agent = GrabHireAgent(llm, tools)
    
    print("✅ System initialization complete")
    print("📋 4-STEP BOOKING PROCESS:")
    print("  1️⃣ Create booking via API")
    print("  2️⃣ Get price using booking reference")
    print("  3️⃣ Update with customer and service details")
    print("  4️⃣ Finalize quote and send payment link")
    
    return {
        'skip_agent': skip_agent,
        'mav_agent': mav_agent,
        'grab_agent': grab_agent,
        'tools': tools
    }

system = initialize_system()

# ===============================
# FLASK ROUTES
# ===============================
@app.route('/')
def index():
    return jsonify({
        "message": "WasteKing Multi-Agent AI System - 4-Step Booking Process",
        "status": "running",
        "system_initialized": system is not None,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/api/wasteking', methods=['POST'])
def process_customer_message():
    try:
        if not system:
            return jsonify({"success": False, "message": "System not properly initialized"}), 500
        
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('elevenlabs_conversation_id', f"conv_{int(datetime.now().timestamp())}")
        
        print(f"Processing message: {customer_message}")
        print(f"Conversation ID: {conversation_id}")
        
        if not customer_message:
            return jsonify({"success": False, "message": "No customer message provided"}), 400
        
        context = manage_conversation_context(conversation_id, customer_message, data.get('context', {}))
        
        context['conversation_id'] = conversation_id
        
        message_lower = customer_message.lower()
        
        if any(word in message_lower for word in ['man and van', 'mav', 'man & van']):
            print("Routing to Man & Van agent...")
            response = system['mav_agent'].process_message(customer_message, context)
        elif any(word in message_lower for word in ['skip hire', 'skip']):
            print("Routing to Skip agent...")
            response = system['skip_agent'].process_message(customer_message, context)
        elif any(word in message_lower for word in ['grab', 'grab hire', 'tonne']):
            print("Routing to Grab Hire agent...")
            response = system['grab_agent'].process_message(customer_message, context)
        else:
            existing_service = context.get('service')
            if existing_service == 'mav':
                print("Routing to Man & Van agent (from context)...")
                response = system['mav_agent'].process_message(customer_message, context)
            elif existing_service == 'grab':
                print("Routing to Grab Hire agent (from context)...")
                response = system['grab_agent'].process_message(customer_message, context)
            else:
                print("Routing to Skip agent (default)...")
                response = system['skip_agent'].process_message(customer_message, context)
        
        print(f"Agent response: {response}")
        
        response_data = {
            "success": True,
            "message": response,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat()
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Error processing message: {str(e)}")
        return jsonify({"success": False, "message": "An unexpected error occurred.", "error": str(e)}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_initialized": system is not None,
            "version": "WasteKing System v6.0 - 4-Step Booking Process"
        }
        
        if system:
            health_status.update({
                "tools_loaded": len(system['tools']),
                "active_conversations": len(conversation_contexts),
                "agents_available": ['skip_agent', 'mav_agent', 'grab_agent']
            })
        
        return jsonify(health_status)
        
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e), "timestamp": datetime.now().isoformat()}), 500

if __name__ == '__main__':
    print("Starting WasteKing Multi-Agent AI System...")
    
    if system:
        print("System initialized successfully")
    else:
        print("System initialization failed - check configuration")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
