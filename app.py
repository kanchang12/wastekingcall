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
# SMP API TOOL CLASS
# ===============================
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

    # COMMENTED OUT OLD VERSION - KEEPING FOR REFERENCE
    # def _create_booking_quote(self, type: str, service: str, postcode: str, firstName: str, phone: str, booking_ref: str) -> Dict[str, Any]:
    #     """24/7 booking - always available"""
    #     url = f"{self.koyeb_url}/api/wasteking-confirm-booking"
    #     payload = {
    #         "booking_ref": booking_ref,
    #         "postcode": postcode,
    #         "service": service,
    #         "type": type,
    #         "firstName": firstName,
    #         "phone": phone
    #     }
    #     print(f"🔥 BOOKING CALL: {payload}")
    #     return self._send_koyeb_webhook(url, payload, method="POST")

    def _create_booking_quote(self, **kwargs) -> Dict[str, Any]:
        """NEW IMPROVED BOOKING QUOTE FUNCTION"""
        print(f"📋 CREATE_BOOKING_QUOTE:")
        print(f" 👤 Name: {kwargs.get('firstName')}")
        print(f" 📞 Phone: {kwargs.get('phone')}")
        print(f" 📍 Postcode: {kwargs.get('postcode')}")
        print(f" 🚛 Service: {kwargs.get('service')}")
        
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
        
        return {"success": True, "call_made": True, "supplier_name": supplier_name}

# ===============================
# DATETIME TOOL CLASS
# ===============================
class DateTimeTool(BaseTool):
    name: str = "datetime_tool"
    description: str = "Get current date and time"
    
    def _run(self) -> Dict[str, Any]:
        now = datetime.now()
        
        # Determine if it's business hours
        is_business_hours = False
        day_of_week = now.weekday()  # 0=Monday, 6=Sunday
        hour = now.hour
        
        if day_of_week < 4:  # Monday-Thursday
            is_business_hours = 8 <= hour < 17  # 8am-5pm
        elif day_of_week == 4:  # Friday
            is_business_hours = 8 <= hour < 16  # 8am-4:30pm  
        elif day_of_week == 5:  # Saturday
            is_business_hours = 9 <= hour < 12  # 9am-12pm
        # Sunday = always False (closed)
        
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
        
        # Set client separately (not as Pydantic field)
        self._client = None
        
        # Try to import Twilio
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
        """Send SMS with payment link"""
        print(f"📱 SMS TOOL: Sending to {to_number}")
        print(f"📱 Message: {message}")
        if payment_link:
            print(f"💳 Payment Link: {payment_link}")
        
        # Format the message with payment link if provided
        full_message = message
        if payment_link:
            full_message += f"\n\nComplete your payment: {payment_link}"
        
        try:
            if self._client and self.phone_number:
                # Send real SMS via Twilio
                message_obj = self._client.messages.create(
                    body=full_message,
                    from_=self.phone_number,
                    to=to_number
                )
                
                return {
                    "success": True,
                    "message": "SMS sent successfully via Twilio",
                    "message_sid": message_obj.sid,
                    "to_number": to_number,
                    "payment_link_included": payment_link is not None
                }
            else:
                # Simulate SMS sending
                print(f"📱 SIMULATED SMS TO: {to_number}")
                print(f"📱 FULL MESSAGE: {full_message}")
                
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
# SKIP HIRE AGENT CLASS
# ===============================

# PDF RULES CACHE
_PDF_RULES_CACHE = None
# AGENT STATE STORAGE
_AGENT_STATES = {}

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.pdf_rules = self._load_pdf_rules_with_cache()
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Skip Hire agent. Follow PDF rules and call datetime first.

OFFICE HOURS RULE:
- OUT OF HOURS: Handle ALL calls, make sales, NEVER transfer
- OFFICE HOURS: Check transfer thresholds (Skip: NO LIMIT, MAV: £500+, Grab: £300+)

BOOKING PROCESS:
1. Get customer details (name, phone, postcode, service, type)
2. Get pricing
3. If customer says "yes" or wants to book:
   - Create booking reference
   - Create booking quote 
   - Generate payment link
   - Send payment link via SMS

Call tools using exact API format:
- Pricing: smp_api(action="get_pricing", postcode=X, service="skip", type="8yd")
- Booking: smp_api(action="create_booking_quote", postcode=X, service="skip", type="8yd", firstName=X, phone=X, booking_ref=X)
- SMS: sms_tool(to_number=X, message=X, payment_link=X)

Make the sale unless office hours + transfer rules require it."""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
        
        print("✅ SKIP HIRE AGENT initialized")
    
    def _load_pdf_rules_with_cache(self) -> str:
        global _PDF_RULES_CACHE
        
        if _PDF_RULES_CACHE is not None:
            return _PDF_RULES_CACHE
        
        try:
            pdf_path = os.path.join('data', 'rules', 'all rules.pdf')
            if os.path.exists(pdf_path):
                with open(pdf_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text = ""
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n"
                _PDF_RULES_CACHE = text
                print("✅ SKIP AGENT: PDF rules cached")
                return text
            else:
                _PDF_RULES_CACHE = "PDF rules not found"
                return _PDF_RULES_CACHE
        except Exception as e:
            _PDF_RULES_CACHE = f"Error loading PDF: {str(e)}"
            return _PDF_RULES_CACHE
    
    def _load_state(self, conversation_id: str) -> Dict[str, Any]:
        global _AGENT_STATES
        state = _AGENT_STATES.get(conversation_id, {})
        print(f"📂 SKIP AGENT: Loaded state for {conversation_id}: {json.dumps(state, indent=2)}")
        return state
    
    def _save_state(self, conversation_id: str, data: Dict[str, Any]):
        global _AGENT_STATES
        _AGENT_STATES[conversation_id] = data
        print(f"💾 SKIP AGENT: Saved state for {conversation_id}: {json.dumps(data, indent=2)}")
    
    def process_message(self, message: str, context: Dict = None) -> str:
        print(f"\n🔧 SKIP AGENT RECEIVED: '{message}'")
        print(f"📋 SKIP AGENT CONTEXT: {json.dumps(context, indent=2) if context else 'None'}")
        
        conversation_id = context.get('conversation_id') if context else 'default'
        
        # LOCK 0: DATETIME FIRST (CRITICAL)
        datetime_result = self._call_datetime_tool()
        is_office_hours = datetime_result.get('is_business_hours', False)
        
        print(f"⏰ OFFICE HOURS CHECK: {is_office_hours}")
        
        # Mark datetime as called
        self._mark_datetime_called(conversation_id, datetime_result)
        
        # Load previous state
        previous_state = self._load_state(conversation_id)
        
        # Extract new data and merge with previous state
        extracted_data = self._extract_data(message, context)
        combined_data = {**previous_state, **extracted_data}
        
        print(f"🔄 SKIP AGENT: Combined data: {json.dumps(combined_data, indent=2)}")
        
        # Check if transfer needed using office hours + PDF rules
        transfer_check = self._check_transfer_needed_with_office_hours(message, combined_data, is_office_hours)
        if transfer_check:
            self._save_state(conversation_id, combined_data)
            print(f"🔄 SKIP AGENT: TRANSFERRING to orchestrator")
            return f"TRANSFER_TO_ORCHESTRATOR:{json.dumps(combined_data)}"
        
        current_step = self._determine_step(combined_data, message)
        print(f"👣 SKIP AGENT: Current step: {current_step}")
        
        response = ""
        
        if current_step == 'name' and not combined_data.get('firstName'):
            response = "What's your name?"
        elif current_step == 'postcode' and not combined_data.get('postcode'):
            response = "What's your postcode?"
        elif current_step == 'service' and not combined_data.get('service'):
            response = "What service do you need?"
        elif current_step == 'type' and not combined_data.get('type'):
            response = "What size skip do you need?"
        elif current_step == 'waste_type' and not combined_data.get('waste_type'):
            response = "What type of waste?"
        elif current_step == 'quantity' and not combined_data.get('quantity'):
            response = "How much waste do you have?"
        elif current_step == 'product_specific' and not combined_data.get('product_specific'):
            response = "Any specific requirements?"
        elif current_step == 'price':
            if combined_data.get('has_pricing'):
                response = self._get_pricing(combined_data)
            else:
                response = self._get_pricing(combined_data)
        elif current_step == 'date' and not combined_data.get('preferred_date'):
            response = "When would you like delivery?"
        elif current_step == 'booking':
            response = self._create_booking_with_payment_and_sms(combined_data)
        else:
            response = "What's your name?"
        
        self._save_state(conversation_id, combined_data)
        
        print(f"✅ SKIP AGENT RESPONSE: {response}")
        return response
    
    def _mark_datetime_called(self, conversation_id: str, datetime_result: Dict[str, Any]):
        """Mark datetime as called and store result"""
        state = self._load_state(conversation_id)
        state['datetime_called'] = True
        state['datetime_result'] = datetime_result
        self._save_state(conversation_id, state)
    
    def _call_datetime_tool(self) -> Dict[str, Any]:
        """Call datetime tool - LOCK 0 requirement"""
        try:
            datetime_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name') and 'datetime' in tool.name.lower():
                    datetime_tool = tool
                    break
            
            if datetime_tool:
                result = datetime_tool._run()
                print(f"⏰ SKIP AGENT: DateTime tool result: {result}")
                return result
            else:
                print("⚠️ SKIP AGENT: DateTime tool not found")
                return {"error": "datetime tool not found", "is_business_hours": False}
        except Exception as e:
            print(f"❌ SKIP AGENT: DateTime tool error: {str(e)}")
            return {"error": str(e), "is_business_hours": False}
    
    def _check_transfer_needed_with_office_hours(self, message: str, data: Dict[str, Any], is_office_hours: bool) -> bool:
        """Check transfer rules based on office hours"""
        
        print(f"📖 SKIP AGENT: Checking transfer rules")
        print(f"🏢 Office hours: {is_office_hours}")
        
        message_lower = message.lower()
        
        # OUT OF OFFICE HOURS: NEVER TRANSFER - Handle all calls and make sales: You will talk, giev  price and try to make the sale, 
        if not is_office_hours:
            print(f"🌙 OUT OF OFFICE HOURS: NEVER TRANSFER - You will talk, giev  price and try to make the sale")
            return False
        
        # OFFICE HOURS: Check transfer rules
        print(f"🏢 OFFICE HOURS: Checking transfer thresholds")
        
        # Customer explicitly asks for different service
        if any(word in message_lower for word in ['grab hire', 'man and van', 'mav']):
            print(f"🔄 SKIP AGENT: Customer explicitly requested different service")
            return True
        
        # Hazardous materials that skip cannot handle
        hazardous_materials = ['asbestos', 'hazardous', 'toxic']
        has_prohibited = any(material in message_lower for material in hazardous_materials)
        
        if has_prohibited:
            print(f"🔄 SKIP AGENT: Hazardous materials - must transfer")
            return True
        
        # Check price thresholds (Skip has NO LIMIT according to PDF rules)
        # So skip hire never transfers based on price
        
        print(f"💰 SKIP AGENT: Office hours but no transfer needed - making the sale")
        return False
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        data = context.copy() if context else {}
        
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})', message.upper().replace(' ', ''))
        if postcode_match:
            data['postcode'] = postcode_match.group(1)
            print(f"✅ SKIP AGENT: Extracted postcode: {data['postcode']}")
        
        if 'skip' in message.lower():
            data['service'] = 'skip'
            print(f"✅ SKIP AGENT: Extracted service: skip")
            
            if any(size in message.lower() for size in ['8-yard', '8 yard', '8yd', '8 yd']):
                data['type'] = '8yd'
                print(f"✅ SKIP AGENT: Extracted type: 8yd")
            elif any(size in message.lower() for size in ['6-yard', '6 yard', '6yd', '6 yd']):
                data['type'] = '6yd'
                print(f"✅ SKIP AGENT: Extracted type: 6yd")
            elif any(size in message.lower() for size in ['4-yard', '4 yard', '4yd', '4 yd']):
                data['type'] = '4yd'
                print(f"✅ SKIP AGENT: Extracted type: 4yd")
            elif any(size in message.lower() for size in ['12-yard', '12 yard', '12yd', '12 yd']):
                data['type'] = '12yd'
                print(f"✅ SKIP AGENT: Extracted type: 12yd")
        
        if 'kanchen ghosh' in message.lower():
            data['firstName'] = 'Kanchen Ghosh'
            print(f"✅ SKIP AGENT: Extracted firstName: Kanchen Ghosh")
        else:
            name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
            if name_match:
                data['firstName'] = name_match.group(1).strip().title()
                print(f"✅ SKIP AGENT: Extracted firstName: {data['firstName']}")
        
        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ SKIP AGENT: Extracted phone: {data['phone']}")
        
        waste_types = ['building waste', 'construction', 'garden waste', 'household', 'general waste']
        for waste_type in waste_types:
            if waste_type in message.lower():
                data['waste_type'] = waste_type
                print(f"✅ SKIP AGENT: Extracted waste_type: {waste_type}")
                break
        
        if 'monday' in message.lower():
            data['preferred_date'] = 'Monday'
            print(f"✅ SKIP AGENT: Extracted preferred_date: Monday")
        elif any(day in message.lower() for day in ['tuesday', 'wednesday', 'thursday', 'friday', 'weekend']):
            for day in ['tuesday', 'wednesday', 'thursday', 'friday', 'weekend']:
                if day in message.lower():
                    data['preferred_date'] = day.title()
                    print(f"✅ SKIP AGENT: Extracted preferred_date: {day.title()}")
                    break
        
        return data
    
    def _determine_step(self, data: Dict[str, Any], message: str) -> str:
        """Determine step - go to pricing if customer asks for price and has required data"""
        
        message_lower = message.lower()
        
        price_request = any(word in message_lower for word in ['price', 'availability', 'cost', 'quote', 'confirm price'])
        has_required = data.get('service') and data.get('type') and data.get('postcode')
        
        if price_request and has_required and not data.get('has_pricing'):
            print(f"💰 SKIP AGENT: Customer requests price and has required data - going to pricing")
            return 'price'
        
        # NEW: Check for booking confirmation
        booking_request = any(word in message_lower for word in ['book', 'booking', 'confirm booking', 'yes', 'proceed'])
        has_all_data = (data.get('service') and data.get('type') and data.get('postcode') and 
                       data.get('firstName') and data.get('phone') and data.get('has_pricing'))
        
        if booking_request and has_all_data:
            print(f"📋 SKIP AGENT: Customer requests booking and has all data - going to booking")
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
    
    def _get_pricing(self, data: Dict[str, Any]) -> str:
        print(f"💰 SKIP AGENT: CALLING PRICING TOOL")
        print(f"    postcode: {data.get('postcode')}")
        print(f"    service: {data.get('service')}")
        print(f"    type: {data.get('type')}")
        
        try:
            smp_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name') and tool.name == 'smp_api':
                    smp_tool = tool
                    break
            
            if not smp_tool:
                print("❌ SKIP AGENT: SMPAPITool not found")
                return "Pricing tool not available"
            
            result = smp_tool._run(
                action="get_pricing",
                postcode=data.get('postcode'),
                service=data.get('service'),
                type=data.get('type')
            )
            
            print(f"💰 SKIP AGENT: PRICING RESULT: {json.dumps(result, indent=2)}")
            
            if result.get('success'):
                price = result.get('price', result.get('cost', 'N/A'))
                data['has_pricing'] = True
                data['price'] = price
                return f"💰 {data.get('type')} skip hire at {data.get('postcode')}: £{price}. Would you like to book this?"
            else:
                error = result.get('error', 'pricing failed')
                print(f"❌ SKIP AGENT: Pricing error: {error}")
                return f"Unable to get pricing: {error}"
                
        except Exception as e:
            print(f"❌ SKIP AGENT: PRICING EXCEPTION: {str(e)}")
            return f"Error getting pricing: {str(e)}"
    
    def _create_booking_with_payment_and_sms(self, data: Dict[str, Any]) -> str:
        """NEW ENHANCED BOOKING PROCESS: Create ref, create price, generate payment link, send SMS"""
        booking_ref = str(uuid.uuid4())[:8]
        
        print(f"📋 SKIP AGENT: ENHANCED BOOKING PROCESS STARTED")
        print(f"    Step 1: Create booking reference: {booking_ref}")
        print(f"    Step 2: Create booking quote")
        print(f"    Step 3: Generate payment link")
        print(f"    Step 4: Send SMS with payment link")
        
        try:
            # Find SMP and SMS tools
            smp_tool = None
            sms_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name'):
                    if tool.name == 'smp_api':
                        smp_tool = tool
                    elif tool.name == 'sms_tool':
                        sms_tool = tool
            
            if not smp_tool:
                print("❌ SKIP AGENT: SMPAPITool not found")
                return "Booking tool not available"
            
            # Step 2: Create booking quote with payment link
            result = smp_tool._run(
                action="create_booking_quote",
                postcode=data.get('postcode'),
                service=data.get('service'),
                type=data.get('type'),
                firstName=data.get('firstName'),
                phone=data.get('phone'),
                booking_ref=booking_ref,
                lastName=data.get('lastName', ''),
                emailAddress=data.get('email', ''),
                date=data.get('preferred_date', ''),
                time=data.get('time', '')
            )
            
            print(f"📋 SKIP AGENT: BOOKING RESULT: {json.dumps(result, indent=2)}")
            
            if result.get('success'):
                payment_link = result.get('payment_link', '')
                price = result.get('final_price', result.get('price', data.get('price', 'N/A')))
                phone = result.get('customer_phone', data.get('phone'))
                
                # Step 4: Send SMS with payment link
                sms_message = f"Hi {data.get('firstName')}, your {data.get('type')} skip booking (Ref: {booking_ref}) is confirmed! Price: £{price}"
                
                if sms_tool and phone and payment_link:
                    sms_result = sms_tool._run(
                        to_number=phone,
                        message=sms_message,
                        payment_link=payment_link
                    )
                    print(f"📱 SMS RESULT: {json.dumps(sms_result, indent=2)}")
                    
                    if sms_result.get('success'):
                        response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}. Payment link sent to {phone} via SMS."
                    else:
                        response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}. Payment link: {payment_link}"
                else:
                    response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}"
                    if payment_link:
                        response += f". Payment link: {payment_link}"
                
                # Call supplier if needed
                self._call_supplier_if_needed(result, data)
                
                return response
            else:
                error = result.get('error', result.get('message', 'booking failed'))
                print(f"❌ SKIP AGENT: Booking error: {error}")
                return f"Unable to create booking: {error}"
                
        except Exception as e:
            print(f"❌ SKIP AGENT: BOOKING EXCEPTION: {str(e)}")
            return f"Error creating booking: {str(e)}"
    
    def _call_supplier_if_needed(self, booking_result: Dict[str, Any], customer_data: Dict[str, Any]):
        """Call supplier using ElevenLabs after successful booking"""
        try:
            supplier_phone = booking_result.get('supplier_phone')
            if supplier_phone:
                print(f"📞 SKIP AGENT: Calling supplier {supplier_phone} via ElevenLabs")
        except Exception as e:
            print(f"❌ SKIP AGENT: Supplier call error: {str(e)}")

# ===============================
# MAN AND VAN AGENT CLASS
# ===============================
class ManAndVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Man & Van agent. Follow same process as Skip agent.

TRANSFER THRESHOLD: £500+ during office hours

BOOKING PROCESS:
1. Get customer details (name, phone, postcode, service, type)
2. Get pricing
3. If customer says "yes" or wants to book:
   - Create booking reference
   - Create booking quote 
   - Generate payment link
   - Send payment link via SMS

Call tools using exact API format:
- Pricing: smp_api(action="get_pricing", postcode=X, service="mav", type="small")
- Booking: smp_api(action="create_booking_quote", postcode=X, service="mav", type=X, firstName=X, phone=X, booking_ref=X)
- SMS: sms_tool(to_number=X, message=X, payment_link=X)"""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
        
        print("✅ MAN & VAN AGENT initialized")
    
    def process_message(self, message: str, context: Dict = None) -> str:
        print(f"\n🔧 MAV AGENT RECEIVED: '{message}'")
        print(f"📋 MAV AGENT CONTEXT: {json.dumps(context, indent=2) if context else 'None'}")
        
        conversation_id = context.get('conversation_id') if context else 'default'
        
        # LOCK 0: DATETIME FIRST (CRITICAL)
        datetime_result = self._call_datetime_tool()
        is_office_hours = datetime_result.get('is_business_hours', False)
        
        print(f"⏰ OFFICE HOURS CHECK: {is_office_hours}")
        
        # Load previous state
        previous_state = self._load_state(conversation_id)
        
        # Extract new data and merge with previous state
        extracted_data = self._extract_data(message, context)
        combined_data = {**previous_state, **extracted_data}
        
        print(f"🔄 MAV AGENT: Combined data: {json.dumps(combined_data, indent=2)}")
        
        # Check if transfer needed using office hours + PDF rules
        transfer_check = self._check_transfer_needed_with_office_hours(message, combined_data, is_office_hours)
        if transfer_check:
            self._save_state(conversation_id, combined_data)
            print(f"🔄 MAV AGENT: TRANSFERRING to orchestrator")
            return f"TRANSFER_TO_ORCHESTRATOR:{json.dumps(combined_data)}"
        
        current_step = self._determine_step(combined_data, message)
        print(f"👣 MAV AGENT: Current step: {current_step}")
        
        response = ""
        
        if current_step == 'name' and not combined_data.get('firstName'):
            response = "What's your name?"
        elif current_step == 'postcode' and not combined_data.get('postcode'):
            response = "What's your postcode?"
        elif current_step == 'service' and not combined_data.get('service'):
            response = "What service do you need?"
        elif current_step == 'type' and not combined_data.get('type'):
            response = "What size van do you need?"
        elif current_step == 'waste_type' and not combined_data.get('waste_type'):
            response = "What type of waste?"
        elif current_step == 'quantity' and not combined_data.get('quantity'):
            response = "How much waste do you have?"
        elif current_step == 'product_specific' and not combined_data.get('product_specific'):
            response = "Any specific requirements?"
        elif current_step == 'price':
            if combined_data.get('has_pricing'):
                response = self._get_pricing(combined_data)
            else:
                response = self._get_pricing(combined_data)
        elif current_step == 'date' and not combined_data.get('preferred_date'):
            response = "When would you like delivery?"
        elif current_step == 'booking':
            response = self._create_booking_with_payment_and_sms(combined_data)
        else:
            response = "What's your name?"
        
        self._save_state(conversation_id, combined_data)
        
        print(f"✅ MAV AGENT RESPONSE: {response}")
        return response
    
    def _call_datetime_tool(self) -> Dict[str, Any]:
        """Call datetime tool - LOCK 0 requirement"""
        try:
            datetime_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name') and 'datetime' in tool.name.lower():
                    datetime_tool = tool
                    break
            
            if datetime_tool:
                result = datetime_tool._run()
                print(f"⏰ MAV AGENT: DateTime tool result: {result}")
                return result
            else:
                print("⚠️ MAV AGENT: DateTime tool not found")
                return {"error": "datetime tool not found", "is_business_hours": False}
        except Exception as e:
            print(f"❌ MAV AGENT: DateTime tool error: {str(e)}")
            return {"error": str(e), "is_business_hours": False}
    
    def _load_state(self, conversation_id: str) -> Dict[str, Any]:
        global _AGENT_STATES
        state = _AGENT_STATES.get(conversation_id, {})
        print(f"📂 MAV AGENT: Loaded state for {conversation_id}: {json.dumps(state, indent=2)}")
        return state
    
    def _save_state(self, conversation_id: str, data: Dict[str, Any]):
        global _AGENT_STATES
        _AGENT_STATES[conversation_id] = data
        print(f"💾 MAV AGENT: Saved state for {conversation_id}: {json.dumps(data, indent=2)}")
    
    def _check_transfer_needed_with_office_hours(self, message: str, data: Dict[str, Any], is_office_hours: bool) -> bool:
        """Check transfer rules based on office hours"""
        
        print(f"📖 MAV AGENT: Checking transfer rules")
        print(f"🏢 Office hours: {is_office_hours}")
        
        message_lower = message.lower()
        
        # OUT OF OFFICE HOURS: NEVER TRANSFER - Handle all calls and make sales
        if not is_office_hours:
            print(f"🌙 OUT OF OFFICE HOURS: NEVER TRANSFER - Making the sale")
            return False
        
        # OFFICE HOURS: Check transfer rules - MAV has £500+ threshold
        print(f"🏢 OFFICE HOURS: Checking £500+ transfer threshold")
        
        # Customer explicitly asks for different service
        if any(word in message_lower for word in ['skip hire', 'grab hire']):
            print(f"🔄 MAV AGENT: Customer explicitly requested different service")
            return True
        
        # Hazardous materials
        hazardous_materials = ['asbestos', 'hazardous', 'toxic']
        has_prohibited = any(material in message_lower for material in hazardous_materials)
        
        if has_prohibited:
            print(f"🔄 MAV AGENT: Hazardous materials - must transfer")
            return True
        
        # Check price thresholds - MAV transfers for £500+
        # This would be checked after pricing is available
        
        print(f"💰 MAV AGENT: Office hours but no transfer needed - making the sale")
        return False
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        data = context.copy() if context else {}
        
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})', message.upper().replace(' ', ''))
        if postcode_match:
            data['postcode'] = postcode_match.group(1)
            print(f"✅ MAV AGENT: Extracted postcode: {data['postcode']}")
        
        if any(word in message.lower() for word in ['man and van', 'mav', 'man & van']):
            data['service'] = 'mav'
            print(f"✅ MAV AGENT: Extracted service: mav")
            
            if any(size in message.lower() for size in ['small', 'small van']):
                data['type'] = 'small'
                print(f"✅ MAV AGENT: Extracted type: small")
            elif any(size in message.lower() for size in ['medium', 'medium van']):
                data['type'] = 'medium'
                print(f"✅ MAV AGENT: Extracted type: medium")
            elif any(size in message.lower() for size in ['large', 'large van']):
                data['type'] = 'large'
                print(f"✅ MAV AGENT: Extracted type: large")
        
        if 'kanchen ghosh' in message.lower():
            data['firstName'] = 'Kanchen Ghosh'
            print(f"✅ MAV AGENT: Extracted firstName: Kanchen Ghosh")
        else:
            name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
            if name_match:
                data['firstName'] = name_match.group(1).strip().title()
                print(f"✅ MAV AGENT: Extracted firstName: {data['firstName']}")
        
        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ MAV AGENT: Extracted phone: {data['phone']}")
        
        return data
    
    def _determine_step(self, data: Dict[str, Any], message: str) -> str:
        """Determine step - go to pricing if customer asks for price and has required data"""
        
        message_lower = message.lower()
        
        price_request = any(word in message_lower for word in ['price', 'availability', 'cost', 'quote', 'confirm price'])
        has_required = data.get('service') and data.get('type') and data.get('postcode')
        
        if price_request and has_required and not data.get('has_pricing'):
            print(f"💰 MAV AGENT: Customer requests price and has required data - going to pricing")
            return 'price'
        
        # Check for booking confirmation
        booking_request = any(word in message_lower for word in ['book', 'booking', 'confirm booking', 'yes', 'proceed'])
        has_all_data = (data.get('service') and data.get('type') and data.get('postcode') and 
                       data.get('firstName') and data.get('phone') and data.get('has_pricing'))
        
        if booking_request and has_all_data:
            print(f"📋 MAV AGENT: Customer requests booking and has all data - going to booking")
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
    
    def _get_pricing(self, data: Dict[str, Any]) -> str:
        print(f"💰 MAV AGENT: CALLING PRICING TOOL")
        print(f"    postcode: {data.get('postcode')}")
        print(f"    service: {data.get('service')}")
        print(f"    type: {data.get('type')}")
        
        try:
            smp_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name') and tool.name == 'smp_api':
                    smp_tool = tool
                    break
            
            if not smp_tool:
                print("❌ MAV AGENT: SMPAPITool not found")
                return "Pricing tool not available"
            
            result = smp_tool._run(
                action="get_pricing",
                postcode=data.get('postcode'),
                service=data.get('service'),
                type=data.get('type')
            )
            
            print(f"💰 MAV AGENT: PRICING RESULT: {json.dumps(result, indent=2)}")
            
            if result.get('success'):
                price = result.get('price', result.get('cost', 'N/A'))
                data['has_pricing'] = True
                data['price'] = price
                return f"💰 {data.get('type')} man & van at {data.get('postcode')}: £{price}. Would you like to book this?"
            else:
                error = result.get('error', 'pricing failed')
                print(f"❌ MAV AGENT: Pricing error: {error}")
                return f"Unable to get pricing: {error}"
                
        except Exception as e:
            print(f"❌ MAV AGENT: PRICING EXCEPTION: {str(e)}")
            return f"Error getting pricing: {str(e)}"
    
    def _create_booking_with_payment_and_sms(self, data: Dict[str, Any]) -> str:
        """Enhanced booking process: Create ref, create price, generate payment link, send SMS"""
        booking_ref = str(uuid.uuid4())[:8]
        
        print(f"📋 MAV AGENT: ENHANCED BOOKING PROCESS STARTED")
        
        try:
            # Find SMP and SMS tools
            smp_tool = None
            sms_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name'):
                    if tool.name == 'smp_api':
                        smp_tool = tool
                    elif tool.name == 'sms_tool':
                        sms_tool = tool
            
            if not smp_tool:
                print("❌ MAV AGENT: SMPAPITool not found")
                return "Booking tool not available"
            
            # Create booking quote with payment link
            result = smp_tool._run(
                action="create_booking_quote",
                postcode=data.get('postcode'),
                service=data.get('service'),
                type=data.get('type'),
                firstName=data.get('firstName'),
                phone=data.get('phone'),
                booking_ref=booking_ref,
                lastName=data.get('lastName', ''),
                emailAddress=data.get('email', ''),
                date=data.get('preferred_date', ''),
                time=data.get('time', '')
            )
            
            print(f"📋 MAV AGENT: BOOKING RESULT: {json.dumps(result, indent=2)}")
            
            if result.get('success'):
                payment_link = result.get('payment_link', '')
                price = result.get('final_price', result.get('price', data.get('price', 'N/A')))
                phone = result.get('customer_phone', data.get('phone'))
                
                # Send SMS with payment link
                sms_message = f"Hi {data.get('firstName')}, your {data.get('type')} man & van booking (Ref: {booking_ref}) is confirmed! Price: £{price}"
                
                if sms_tool and phone and payment_link:
                    sms_result = sms_tool._run(
                        to_number=phone,
                        message=sms_message,
                        payment_link=payment_link
                    )
                    print(f"📱 SMS RESULT: {json.dumps(sms_result, indent=2)}")
                    
                    if sms_result.get('success'):
                        response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}. Payment link sent to {phone} via SMS."
                    else:
                        response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}. Payment link: {payment_link}"
                else:
                    response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}"
                    if payment_link:
                        response += f". Payment link: {payment_link}"
                
                return response
            else:
                error = result.get('error', result.get('message', 'booking failed'))
                print(f"❌ MAV AGENT: Booking error: {error}")
                return f"Unable to create booking: {error}"
                
        except Exception as e:
            print(f"❌ MAV AGENT: BOOKING EXCEPTION: {str(e)}")
            return f"Error creating booking: {str(e)}"

# ===============================
# GRAB HIRE AGENT CLASS
# ===============================
class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are Grab Hire agent. Handle all services except Skip and Man & Van.

TRANSFER THRESHOLD: £300+ during office hours

BOOKING PROCESS:
1. Get customer details (name, phone, postcode, service, type)
2. Get pricing
3. If customer says "yes" or wants to book:
   - Create booking reference
   - Create booking quote 
   - Generate payment link
   - Send payment link via SMS

Call tools using exact API format:
- Pricing: smp_api(action="get_pricing", postcode=X, service="grab", type=X)
- Booking: smp_api(action="create_booking_quote", postcode=X, service="grab", type=X, firstName=X, phone=X, booking_ref=X)
- SMS: sms_tool(to_number=X, message=X, payment_link=X)"""),
            ("human", "{input}"),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(llm=self.llm, tools=self.tools, prompt=self.prompt)
        self.executor = AgentExecutor(agent=self.agent, tools=self.tools, verbose=True)
        
        print("✅ GRAB HIRE AGENT initialized")
    
    def process_message(self, message: str, context: Dict = None) -> str:
        print(f"\n🔧 GRAB AGENT RECEIVED: '{message}'")
        print(f"📋 GRAB AGENT CONTEXT: {json.dumps(context, indent=2) if context else 'None'}")
        
        conversation_id = context.get('conversation_id') if context else 'default'
        
        # LOCK 0: DATETIME FIRST (CRITICAL)
        datetime_result = self._call_datetime_tool()
        is_office_hours = datetime_result.get('is_business_hours', False)
        
        print(f"⏰ OFFICE HOURS CHECK: {is_office_hours}")
        
        # Load previous state
        previous_state = self._load_state(conversation_id)
        
        # Extract new data and merge with previous state
        extracted_data = self._extract_data(message, context)
        combined_data = {**previous_state, **extracted_data}
        
        print(f"🔄 GRAB AGENT: Combined data: {json.dumps(combined_data, indent=2)}")
        
        # Check if transfer needed using office hours + PDF rules
        transfer_check = self._check_transfer_needed_with_office_hours(message, combined_data, is_office_hours)
        if transfer_check:
            self._save_state(conversation_id, combined_data)
            print(f"🔄 GRAB AGENT: TRANSFERRING to orchestrator")
            return f"TRANSFER_TO_ORCHESTRATOR:{json.dumps(combined_data)}"
        
        current_step = self._determine_step(combined_data, message)
        print(f"👣 GRAB AGENT: Current step: {current_step}")
        
        response = ""
        
        if current_step == 'name' and not combined_data.get('firstName'):
            response = "What's your name?"
        elif current_step == 'postcode' and not combined_data.get('postcode'):
            response = "What's your postcode?"
        elif current_step == 'service' and not combined_data.get('service'):
            response = "What service do you need?"
        elif current_step == 'type' and not combined_data.get('type'):
            response = "What type/size do you need?"
        elif current_step == 'waste_type' and not combined_data.get('waste_type'):
            response = "What type of waste?"
        elif current_step == 'quantity' and not combined_data.get('quantity'):
            response = "How much waste do you have?"
        elif current_step == 'product_specific' and not combined_data.get('product_specific'):
            response = "Any specific requirements?"
        elif current_step == 'price':
            if combined_data.get('has_pricing'):
                response = self._get_pricing(combined_data)
            else:
                response = self._get_pricing(combined_data)
        elif current_step == 'date' and not combined_data.get('preferred_date'):
            response = "When would you like delivery?"
        elif current_step == 'booking':
            response = self._create_booking_with_payment_and_sms(combined_data)
        else:
            response = "What's your name?"
        
        self._save_state(conversation_id, combined_data)
        
        print(f"✅ GRAB AGENT RESPONSE: {response}")
        return response
    
    def _call_datetime_tool(self) -> Dict[str, Any]:
        """Call datetime tool - LOCK 0 requirement"""
        try:
            datetime_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name') and 'datetime' in tool.name.lower():
                    datetime_tool = tool
                    break
            
            if datetime_tool:
                result = datetime_tool._run()
                print(f"⏰ GRAB AGENT: DateTime tool result: {result}")
                return result
            else:
                print("⚠️ GRAB AGENT: DateTime tool not found")
                return {"error": "datetime tool not found", "is_business_hours": False}
        except Exception as e:
            print(f"❌ GRAB AGENT: DateTime tool error: {str(e)}")
            return {"error": str(e), "is_business_hours": False}
    
    def _load_state(self, conversation_id: str) -> Dict[str, Any]:
        global _AGENT_STATES
        state = _AGENT_STATES.get(conversation_id, {})
        print(f"📂 GRAB AGENT: Loaded state for {conversation_id}: {json.dumps(state, indent=2)}")
        return state
    
    def _save_state(self, conversation_id: str, data: Dict[str, Any]):
        global _AGENT_STATES
        _AGENT_STATES[conversation_id] = data
        print(f"💾 GRAB AGENT: Saved state for {conversation_id}: {json.dumps(data, indent=2)}")
    
    def _check_transfer_needed_with_office_hours(self, message: str, data: Dict[str, Any], is_office_hours: bool) -> bool:
        """Check transfer rules based on office hours"""
        
        print(f"📖 GRAB AGENT: Checking transfer rules")
        print(f"🏢 Office hours: {is_office_hours}")
        
        message_lower = message.lower()
        
        # OUT OF OFFICE HOURS: NEVER TRANSFER - Handle all calls and make sales
        if not is_office_hours:
            print(f"🌙 OUT OF OFFICE HOURS: NEVER TRANSFER - Making the sale")
            return False
        
        # OFFICE HOURS: Check transfer rules - GRAB has £300+ threshold
        print(f"🏢 OFFICE HOURS: Checking £300+ transfer threshold")
        
        # Customer explicitly asks for different service
        if any(word in message_lower for word in ['skip hire', 'man and van', 'mav']):
            print(f"🔄 GRAB AGENT: Customer explicitly requested different service")
            return True
        
        # Hazardous materials
        hazardous_materials = ['asbestos', 'hazardous', 'toxic']
        has_prohibited = any(material in message_lower for material in hazardous_materials)
        
        if has_prohibited:
            print(f"🔄 GRAB AGENT: Hazardous materials - must transfer")
            return True
        
        # Check price thresholds - GRAB transfers for £300+
        # This would be checked after pricing is available
        
        print(f"💰 GRAB AGENT: Office hours but no transfer needed - making the sale")
        return False
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        data = context.copy() if context else {}
        
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})', message.upper().replace(' ', ''))
        if postcode_match:
            data['postcode'] = postcode_match.group(1)
            print(f"✅ GRAB AGENT: Extracted postcode: {data['postcode']}")
        
        if any(word in message.lower() for word in ['grab', 'grab hire']):
            data['service'] = 'grab'
            print(f"✅ GRAB AGENT: Extracted service: grab")
            
            if any(size in message.lower() for size in ['6-tonne', '6 tonne', '6t']):
                data['type'] = '6t'
                print(f"✅ GRAB AGENT: Extracted type: 6t")
            elif any(size in message.lower() for size in ['8-tonne', '8 tonne', '8t']):
                data['type'] = '8t'
                print(f"✅ GRAB AGENT: Extracted type: 8t")
        
        if 'kanchen ghosh' in message.lower():
            data['firstName'] = 'Kanchen Ghosh'
            print(f"✅ GRAB AGENT: Extracted firstName: Kanchen Ghosh")
        else:
            name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
            if name_match:
                data['firstName'] = name_match.group(1).strip().title()
                print(f"✅ GRAB AGENT: Extracted firstName: {data['firstName']}")
        
        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ GRAB AGENT: Extracted phone: {data['phone']}")
        
        return data
    
    def _determine_step(self, data: Dict[str, Any], message: str) -> str:
        """Determine step - go to pricing if customer asks for price and has required data"""
        
        message_lower = message.lower()
        
        price_request = any(word in message_lower for word in ['price', 'availability', 'cost', 'quote', 'confirm price'])
        has_required = data.get('service') and data.get('type') and data.get('postcode')
        
        if price_request and has_required and not data.get('has_pricing'):
            print(f"💰 GRAB AGENT: Customer requests price and has required data - going to pricing")
            return 'price'
        
        # Check for booking confirmation
        booking_request = any(word in message_lower for word in ['book', 'booking', 'confirm booking', 'yes', 'proceed'])
        has_all_data = (data.get('service') and data.get('type') and data.get('postcode') and 
                       data.get('firstName') and data.get('phone') and data.get('has_pricing'))
        
        if booking_request and has_all_data:
            print(f"📋 GRAB AGENT: Customer requests booking and has all data - going to booking")
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
    
    def _get_pricing(self, data: Dict[str, Any]) -> str:
        print(f"💰 GRAB AGENT: CALLING PRICING TOOL")
        print(f"    postcode: {data.get('postcode')}")
        print(f"    service: {data.get('service')}")
        print(f"    type: {data.get('type')}")
        
        try:
            smp_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name') and tool.name == 'smp_api':
                    smp_tool = tool
                    break
            
            if not smp_tool:
                print("❌ GRAB AGENT: SMPAPITool not found")
                return "Pricing tool not available"
            
            result = smp_tool._run(
                action="get_pricing",
                postcode=data.get('postcode'),
                service=data.get('service'),
                type=data.get('type')
            )
            
            print(f"💰 GRAB AGENT: PRICING RESULT: {json.dumps(result, indent=2)}")
            
            if result.get('success'):
                price = result.get('price', result.get('cost', 'N/A'))
                data['has_pricing'] = True
                data['price'] = price
                return f"💰 {data.get('type')} grab hire at {data.get('postcode')}: £{price}. Would you like to book this?"
            else:
                error = result.get('error', 'pricing failed')
                print(f"❌ GRAB AGENT: Pricing error: {error}")
                return f"Unable to get pricing: {error}"
                
        except Exception as e:
            print(f"❌ GRAB AGENT: PRICING EXCEPTION: {str(e)}")
            return f"Error getting pricing: {str(e)}"
    
    def _create_booking_with_payment_and_sms(self, data: Dict[str, Any]) -> str:
        """Enhanced booking process: Create ref, create price, generate payment link, send SMS"""
        booking_ref = str(uuid.uuid4())[:8]
        
        print(f"📋 GRAB AGENT: ENHANCED BOOKING PROCESS STARTED")
        
        try:
            # Find SMP and SMS tools
            smp_tool = None
            sms_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name'):
                    if tool.name == 'smp_api':
                        smp_tool = tool
                    elif tool.name == 'sms_tool':
                        sms_tool = tool
            
            if not smp_tool:
                print("❌ GRAB AGENT: SMPAPITool not found")
                return "Booking tool not available"
            
            # Create booking quote with payment link
            result = smp_tool._run(
                action="create_booking_quote",
                postcode=data.get('postcode'),
                service=data.get('service'),
                type=data.get('type'),
                firstName=data.get('firstName'),
                phone=data.get('phone'),
                booking_ref=booking_ref,
                lastName=data.get('lastName', ''),
                emailAddress=data.get('email', ''),
                date=data.get('preferred_date', ''),
                time=data.get('time', '')
            )
            
            print(f"📋 GRAB AGENT: BOOKING RESULT: {json.dumps(result, indent=2)}")
            
            if result.get('success'):
                payment_link = result.get('payment_link', '')
                price = result.get('final_price', result.get('price', data.get('price', 'N/A')))
                phone = result.get('customer_phone', data.get('phone'))
                
                # Send SMS with payment link
                sms_message = f"Hi {data.get('firstName')}, your {data.get('type')} grab hire booking (Ref: {booking_ref}) is confirmed! Price: £{price}"
                
                if sms_tool and phone and payment_link:
                    sms_result = sms_tool._run(
                        to_number=phone,
                        message=sms_message,
                        payment_link=payment_link
                    )
                    print(f"📱 SMS RESULT: {json.dumps(sms_result, indent=2)}")
                    
                    if sms_result.get('success'):
                        response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}. Payment link sent to {phone} via SMS."
                    else:
                        response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}. Payment link: {payment_link}"
                else:
                    response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}"
                    if payment_link:
                        response += f". Payment link: {payment_link}"
                
                return response
            else:
                error = result.get('error', result.get('message', 'booking failed'))
                print(f"❌ GRAB AGENT: Booking error: {error}")
                return f"Unable to create booking: {error}"
                
        except Exception as e:
            print(f"❌ GRAB AGENT: BOOKING EXCEPTION: {str(e)}")
            return f"Error creating booking: {str(e)}"

# ===============================
# CONVERSATION CONTEXT MANAGEMENT
# ===============================
conversation_contexts = {}

def manage_conversation_context(conversation_id, message, data=None):
    """Manage conversation context to prevent data contamination"""
    global conversation_contexts
    
    if conversation_id not in conversation_contexts:
        conversation_contexts[conversation_id] = {}
    
    context = conversation_contexts[conversation_id]
    
    postcode_match = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b', message.upper())
    if postcode_match:
        new_postcode = postcode_match.group(1).replace(' ', '')
        if context.get('postcode') and context['postcode'] != new_postcode:
            print(f"🔄 NEW POSTCODE DETECTED: {new_postcode} (clearing old: {context['postcode']})")
            conversation_contexts[conversation_id] = {'postcode': new_postcode}
        else:
            context['postcode'] = new_postcode
    
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
    '''Initialize the complete system with all three agents'''
    
    print("🚀 Initializing WasteKing Multi-Agent System...")
    
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
        SMSTool(  # Now properly using Twilio environment variables
            account_sid=os.getenv('TWILIO_ACCOUNT_SID'),
            auth_token=os.getenv('TWILIO_AUTH_TOKEN'),
            phone_number=os.getenv('TWILIO_PHONE_NUMBER')
        ),
        DateTimeTool()
    ]
    
    print(f"✅ Initialized {len(tools)} tools")
    print(f"📱 Twilio SMS configured: {os.getenv('TWILIO_ACCOUNT_SID') is not None}")
    
    # Initialize all three agents
    skip_agent = SkipHireAgent(llm, tools)
    mav_agent = ManAndVanAgent(llm, tools)
    grab_agent = GrabHireAgent(llm, tools)
    rules_processor = RulesProcessor()
    
    print("✅ System initialization complete")
    print("🏢 OFFICE HOURS LOGIC:")
    print("  ✅ OUT OF HOURS: Handle ALL calls, make sales, NEVER transfer")
    print("  ✅ OFFICE HOURS: Check transfer thresholds for specific numbers")
    print("📋 ENHANCED BOOKING PROCESS:")
    print("  1️⃣ Create booking reference")
    print("  2️⃣ Create booking quote")
    print("  3️⃣ Generate payment link")
    print("  4️⃣ Send SMS with payment link via Twilio")
    
    return {
        'skip_agent': skip_agent,
        'mav_agent': mav_agent,
        'grab_agent': grab_agent,
        'rules_processor': rules_processor,
        'tools': tools
    }

# Initialize system
system = initialize_system()

# ===============================
# FLASK ROUTES
# ===============================
@app.route('/')
def index():
    '''Main endpoint'''
    return jsonify({
        "message": "WasteKing Multi-Agent AI System - Enhanced Booking & SMS",
        "status": "running",
        "system_initialized": system is not None,
        "timestamp": datetime.now().isoformat(),
        "features": [
            "Three Agents: Skip, Man & Van, Grab Hire",
            "Enhanced booking process with payment links",
            "Twilio SMS integration",
            "OUT OF HOURS: Handle ALL calls, make sales",
            "OFFICE HOURS: Check transfer thresholds",
            "SMPAPITool integration with improved booking"
        ],
        "agents": [
            "Skip Hire Agent (NO LIMIT transfer threshold)",
            "Man & Van Agent (£500+ transfer threshold)",
            "Grab Hire Agent (£300+ transfer threshold, handles all others)"
        ],
        "endpoints": [
            "/api/wasteking",
            "/api/health"
        ]
    })

@app.route('/api/wasteking', methods=['POST'])
def process_customer_message():
    '''Main endpoint for processing customer messages'''
    try:
        if not system:
            return jsonify({
                "success": False,
                "message": "System not properly initialized - check configuration"
            }), 500
        
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "message": "No data provided"
            }), 400
        
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('elevenlabs_conversation_id', f"conv_{int(datetime.now().timestamp())}")
        
        print(f"Processing message: {customer_message}")
        print(f"Conversation ID: {conversation_id}")
        
        if not customer_message:
            return jsonify({
                "success": False,
                "message": "No customer message provided"
            }), 400
        
        context = manage_conversation_context(
            conversation_id, 
            customer_message, 
            data.get('context', {})
        )
        
        context['conversation_id'] = conversation_id
        
        # Route to appropriate agent (currently only Skip agent is fully implemented)
        message_lower = customer_message.lower()
        
        if any(word in message_lower for word in ['man and van', 'mav', 'man & van']):
            print("Routing to Man & Van agent...")
            response = system['mav_agent'].process_message(customer_message, context)
        elif any(word in message_lower for word in ['grab', 'grab hire']) or \
             not any(word in message_lower for word in ['skip', 'man and van', 'mav']):
            print("Routing to Grab Hire agent...")
            response = system['grab_agent'].process_message(customer_message, context)
        else:
            print("Routing to Skip agent...")
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
        return jsonify({
            "success": False,
            "message": "I understand. Let me connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    '''Health check endpoint'''
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_initialized": system is not None,
            "version": "WasteKing System v4.0 - Enhanced Booking & SMS"
        }
        
        if system:
            health_status.update({
                "tools_loaded": len(system['tools']),
                "active_conversations": len(conversation_contexts),
                "agents_available": ['skip_agent', 'mav_agent', 'grab_agent'],
                "twilio_configured": os.getenv('TWILIO_ACCOUNT_SID') is not None
            })
        
        return jsonify(health_status)
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@app.after_request
def after_request(response):
    '''Add CORS headers'''
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    print("Starting WasteKing Multi-Agent AI System...")
    
    if system:
        print("System initialized successfully")
        print("🔧 KEY FEATURES:")
        print("  ✅ Three agents: Skip, Man & Van, Grab Hire")
        print("  ✅ Enhanced booking process with payment links")
        print("  ✅ Twilio SMS integration for payment links")
        print("  ✅ OUT OF HOURS: Handle ALL calls, make sales, NEVER transfer")
        print("  ✅ OFFICE HOURS: Check transfer thresholds")
        print("  ✅ SMPAPITool with improved booking quote functionality")
    else:
        print("System initialization failed - check configuration")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
