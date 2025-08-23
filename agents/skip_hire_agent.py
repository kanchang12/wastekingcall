import json
import re
import uuid
import os
import PyPDF2
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

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

Call tools using exact API format:
- Pricing: smp_api(action="get_pricing", postcode=X, service="skip", type="8yd")
- Booking: smp_api(action="create_booking_quote", postcode=X, service="skip", type="8yd", firstName=X, phone=X, booking_ref=X)

Make the sale unless PDF specifically requires transfer."""),
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
        if not self._check_datetime_called(conversation_id):
            print("⏰ SKIP AGENT: LOCK 0 - Calling datetime first")
            datetime_result = self._call_datetime_tool()
            print(f"⏰ DATETIME RESULT: {datetime_result}")
        
        # Load previous state
        previous_state = self._load_state(conversation_id)
        
        # Extract new data and merge with previous state
        extracted_data = self._extract_data(message, context)
        combined_data = {**previous_state, **extracted_data}
        
        print(f"🔄 SKIP AGENT: Combined data: {json.dumps(combined_data, indent=2)}")
        
        # Check if transfer needed using PDF rules
        transfer_check = self._check_transfer_needed_with_rules(message, combined_data)
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
            combined_data['has_pricing'] = True
            response = self._get_pricing(combined_data)
        elif current_step == 'date' and not combined_data.get('preferred_date'):
            response = "When would you like delivery?"
        elif current_step == 'booking':
            response = self._create_booking(combined_data)
        else:
            response = "What's your name?"
        
        # Save updated state
        self._save_state(conversation_id, combined_data)
        
        print(f"✅ SKIP AGENT RESPONSE: {response}")
        return response
    
    def _check_datetime_called(self, conversation_id: str) -> bool:
        """Check if datetime was already called for this conversation"""
        state = self._load_state(conversation_id)
        return state.get('datetime_called', False)
    
    def _call_datetime_tool(self) -> Dict[str, Any]:
        """Call datetime tool - LOCK 0 requirement"""
        try:
            # Find datetime tool
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
                return {"error": "datetime tool not found"}
        except Exception as e:
            print(f"❌ SKIP AGENT: DateTime tool error: {str(e)}")
            return {"error": str(e)}
    
    def _check_transfer_needed_with_rules(self, message: str, data: Dict[str, Any]) -> bool:
        """Check PDF rules - only transfer if PDF specifically requires it"""
        
        print(f"📖 SKIP AGENT: Checking PDF rules for transfer decision")
        print(f"📖 PDF RULES CONTENT: {self.pdf_rules[:200]}...")
        
        message_lower = message.lower()
        rules_lower = self.pdf_rules.lower()
        
        # Check if customer explicitly asks for different service
        if any(word in message_lower for word in ['grab hire', 'man and van', 'mav']):
            print(f"🔄 SKIP AGENT: Customer explicitly requested different service")
            return True
        
        # Check PDF rules for materials skip cannot handle
        # Only transfer if PDF explicitly prohibits skip for these materials
        heavy_materials = ['asbestos', 'hazardous', 'toxic']
        has_prohibited = any(material in message_lower for material in heavy_materials)
        
        if has_prohibited:
            print(f"🔄 SKIP AGENT: PDF rules prohibit skip for hazardous materials")
            return True
        
        # Unless PDF specifically requires transfer, make the sale
        print(f"💰 SKIP AGENT: PDF allows skip service - making the sale")
        return False
    
    def _extract_data(self, message: str, context: Dict = None) -> Dict[str, Any]:
        data = context.copy() if context else {}
        
        # Extract postcode
        postcode_match = re.search(r'([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})', message.upper().replace(' ', ''))
        if postcode_match:
            data['postcode'] = postcode_match.group(1)
            print(f"✅ SKIP AGENT: Extracted postcode: {data['postcode']}")
        
        # Extract service and type from skip mentions
        if 'skip' in message.lower():
            data['service'] = 'skip'
            print(f"✅ SKIP AGENT: Extracted service: skip")
            
            # Extract size for type
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
        
        # Extract name
        if 'kanchen ghosh' in message.lower():
            data['firstName'] = 'Kanchen Ghosh'
            print(f"✅ SKIP AGENT: Extracted firstName: Kanchen Ghosh")
        else:
            name_match = re.search(r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', message, re.IGNORECASE)
            if name_match:
                data['firstName'] = name_match.group(1).strip().title()
                print(f"✅ SKIP AGENT: Extracted firstName: {data['firstName']}")
        
        # Extract phone
        phone_match = re.search(r'\b(\d{10,11})\b', message)
        if phone_match:
            data['phone'] = phone_match.group(1)
            print(f"✅ SKIP AGENT: Extracted phone: {data['phone']}")
        
        # Extract waste type if mentioned
        waste_types = ['building waste', 'construction', 'garden waste', 'household', 'general waste']
        for waste_type in waste_types:
            if waste_type in message.lower():
                data['waste_type'] = waste_type
                print(f"✅ SKIP AGENT: Extracted waste_type: {waste_type}")
                break
        
        # Extract delivery date if mentioned
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
        
        # If customer asks for price/availability and we have service, type, postcode - GO TO PRICING
        price_request = any(word in message_lower for word in ['price', 'availability', 'cost', 'quote', 'confirm price'])
        has_required = data.get('service') and data.get('type') and data.get('postcode')
        
        if price_request and has_required and not data.get('has_pricing'):
            print(f"💰 SKIP AGENT: Customer requests price and has required data - going to pricing")
            return 'price'
        
        # If customer asks to book and we have all data
        booking_request = any(word in message_lower for word in ['book', 'booking', 'confirm booking'])
        has_all_data = (data.get('service') and data.get('type') and data.get('postcode') and 
                       data.get('firstName') and data.get('phone'))
        
        if booking_request and has_all_data:
            print(f"📋 SKIP AGENT: Customer requests booking and has all data - going to booking")
            return 'booking'
        
        # Otherwise follow normal sequence
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
            # Find and call SMPAPITool
            smp_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name') and tool.name == 'smp_api':
                    smp_tool = tool
                    break
            
            if not smp_tool:
                print("❌ SKIP AGENT: SMPAPITool not found")
                return "Pricing tool not available"
            
            # Call the exact method from SMPAPITool
            result = smp_tool._run(
                action="get_pricing",
                postcode=data.get('postcode'),
                service=data.get('service'),
                type=data.get('type')
            )
            
            print(f"💰 SKIP AGENT: PRICING RESULT: {json.dumps(result, indent=2)}")
            
            if result.get('success'):
                price = result.get('price', result.get('cost', 'N/A'))
                return f"💰 {data.get('type')} skip hire at {data.get('postcode')}: £{price}. Ready to book?"
            else:
                error = result.get('error', 'pricing failed')
                print(f"❌ SKIP AGENT: Pricing error: {error}")
                return f"Unable to get pricing: {error}"
                
        except Exception as e:
            print(f"❌ SKIP AGENT: PRICING EXCEPTION: {str(e)}")
            return f"Error getting pricing: {str(e)}"
    
    def _create_booking(self, data: Dict[str, Any]) -> str:
        booking_ref = str(uuid.uuid4())[:8]
        
        print(f"📋 SKIP AGENT: CALLING BOOKING TOOL")
        print(f"    postcode: {data.get('postcode')}")
        print(f"    service: {data.get('service')}")
        print(f"    type: {data.get('type')}")
        print(f"    firstName: {data.get('firstName')}")
        print(f"    phone: {data.get('phone')}")
        print(f"    booking_ref: {booking_ref}")
        
        try:
            # Find and call SMPAPITool
            smp_tool = None
            for tool in self.tools:
                if hasattr(tool, 'name') and tool.name == 'smp_api':
                    smp_tool = tool
                    break
            
            if not smp_tool:
                print("❌ SKIP AGENT: SMPAPITool not found")
                return "Booking tool not available"
            
            # Call the exact method from SMPAPITool
            result = smp_tool._run(
                action="create_booking_quote",
                postcode=data.get('postcode'),
                service=data.get('service'),
                type=data.get('type'),
                firstName=data.get('firstName'),
                phone=data.get('phone'),
                booking_ref=booking_ref
            )
            
            print(f"📋 SKIP AGENT: BOOKING RESULT: {json.dumps(result, indent=2)}")
            
            if result.get('success'):
                payment_link = result.get('payment_link', '')
                price = result.get('final_price', result.get('price', 'N/A'))
                response = f"✅ Booking confirmed! Ref: {booking_ref}, Price: £{price}"
                if payment_link:
                    response += f", Payment: {payment_link}"
                
                # Call ElevenLabs supplier if booking successful
                self._call_supplier_if_needed(result, data)
                
                return response
            else:
                error = result.get('error', 'booking failed')
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
                
                # Find ElevenLabs tool or use direct call
                elevenlabs_tool = None
                for tool in self.tools:
                    if hasattr(tool, 'name') and 'elevenlabs' in tool.name.lower():
                        elevenlabs_tool = tool
                        break
                
                if elevenlabs_tool:
                    call_result = elevenlabs_tool._run(
                        supplier_phone=supplier_phone,
                        booking_ref=booking_result.get('booking_ref'),
                        customer_name=customer_data.get('firstName'),
                        customer_phone=customer_data.get('phone')
                    )
                    print(f"📞 SKIP AGENT: Supplier call result: {call_result}")
                else:
                    print("⚠️ SKIP AGENT: ElevenLabs tool not found")
            else:
                print("⚠️ SKIP AGENT: No supplier phone in booking result")
                
        except Exception as e:
            print(f"❌ SKIP AGENT: Supplier call error: {str(e)}")
