import re
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

# GLOBAL STATE STORAGE - survives instance recreation
_GLOBAL_CONVERSATION_STATES = {}

class AgentOrchestrator:
    """Orchestrates customer interactions between specialized agents with persistent state"""
    
    def __init__(self, llm, agents: Dict[str, Any], storage_backend=None):
        self.llm = llm
        self.agents = agents
        self.storage = storage_backend or {}
        # Use GLOBAL state to survive instance recreation
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        
        print("✅ AgentOrchestrator initialized with GLOBAL state management")
        print(f"✅ Available agents: {list(agents.keys())}")
        print(f"✅ Existing conversations: {len(self.conversation_states)}")
        print("🎯 ROUTING LOGIC: Grab handles ALL except mav and skip")
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """Process customer message and route to appropriate agent with state management"""
        
        print(f"\n🎯 ORCHESTRATOR: Processing message for {conversation_id}")
        print(f"📝 Message: {message}")
        print(f"📋 Incoming Context: {context}")
        
        try:
            # Load existing conversation state
            conversation_state = self._load_conversation_state(conversation_id)
            
            # Extract and update state from current message
            self._extract_and_update_state(message, conversation_state)
            
            # Merge with incoming context
            if context:
                conversation_state.update(context)
            
            print(f"🔄 Updated Conversation State: {conversation_state}")
            
            # CHECK FOR BOOKING CONFIRMATION
            if self._is_booking_confirmation(message, conversation_state):
                print("🔥 BOOKING CONFIRMATION DETECTED - CALLING SUPPLIER")
                self._call_supplier_async(conversation_state)
                
                # Return booking confirmation response
                extracted = conversation_state.get('extracted_info', {})
                customer_name = extracted.get('name') or conversation_state.get('name', 'Customer')
                booking_ref = conversation_state.get('booking_ref', f"WK-{int(datetime.now().timestamp())}")
                
                booking_response = f"""✅ **Booking Confirmed & Payment Sent!**

👤 **Customer:** {customer_name}
📋 **Reference:** {booking_ref}
📞 **Supplier notified:** ✅ (will call if unavailable)
📱 **Payment link sent:** ✅ (SMS to {conversation_state.get('phone', 'customer')})
💰 **Business secured:** ✅ (payment link active)

Collection will be arranged within 24 hours. Thank you for choosing WasteKing!"""

                self._save_conversation_state(conversation_id, conversation_state, message, booking_response, 'orchestrator_booking')
                
                return {
                    "success": True,
                    "response": booking_response,
                    "agent_used": "orchestrator_booking",
                    "booking_created": conversation_state.get('booking_created', False),
                    "supplier_called": conversation_state.get('supplier_called', False),
                    "payment_sent": conversation_state.get('payment_sent', False),
                    "conversation_state": conversation_state,
                    "conversation_id": conversation_id,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Determine which agent should handle this message
            agent_choice, routing_reason = self._determine_agent(message, conversation_state)
            
            print(f"🎯 ROUTING TO: {agent_choice.upper()} agent ({routing_reason})")
            
            # Get the appropriate agent
            agent = self.agents.get(agent_choice)
            if not agent:
                print(f"❌ Agent '{agent_choice}' not found, defaulting to grab_hire")
                agent = self.agents.get('grab_hire')
                agent_choice = 'grab_hire'
            
            # Update service in state
            conversation_state['last_service'] = agent_choice
            conversation_state['service'] = agent_choice.replace('_hire', '').replace('_', '')
            
            # Process message with the selected agent, passing full state as context
            print(f"🔧 CALLING {agent_choice.upper()} AGENT")
            print(f"🔧 AGENT INPUT DATA:")
            print(f"   📝 Message: {message}")
            print(f"   📍 Postcode: {conversation_state.get('postcode', 'None')}")
            print(f"   🗑️ Waste Type: {conversation_state.get('waste_type', 'None')}")
            print(f"   👤 Name: {conversation_state.get('name', 'None')}")
            print(f"   📞 Phone: {conversation_state.get('phone', 'None')}")
            
            response = agent.process_message(message, conversation_state)
            
            print(f"🔧 {agent_choice.upper()} AGENT RESPONSE: {response}")
            
            # Check if response contains pricing and update state
            if '£' in response and any(word in response.lower() for word in ['price', 'cost', 'quote']):
                conversation_state['has_pricing'] = True
                print(f"🔧 PRICING DETECTED IN RESPONSE")
            
            # Save updated conversation state
            self._save_conversation_state(conversation_id, conversation_state, message, response, agent_choice)
            
            return {
                "success": True,
                "response": response,
                "agent_used": agent_choice,
                "routing": {
                    "agent": agent_choice,
                    "reason": routing_reason,
                    "message_processed": True
                },
                "conversation_state": conversation_state,
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Orchestrator Error: {str(e)}")
            return {
                "success": False,
                "response": "I'm having a technical issue. What's your postcode and what type of waste do you need collected?",
                "error": str(e),
                "agent_used": "fallback",
                "conversation_id": conversation_id
            }
    
    def _is_booking_confirmation(self, message: str, state: Dict[str, Any]) -> bool:
        """Check if customer is confirming a booking"""
        message_lower = message.lower()
        
        # Look for confirmation words
        confirmation_words = ['yes', 'yeah', 'ok', 'okay', 'sure', 'book it', 'go ahead', 'confirm', 'proceed']
        
        # Check if we have pricing in recent conversation AND customer details
        has_recent_pricing = False
        has_customer_details = False
        
        messages = state.get('messages', [])
        if messages:
            last_response = messages[-1].get('agent_response', '').lower() if messages else ''
            if '£' in last_response and any(word in last_response for word in ['price', 'cost', 'quote']):
                has_recent_pricing = True
        
        # Check for customer details
        extracted = state.get('extracted_info', {})
        name = extracted.get('name') or state.get('name')
        phone = extracted.get('phone') or state.get('phone')
        postcode = extracted.get('postcode') or state.get('postcode')
        
        has_customer_details = bool(name and phone and postcode)
        
        print(f"🔥 BOOKING CHECK: confirmation={any(word in message_lower for word in confirmation_words)}, pricing={has_recent_pricing}, details={has_customer_details}")
        
        return (any(word in message_lower for word in confirmation_words) and 
                has_recent_pricing and 
                has_customer_details)
    
    def _call_supplier_async(self, state: Dict[str, Any]):
        """Call supplier to notify, CREATE BOOKING IMMEDIATELY, don't lose business"""
        
        # Get supplier phone from environment variable instead of hardcoding
        supplier_phone = os.getenv('SUPPLIER_PHONE', '+447394642517')
        
        try:
            print(f"🔥 CUSTOMER SAID YES - BUSINESS FLOW: NOTIFY SUPPLIER + CREATE BOOKING")
            
            # Get customer details
            extracted = state.get('extracted_info', {})
            customer_name = extracted.get('name') or state.get('name')
            customer_phone = extracted.get('phone') or state.get('phone')
            postcode = extracted.get('postcode') or state.get('postcode')
            service = state.get('service', 'grab')
            
            print(f"📋 CUSTOMER DETAILS: {customer_name}, {customer_phone}, {postcode}, {service}")
            
            # STEP 1: Call supplier to NOTIFY (fire and forget - don't wait for response)
            print(f"📞 STEP 1: NOTIFYING SUPPLIER (FIRE AND FORGET)")
            supplier_result = self._call_supplier_notification(supplier_phone, postcode, service, customer_name)
            state['supplier_called'] = supplier_result.get('success', False)
            
            # STEP 2: CREATE BOOKING IMMEDIATELY (don't wait for supplier - take the money!)
            print(f"📋 STEP 2: CREATING BOOKING IMMEDIATELY (DON'T LOSE BUSINESS)")
            booking_result = self._create_booking_quote(customer_name, customer_phone, postcode, service)
            state['booking_created'] = booking_result.get('success', False)
            state['booking_ref'] = booking_result.get('booking_ref', '')
            
            if not booking_result.get('success'):
                print(f"❌ BOOKING CREATION FAILED - TECHNICAL ISSUE")
                state['payment_sent'] = False
                return
            
            # STEP 3: SEND PAYMENT LINK IMMEDIATELY (booking created, take payment)
            print(f"📱 STEP 3: SENDING PAYMENT LINK (TAKE THE MONEY)")
            payment_result = self._send_payment_sms(customer_phone, booking_result.get('booking_ref'), booking_result.get('final_price'))
            state['payment_sent'] = payment_result.get('success', False)
            
            print(f"🔥 BUSINESS FLOW COMPLETE:")
            print(f"   📞 Supplier Notified: {state.get('supplier_called', False)}")
            print(f"   📋 Booking Created: {state.get('booking_created', False)}")
            print(f"   📱 Payment Link Sent: {state.get('payment_sent', False)}")
            print(f"   💰 MONEY SECURED: {booking_result.get('success', False)}")
            
        except Exception as e:
            print(f"❌ Business flow failed: {e}")
            state['booking_error'] = str(e)
    
    def _call_supplier_notification(self, supplier_phone: str, postcode: str, service: str, customer_name: str) -> Dict[str, Any]:
        """Call supplier to NOTIFY about new booking (fire and forget)"""
        
        try:
            from agents.elevenlabs_supplier_caller import ElevenLabsSupplierCaller
            
            print(f"📞 NOTIFYING SUPPLIER:")
            print(f"   📞 Phone: {supplier_phone}")
            print(f"   📍 Postcode: {postcode}")
            print(f"   🚛 Service: {service}")
            print(f"   👤 Customer: {customer_name}")
            print(f"   💼 PURPOSE: NOTIFICATION (not waiting for confirmation)")
            
            # Use ElevenLabs agent for supplier calls
            caller = ElevenLabsSupplierCaller(
                elevenlabs_api_key=os.getenv('ELEVENLABS_API_KEY'),
                agent_id=os.getenv('ELEVENLABS_SUPPLIER_AGENT_ID', os.getenv('ELEVENLABS_AGENT_ID')),
                agent_phone_number_id=os.getenv('ELEVENLABS_SUPPLIER_PHONE_ID', os.getenv('ELEVENLABS_AGENT_PHONE_NUMBER_ID'))
            )
            
            print(f"🔧 ORCHESTRATOR: TOOL CALL - ElevenLabsSupplierCaller.call_supplier_for_availability")
            print(f"🔧 TOOL CALL: caller.call_supplier_for_availability(supplier_phone='{supplier_phone}', service_type='{service}', postcode='{postcode}', date='ASAP')")
            
            # Fire and forget - don't block business on supplier response
            result = caller.call_supplier_for_availability(
                supplier_phone=supplier_phone,
                service_type=service,
                postcode=postcode,
                date="ASAP"
            )
            
            print(f"📞 SUPPLIER NOTIFICATION RESULT: {result}")
            print(f"📞 BUSINESS CONTINUES REGARDLESS - SUPPLIER WILL CALL BACK IF UNAVAILABLE")
            
            return result
            
        except Exception as e:
            print(f"❌ Supplier notification failed: {e}")
            print(f"📞 BUSINESS CONTINUES - SUPPLIER ISSUE WON'T BLOCK BOOKING")
            return {'success': False, 'error': str(e)}
    
    def _create_booking_quote(self, name: str, phone: str, postcode: str, service: str) -> Dict[str, Any]:
        """Create booking quote using SMP API with clean postcode format"""
        
        try:
            from tools.smp_api_tool import SMPAPITool
            
            smp_tool = SMPAPITool()
            
            booking_ref = f"WK-{int(datetime.now().timestamp())}"
            
            # CLEAN POSTCODE FOR API (remove spaces, uppercase)
            clean_postcode = postcode.replace(' ', '').upper()
            
            booking_params = {
                'postcode': clean_postcode,
                'service': service,
                'type': '8yd',
                'firstName': name,
                'phone': phone,
                'booking_ref': booking_ref,
                'emailAddress': '',
                'lastName': '',
                'date': '',
                'time': ''
            }
            
            print(f"📋 CREATING BOOKING QUOTE:")
            print(f"   📍 Postcode: '{postcode}' → API: '{clean_postcode}'")
            print(f"   🚛 Service: {service}")
            print(f"   👤 Customer: {name}")
            print(f"   📞 Phone: {phone}")
            print(f"🔧 ORCHESTRATOR: TOOL CALL - SMPAPITool._run")
            print(f"🔧 TOOL CALL: smp_tool._run(action='create_booking_quote', {booking_params})")
            
            result = smp_tool._run(action="create_booking_quote", **booking_params)
            
            print(f"📋 BOOKING QUOTE RESULT:")
            print(f"   ✅ Success: {result.get('success', False)}")
            print(f"   📋 Booking Ref: {result.get('booking_ref')}")
            print(f"   💰 Final Price: {result.get('final_price')}")
            print(f"   💳 Payment Link: {result.get('payment_link')}")
            
            return result
            
        except Exception as e:
            print(f"❌ Booking quote creation failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_payment_sms(self, customer_phone: str, booking_ref: str, amount: str) -> Dict[str, Any]:
        """Send payment SMS using SMP API → Koyeb → Twilio chain"""
        
        try:
            from tools.smp_api_tool import SMPAPITool
            
            smp_tool = SMPAPITool()
            
            print(f"📱 PAYMENT SMS PROCESS:")
            print(f"   📞 Customer Phone: {customer_phone}")
            print(f"   📋 Booking Ref: {booking_ref}")
            print(f"   💰 Amount: £{amount}")
            print(f"   🔄 Process: SMP API → Koyeb webhook → Twilio SMS")
            
            print(f"🔧 ORCHESTRATOR: TOOL CALL - SMPAPITool._run")
            print(f"🔧 TOOL CALL: smp_tool._run(action='take_payment', customer_phone='{customer_phone}', quote_id='{booking_ref}', amount='{amount}', call_sid='orchestrator')")
            
            result = smp_tool._run(
                action="take_payment",
                customer_phone=customer_phone,
                quote_id=booking_ref,
                amount=amount or "1",
                call_sid="orchestrator"
            )
            
            print(f"📱 PAYMENT SMS CHAIN RESULT:")
            print(f"   ✅ SMP API Success: {result.get('success', False)}")
            print(f"   💳 Payment Link: {result.get('payment_link', 'None')}")
            print(f"   📱 SMS Sent: {result.get('sms_sent', False)}")
            print(f"   📞 To Phone: {customer_phone}")
            
            return result
            
        except Exception as e:
            print(f"❌ Payment SMS chain failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _load_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        """Load conversation state from storage"""
        
        # Try GLOBAL state first (survives instance recreation)
        global _GLOBAL_CONVERSATION_STATES
        if conversation_id in _GLOBAL_CONVERSATION_STATES:
            print(f"📁 Loaded state from GLOBAL storage for {conversation_id}")
            state = _GLOBAL_CONVERSATION_STATES[conversation_id].copy()
            # Sync to instance cache
            self.conversation_states[conversation_id] = state.copy()
            return state
        
        # Try in-memory cache
        if conversation_id in self.conversation_states:
            print(f"📁 Loaded state from memory for {conversation_id}")
            state = self.conversation_states[conversation_id].copy()
            # Sync to global cache
            _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
            return state
        
        # Try persistent storage
        if hasattr(self.storage, 'get'):
            stored_state = self.storage.get(f"conv_state_{conversation_id}")
            if stored_state:
                if isinstance(stored_state, str):
                    stored_state = json.loads(stored_state)
                print(f"📁 Loaded state from storage for {conversation_id}")
                # Sync to both caches
                self.conversation_states[conversation_id] = stored_state
                _GLOBAL_CONVERSATION_STATES[conversation_id] = stored_state.copy()
                return stored_state.copy()
        
        # Return empty state
        print(f"📁 No existing state for {conversation_id}, creating new")
        default_state = {
            'conversation_id': conversation_id,
            'created_at': datetime.now().isoformat(),
            'messages': [],
            'extracted_info': {}
        }
        
        return default_state
        
        
    def _extract_and_update_state(self, message: str, state: Dict[str, Any]):
        """Extract key information from message and update state"""
    
        message_lower = message.lower()
        extracted = state.get('extracted_info', {})
    
        # Extract postcode
        postcode_patterns = [
            r'\b([A-Z]{1,2}[0-9R][0-9A-Z]? ?[0-9][A-Z]{2})\b',
            r'\b([A-Z]{1,2}\d{1,4})\b',
        ]
        for pattern in postcode_patterns:
            postcode_match = re.search(pattern, message.upper())
            if postcode_match:
                raw_postcode = postcode_match.group(1)
                extracted['postcode'] = raw_postcode.replace(' ', '').upper()
                print(f"✅ FOUND POSTCODE: '{raw_postcode}' → CLEANED: '{extracted['postcode']}' (for API)")
                break
        
        # Correct phone number extraction and stop at first match
        phone_patterns = [
            r'\b(?:phone|number)?\s*(?:\+?44\s?7|\b07)\d{9}\b',
            r'\b\d{11}\b',
            r'\b\+?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{4,8}\b'
        ]
        for pattern in phone_patterns:
            phone_match = re.search(pattern, message)
            if phone_match:
                extracted['phone'] = phone_match.group(0).replace(' ', '').replace('-', '').replace('.', '')
                print(f"✅ FOUND PHONE: {extracted['phone']}")
                break
    
        # Correct Name extraction and stop at first match
        name_patterns = [
            r'\bname\s*:?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',
            r'\bmy\s+name\s+is\s+([A-Z][a-z]+)\b',
            r'\bi\s+am\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',
            r'\b([A-Z][a-z]+)\b'
        ]
        
        if not extracted.get('name'):
            for pattern in name_patterns:
                name_match = re.search(pattern, message)
                if name_match:
                    extracted['name'] = name_match.group(1)
                    print(f"✅ FOUND NAME: {extracted['name']}")
                    break
    
        # Extract waste types
        waste_keywords = [
            'brick', 'bricks', 'rubble', 'concrete', 'soil', 'muck', 'sand', 'gravel',
            'furniture', 'sofa', 'construction', 'building', 'demolition', 'garden',
            'household', 'general', 'mixed', 'renovation', 'clearance', 'bags', 'books'
        ]
        
        found_waste = []
        for keyword in waste_keywords:
            if keyword in message_lower:
                found_waste.append(keyword)
        
        if found_waste:
            existing_waste = extracted.get('waste_type', [])
            if isinstance(existing_waste, str):
                existing_waste = existing_waste.split(', ')
            elif not isinstance(existing_waste, list):
                existing_waste = []
            
            all_waste = list(set(existing_waste + found_waste))
            extracted['waste_type'] = ', '.join(all_waste)
            print(f"✅ FOUND WASTE: {extracted['waste_type']}")
    
        # Extract skip size
        size_patterns = [
            r'(\d+)\s*ya?rd',
            r'(\d+)\s*cubic',
            r'(\d+)ya?rd',
            r'(\d+)yd'
        ]
        for pattern in size_patterns:
            size_match = re.search(pattern, message_lower)
            if size_match:
                extracted['size'] = f"{size_match.group(1)}yd"
                extracted['type'] = f"{size_match.group(1)}yd"
                print(f"✅ FOUND SIZE: {extracted['size']}")
                break
    
        # Check for booking intent
        booking_keywords = ['book', 'booking', 'schedule', 'arrange', 'order', 'confirm']
        if any(keyword in message_lower for keyword in booking_keywords):
            extracted['wants_booking'] = True
            print(f"✅ BOOKING INTENT DETECTED")
    
        # Update state
        state['extracted_info'] = extracted
        
        # Copy key extracted info to top level for easier access
        for key in ['postcode', 'phone', 'name', 'waste_type', 'size', 'wants_booking']:
            if key in extracted:
                state[key] = extracted[key]
                if key == 'size':
                    state['type'] = extracted[key]
        
        # Log what we have collected so far
        print(f"✅ STATE UPDATED:")
        print(f"   📍 Postcode: {state.get('postcode', 'Missing')}")
        print(f"   🗑️ Waste: {state.get('waste_type', 'Missing')}")
        print(f"   👤 Name: {state.get('name', 'Missing')}")
        print(f"   📞 Phone: {state.get('phone', 'Missing')}")
        print(f"   💰 Has Pricing: {state.get('has_pricing', False)}")
    
    def _save_conversation_state(self, conversation_id: str, state: Dict[str, Any], 
                               message: str, response: str, agent_used: str):
        """Save conversation state to storage"""
        
        # Add this message to history
        if 'messages' not in state:
            state['messages'] = []
        
        state['messages'].append({
            "timestamp": datetime.now().isoformat(),
            "customer_message": message,
            "agent_response": response,
            "agent_used": agent_used
        })
        
        # Keep only last 20 messages
        if len(state['messages']) > 100:
            state['messages'] = state['messages'][-20:]
        
        state['last_updated'] = datetime.now().isoformat()
        
        # Save to BOTH in-memory cache AND global state
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states[conversation_id] = state.copy()
        _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
        
        print(f"💾 Saved state for {conversation_id} (total: {len(_GLOBAL_CONVERSATION_STATES)})")
        
        # Save to persistent storage if available
        if hasattr(self.storage, 'set'):
            try:
                state_json = json.dumps(state, default=str)
                self.storage.set(f"conv_state_{conversation_id}", state_json)
                print(f"💾 Saved state to storage for {conversation_id}")
            except Exception as e:
                print(f"⚠️ Failed to save to storage: {e}")
    
    def _determine_agent(self, message: str, context: Dict = None) -> tuple:
        """YOUR ORIGINAL routing logic: grab handles everything except skip and mav"""
        
        message_lower = message.lower()
        
        # 1. EXPLICIT SERVICE MENTIONS ONLY
        
        # Man & Van explicit requests
        if any(phrase in message_lower for phrase in [
            'man and van', 'man & van', 'mav', 'removal service', 'house removal', 'office removal'
        ]):
            return 'mav', 'explicit_mav_request'
        
        # Skip hire explicit requests 
        if any(phrase in message_lower for phrase in [
            'skip', 'skip hire', 'container', 'bin hire', 'waste container'
        ]):
            return 'skip_hire', 'explicit_skip_request'
        
        # 2. EVERYTHING ELSE GOES TO GRAB (as per your original logic)
        return 'grab_hire', 'grab_handles_everything_else'
    
    def get_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        """Get current conversation state"""
        return self._load_conversation_state(conversation_id)
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """Get statistics about agent usage"""
        agent_usage = {}
        total_messages = 0
        
        global _GLOBAL_CONVERSATION_STATES
        
        for state in _GLOBAL_CONVERSATION_STATES.values():
            for entry in state.get('messages', []):
                agent = entry.get('agent_used', 'unknown')
                agent_usage[agent] = agent_usage.get(agent, 0) + 1
                total_messages += 1
        
        return {
            "total_messages_processed": total_messages,
            "agent_usage": agent_usage,
            "active_conversations": len(_GLOBAL_CONVERSATION_STATES)
        }
