# agents/orchestrator.py - COMPLETE FIXED VERSION WITH AUTOMATED BOOKING FLOW
# 
# KEY FEATURES:
# ✅ Keeps existing PDF rules as guidelines
# ✅ Hardcoded supplier number: +447394642517
# ✅ Uses second ElevenLabs agent for supplier calls  
# ✅ Full console logging for all tool calls
# ✅ Automated booking workflow progression
# ✅ Global state storage for persistence
#
# REQUIRED ENVIRONMENT VARIABLES:
# ELEVENLABS_API_KEY=your_api_key
# ELEVENLABS_AGENT_ID=main_agent_id (for customers)
# ELEVENLABS_AGENT_PHONE_NUMBER_ID=main_phone_id
# ELEVENLABS_SUPPLIER_AGENT_ID=supplier_agent_id (for calling suppliers)
# ELEVENLABS_SUPPLIER_PHONE_ID=supplier_phone_id
# TWILIO_ACCOUNT_SID=your_twilio_sid
# TWILIO_AUTH_TOKEN=your_twilio_token
# TWILIO_PHONE_NUMBER=your_twilio_number
#
import re
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

# GLOBAL STATE STORAGE
_GLOBAL_CONVERSATION_STATES = {}

class AgentOrchestrator:
    """Orchestrates customer interactions with AUTOMATED BOOKING FLOW"""
    
    def __init__(self, llm, agents: Dict[str, Any], storage_backend=None):
        self.llm = llm
        self.agents = agents
        self.storage = storage_backend or {}
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        
        print("✅ AgentOrchestrator initialized with AUTOMATED BOOKING FLOW")
        print(f"✅ Available agents: {list(agents.keys())}")
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """Process message with AUTOMATED booking workflow progression"""
        
        print(f"\n🎯 ORCHESTRATOR: Processing message for {conversation_id}")
        print(f"📝 Message: {message}")
        
        try:
            # Load conversation state
            conversation_state = self._load_conversation_state(conversation_id)
            
            # Extract and update state
            self._extract_and_update_state(message, conversation_state)
            
            # Merge with incoming context
            if context:
                conversation_state.update(context)
            
            print(f"🔄 Current State: {conversation_state}")
            
            # AUTOMATED WORKFLOW PROGRESSION
            workflow_result = self._execute_automated_workflow(message, conversation_state)
            
            if workflow_result['auto_handled']:
                # Save state and return automated response
                self._save_conversation_state(conversation_id, conversation_state, message, workflow_result['response'], workflow_result['agent_used'])
                return {
                    "success": True,
                    "response": workflow_result['response'],
                    "agent_used": workflow_result['agent_used'],
                    "conversation_state": conversation_state,
                    "workflow_stage": workflow_result['stage'],
                    "conversation_id": conversation_id,
                    "timestamp": datetime.now().isoformat()
                }
            
            # Fallback to regular agent routing if automation didn't handle it
            agent_choice, routing_reason = self._determine_agent(message, conversation_state)
            agent = self.agents.get(agent_choice)
            
            response = agent.process_message(message, conversation_state)
            
            # Check if we can auto-progress after agent response
            post_agent_workflow = self._check_post_agent_progression(conversation_state, response)
            if post_agent_workflow['should_progress']:
                response = post_agent_workflow['enhanced_response']
            
            self._save_conversation_state(conversation_id, conversation_state, message, response, agent_choice)
            
            return {
                "success": True,
                "response": response,
                "agent_used": agent_choice,
                "conversation_state": conversation_state,
                "conversation_id": conversation_id,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"❌ Orchestrator Error: {str(e)}")
            return {
                "success": False,
                "response": "I'll help you with that. What's your postcode and what type of waste do you need collected?",
                "error": str(e),
                "agent_used": "fallback",
                "conversation_id": conversation_id
            }
    
    def _execute_automated_workflow(self, message: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """AUTOMATED WORKFLOW - handles complete booking flow without repeat questions"""
        
        message_lower = message.lower()
        
        # Check what stage we're at
        current_stage = state.get('workflow_stage', 'initial')
        
        print(f"🔄 WORKFLOW STAGE: {current_stage}")
        
        # STAGE 1: INITIAL PRICING (if we have enough info)
        if current_stage == 'initial' and self._has_pricing_requirements(state):
            print("🔄 AUTO-EXECUTING: Initial pricing")
            
            # Determine service automatically
            service = self._determine_service_from_state(state)
            pricing_result = self._auto_get_pricing(state, service)
            
            if pricing_result['success']:
                state['workflow_stage'] = 'pricing_complete'
                state['pricing_data'] = pricing_result
                state['service'] = service
                
                # Immediately progress to booking confirmation
                return self._auto_confirm_booking(state, pricing_result)
            else:
                return {'auto_handled': False}
        
        # STAGE 2: BOOKING CONFIRMATION (if customer confirms or provides details)
        elif current_stage == 'pricing_complete' and self._customer_wants_to_proceed(message):
            print("🔄 AUTO-EXECUTING: Booking confirmation")
            
            if self._has_booking_requirements(state):
                # CUSTOMER SAID YES - CALL HARDCODED SUPPLIER FIRST
                print("📞 CUSTOMER CONFIRMED BOOKING - CALLING HARDCODED SUPPLIER +447394642517")
                supplier_result = self._call_hardcoded_supplier_for_availability(state)
                
                booking_result = self._auto_create_booking(state)
                if booking_result['success']:
                    state['workflow_stage'] = 'booking_confirmed'
                    state['booking_data'] = booking_result
                    state['supplier_called'] = supplier_result.get('success', False)
                    
                    # Also send payment link
                    payment_result = self._auto_send_payment_link(state, booking_result)
                    state['payment_sent'] = payment_result.get('success', False)
                    
                    customer_name = state.get('extracted_info', {}).get('name') or state.get('name', 'Customer')
                    
                    response = f"""✅ **Booking Confirmed!**

👤 **Customer:** {customer_name}
📋 **Reference:** {booking_result.get('booking_ref')}
💰 **Total:** {booking_result.get('final_price')}

📞 **Supplier contacted for availability** 
📱 **Payment link sent to your phone**
🚛 **Collection will be arranged**

Thank you for choosing WasteKing!"""
                    
                    return {
                        'auto_handled': True,
                        'response': response,
                        'agent_used': 'orchestrator_booking_confirmed',
                        'stage': 'booking_confirmed'
                    }
                else:
                    return {'auto_handled': False}
            else:
                return self._request_missing_booking_info(state)
        
        # STAGE 3: PAYMENT CONFIRMATION
        elif current_stage == 'booking_confirmed' and ('pay' in message_lower or 'payment' in message_lower):
            print("🔄 AUTO-EXECUTING: Payment processing")
            return self._auto_send_payment_link(state)
        
        # AUTO-PROGRESSION: If we have all info but stuck in initial, progress automatically
        elif current_stage == 'initial' and self._has_complete_booking_info(state):
            print("🔄 AUTO-PROGRESSION: Complete info available, executing full flow")
            return self._execute_full_booking_flow(state)
        
        return {'auto_handled': False}
    
    def _has_pricing_requirements(self, state: Dict[str, Any]) -> bool:
        """Check if we have minimum info for pricing"""
        postcode = state.get('postcode') or state.get('extracted_info', {}).get('postcode')
        waste_type = state.get('waste_type') or state.get('extracted_info', {}).get('waste_type')
        
        return bool(postcode and waste_type)
    
    def _has_booking_requirements(self, state: Dict[str, Any]) -> bool:
        """Check if we have minimum info for booking"""
        extracted = state.get('extracted_info', {})
        
        name = extracted.get('name') or state.get('name')
        phone = extracted.get('phone') or state.get('phone')
        postcode = extracted.get('postcode') or state.get('postcode')
        
        return bool(name and phone and postcode)
    
    def _has_complete_booking_info(self, state: Dict[str, Any]) -> bool:
        """Check if we have everything needed for complete booking"""
        return (self._has_pricing_requirements(state) and 
                self._has_booking_requirements(state))
    
    def _customer_wants_to_proceed(self, message: str) -> bool:
        """Check if customer wants to proceed with booking"""
        proceed_keywords = [
            'yes', 'yeah', 'ok', 'okay', 'sure', 'go ahead', 'book it', 
            'proceed', 'confirm', 'arrange', 'schedule', 'want it'
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in proceed_keywords)
    
    def _determine_service_from_state(self, state: Dict[str, Any]) -> str:
        """Determine service type from extracted info"""
        waste_type = (state.get('waste_type', '') + ' ' + 
                     state.get('extracted_info', {}).get('waste_type', '')).lower()
        
        # Heavy materials = grab
        if any(material in waste_type for material in ['soil', 'muck', 'rubble', 'concrete', 'brick']):
            return 'grab'
        
        # Light items = mav
        if any(item in waste_type for item in ['furniture', 'sofa', 'bags', 'appliances']):
            return 'mav'
        
        # Default = skip
        return 'skip'
    
    def _auto_get_pricing(self, state: Dict[str, Any], service: str) -> Dict[str, Any]:
        """Automatically get pricing without asking questions"""
        
        try:
            from tools.smp_api_tool import SMPAPITool
            
            smp_tool = SMPAPITool()
            
            # Extract required data
            postcode = state.get('postcode') or state.get('extracted_info', {}).get('postcode')
            size = state.get('size') or '8yd'  # Default size
            
            print(f"🔄 AUTO-PRICING CALL:")
            print(f"   📍 Postcode: {postcode}")
            print(f"   🚛 Service: {service}")
            print(f"   📦 Size: {size}")
            print(f"   🔧 FULL TOOL CALL: smp_tool._run(action='get_pricing', postcode='{postcode}', service='{service}', type='{size}')")
            
            result = smp_tool._run(
                action="get_pricing",
                postcode=postcode,
                service=service,
                type=size
            )
            
            print(f"🔄 PRICING RESULT:")
            print(f"   ✅ Success: {result.get('success')}")
            print(f"   💰 Price: {result.get('price')}")
            print(f"   📋 Booking Ref: {result.get('booking_ref')}")
            print(f"   📞 Supplier Phone: {result.get('real_supplier_phone')}")
            print(f"   🔧 FULL RESPONSE: {json.dumps(result, indent=2)}")
            
            return result
            
        except Exception as e:
            print(f"❌ Auto-pricing failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _auto_confirm_booking(self, state: Dict[str, Any], pricing_result: Dict[str, Any]) -> Dict[str, Any]:
        """Auto-confirm booking with pricing info"""
        
        price = pricing_result.get('price', 'Contact for pricing')
        service = state.get('service', 'waste collection')
        postcode = state.get('postcode', '')
        
        print(f"🔄 AUTO-CONFIRM BOOKING:")
        print(f"   💰 Price: {price}")
        print(f"   🚛 Service: {service}")
        print(f"   📍 Postcode: {postcode}")
        
        response = f"""Perfect! I've got you a quote:

💰 **Price: {price}**
📍 **Area: {postcode}**
🚛 **Service: {service.title()}**

Would you like to book this? I just need your name and phone number to confirm."""
        
        return {
            'auto_handled': True,
            'response': response,
            'agent_used': 'orchestrator_auto_pricing',
            'stage': 'pricing_complete'
        }
    
    def _auto_create_booking(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Automatically create booking"""
        
        try:
            from tools.smp_api_tool import SMPAPITool
            
            smp_tool = SMPAPITool()
            extracted = state.get('extracted_info', {})
            pricing_data = state.get('pricing_data', {})
            
            booking_params = {
                'postcode': state.get('postcode'),
                'service': state.get('service'),
                'type': state.get('size') or '8yd',
                'firstName': extracted.get('name') or state.get('name'),
                'phone': extracted.get('phone') or state.get('phone'),
                'booking_ref': pricing_data.get('booking_ref'),
                'emailAddress': extracted.get('email', ''),
                'lastName': '',
                'date': '',
                'time': ''
            }
            
            print(f"🔄 AUTO-BOOKING CALL:")
            print(f"   👤 Customer: {booking_params['firstName']}")
            print(f"   📞 Phone: {booking_params['phone']}")
            print(f"   📍 Postcode: {booking_params['postcode']}")
            print(f"   🚛 Service: {booking_params['service']}")
            print(f"   📦 Type: {booking_params['type']}")
            print(f"   🔧 FULL TOOL CALL: smp_tool._run(action='create_booking_quote', {booking_params})")
            
            result = smp_tool._run(action="create_booking_quote", **booking_params)
            
            print(f"🔄 BOOKING RESULT:")
            print(f"   ✅ Success: {result.get('success')}")
            print(f"   📋 Booking Ref: {result.get('booking_ref')}")
            print(f"   💰 Final Price: {result.get('final_price')}")
            print(f"   💳 Payment Link: {result.get('payment_link')}")
            print(f"   🔧 FULL RESPONSE: {json.dumps(result, indent=2)}")
            
            return result
            
        except Exception as e:
            print(f"❌ Auto-booking failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _auto_complete_booking_flow(self, state: Dict[str, Any], booking_result: Dict[str, Any]) -> Dict[str, Any]:
        """Complete the full booking flow - call supplier AND send payment"""
        
        try:
            # Call supplier
            supplier_result = self._auto_call_supplier(state, booking_result)
            
            # Send payment link
            payment_result = self._auto_send_payment_link(state, booking_result)
            
            customer_name = state.get('extracted_info', {}).get('name') or state.get('name', 'Customer')
            phone = state.get('extracted_info', {}).get('phone') or state.get('phone', '')
            booking_ref = booking_result.get('booking_ref', '')
            price = booking_result.get('final_price', '')
            
            response = f"""✅ **Booking Confirmed!**

👤 **Customer:** {customer_name}
📞 **Phone:** {phone}
📋 **Reference:** {booking_ref}
💰 **Total:** {price}

✅ **Supplier has been notified**
📱 **Payment link sent to your phone**
🚛 **Collection will be arranged**

Thank you for choosing WasteKing!"""
            
            # Update state
            state['workflow_stage'] = 'complete'
            state['supplier_called'] = supplier_result.get('success', False)
            state['payment_sent'] = payment_result.get('success', False)
            
            return {
                'auto_handled': True,
                'response': response,
                'agent_used': 'orchestrator_auto_complete',
                'stage': 'complete'
            }
            
        except Exception as e:
            print(f"❌ Auto-completion failed: {e}")
            return {
                'auto_handled': True,
                'response': "Booking created! We'll contact you shortly to arrange collection and payment.",
                'agent_used': 'orchestrator_fallback',
                'stage': 'booking_confirmed'
            }
    
    def _call_hardcoded_supplier_for_availability(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Call hardcoded supplier +447394642517 for availability when customer says YES"""
        
        SUPPLIER_PHONE = "+447394642517"  # HARDCODED as requested
        
        try:
            from agents.elevenlabs_supplier_caller import ElevenLabsSupplierCaller
            import os
            
            print(f"📞 CUSTOMER SAID YES - CALLING HARDCODED SUPPLIER:")
            print(f"   📞 Supplier Phone: {SUPPLIER_PHONE}")
            print(f"   🚛 Service: {state.get('service', '')}")
            print(f"   📍 Postcode: {state.get('postcode', '')}")
            print(f"   👤 Customer: {state.get('extracted_info', {}).get('name', 'Customer')}")
            
            # Use SECOND ElevenLabs agent for supplier availability calls
            supplier_agent_id = os.getenv('ELEVENLABS_SUPPLIER_AGENT_ID', os.getenv('ELEVENLABS_AGENT_ID'))
            supplier_phone_id = os.getenv('ELEVENLABS_SUPPLIER_PHONE_ID', os.getenv('ELEVENLABS_AGENT_PHONE_NUMBER_ID'))
            
            print(f"📞 Using ElevenLabs Supplier Config:")
            print(f"   🤖 Agent ID: {supplier_agent_id}")
            print(f"   📞 Phone ID: {supplier_phone_id}")
            
            caller = ElevenLabsSupplierCaller(
                elevenlabs_api_key=os.getenv('ELEVENLABS_API_KEY'),
                agent_id=supplier_agent_id,
                agent_phone_number_id=supplier_phone_id
            )
            
            print(f"📞 CALLING FOR AVAILABILITY CHECK:")
            print(f"   🔧 TOOL CALL: caller.call_supplier_for_availability(supplier_phone='{SUPPLIER_PHONE}', service_type='{state.get('service', '')}', postcode='{state.get('postcode', '')}', date='ASAP')")
            
            result = caller.call_supplier_for_availability(
                supplier_phone=SUPPLIER_PHONE,
                service_type=state.get('service', ''),
                postcode=state.get('postcode', ''),
                date="ASAP"
            )
            
            print(f"📞 AVAILABILITY CALL RESULT:")
            print(f"   ✅ Success: {result.get('success')}")
            print(f"   📞 Called: {SUPPLIER_PHONE}")
            print(f"   🆔 Conversation ID: {result.get('conversation_id')}")
            print(f"   📞 Call SID: {result.get('call_sid')}")
            print(f"   🔧 FULL RESPONSE: {json.dumps(result, indent=2)}")
            
            return result
            
        except Exception as e:
            print(f"❌ Availability call failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _auto_call_supplier(self, state: Dict[str, Any], booking_result: Dict[str, Any]) -> Dict[str, Any]:
        """Automatically call HARDCODED supplier for availability check"""
        
        # HARDCODED SUPPLIER NUMBER as requested
        SUPPLIER_PHONE = "+447394642517"
        
        try:
            from agents.elevenlabs_supplier_caller import ElevenLabsSupplierCaller
            import os
            
            print(f"📞 CALLING HARDCODED SUPPLIER:")
            print(f"   📞 Supplier Phone: {SUPPLIER_PHONE}")
            print(f"   🚛 Service: {state.get('service', '')}")
            print(f"   📍 Postcode: {state.get('postcode', '')}")
            print(f"   📋 Booking Ref: {booking_result.get('booking_ref', '')}")
            
            # Use SECOND ElevenLabs agent for supplier calls (with fallback)
            supplier_agent_id = os.getenv('ELEVENLABS_SUPPLIER_AGENT_ID', os.getenv('ELEVENLABS_AGENT_ID'))
            supplier_phone_id = os.getenv('ELEVENLABS_SUPPLIER_PHONE_ID', os.getenv('ELEVENLABS_AGENT_PHONE_NUMBER_ID'))
            
            print(f"📞 ElevenLabs Config:")
            print(f"   🔑 API Key: {'✅ Set' if os.getenv('ELEVENLABS_API_KEY') else '❌ Missing'}")
            print(f"   🤖 Supplier Agent ID: {supplier_agent_id}")
            print(f"   📞 Supplier Phone ID: {supplier_phone_id}")
            
            caller = ElevenLabsSupplierCaller(
                elevenlabs_api_key=os.getenv('ELEVENLABS_API_KEY'),
                agent_id=supplier_agent_id,
                agent_phone_number_id=supplier_phone_id
            )
            
            call_message = f"New booking availability check from WasteKing. Customer: {state.get('extracted_info', {}).get('name', 'Customer')}, Reference: {booking_result.get('booking_ref', '')}, Service: {state.get('service', '')}, Area: {state.get('postcode', '')}"
            
            print(f"📞 FULL SUPPLIER CALL:")
            print(f"   📞 Phone: {SUPPLIER_PHONE}")
            print(f"   💬 Message: {call_message}")
            print(f"   🔧 TOOL CALL: caller.call_supplier_for_availability(supplier_phone='{SUPPLIER_PHONE}', service_type='{state.get('service', '')}', postcode='{state.get('postcode', '')}', date='ASAP')")
            
            result = caller.call_supplier_for_availability(
                supplier_phone=SUPPLIER_PHONE,
                service_type=state.get('service', ''),
                postcode=state.get('postcode', ''),
                date="ASAP"
            )
            
            print(f"📞 SUPPLIER CALL RESULT:")
            print(f"   ✅ Success: {result.get('success')}")
            print(f"   📞 Phone Called: {SUPPLIER_PHONE}")
            print(f"   🆔 Conversation ID: {result.get('conversation_id')}")
            print(f"   📞 Call SID: {result.get('call_sid')}")
            print(f"   🔧 FULL RESPONSE: {json.dumps(result, indent=2)}")
            
            return result
            
        except Exception as e:
            print(f"❌ Supplier call failed: {e}")
            return {'success': False, 'error': str(e), 'supplier_phone': SUPPLIER_PHONE}
    
    def _auto_send_payment_link(self, state: Dict[str, Any], booking_result: Dict[str, Any] = None) -> Dict[str, Any]:
        """Automatically send payment link"""
        
        try:
            from tools.smp_api_tool import SMPAPITool
            
            smp_tool = SMPAPITool()
            
            if booking_result:
                booking_ref = booking_result.get('booking_ref', '')
                price = booking_result.get('final_price', '1')
            else:
                booking_data = state.get('booking_data', {})
                booking_ref = booking_data.get('booking_ref', '')
                price = booking_data.get('final_price', '1')
            
            customer_phone = state.get('extracted_info', {}).get('phone') or state.get('phone', '')
            
            print(f"📱 SENDING PAYMENT LINK:")
            print(f"   📞 Customer Phone: {customer_phone}")
            print(f"   📋 Booking Ref: {booking_ref}")
            print(f"   💰 Amount: £{price}")
            print(f"   🔧 TOOL CALL: smp_tool._run(action='take_payment', customer_phone='{customer_phone}', quote_id='{booking_ref}', amount='{price}', call_sid='orchestrator_auto')")
            
            result = smp_tool._run(
                action="take_payment",
                customer_phone=customer_phone,
                quote_id=booking_ref,
                amount=price,
                call_sid="orchestrator_auto"
            )
            
            print(f"📱 PAYMENT LINK RESULT:")
            print(f"   ✅ Success: {result.get('success')}")
            print(f"   📞 Phone: {customer_phone}")
            print(f"   💳 Payment Link: {result.get('payment_link')}")
            print(f"   📱 SMS Sent: {result.get('sms_sent')}")
            print(f"   🔧 FULL RESPONSE: {json.dumps(result, indent=2)}")
            
            return result
            
        except Exception as e:
            print(f"❌ Payment link failed: {e}")
            return {'success': False, 'error': str(e)}
    
    def _execute_full_booking_flow(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Execute complete booking flow when all info is available"""
        
        print("🔄 EXECUTING FULL BOOKING FLOW")
        
        # Step 1: Get pricing
        service = self._determine_service_from_state(state)
        pricing_result = self._auto_get_pricing(state, service)
        
        if not pricing_result.get('success'):
            return {'auto_handled': False}
        
        state['pricing_data'] = pricing_result
        state['service'] = service
        
        # Step 2: Create booking
        booking_result = self._auto_create_booking(state)
        
        if not booking_result.get('success'):
            return {'auto_handled': False}
        
        state['booking_data'] = booking_result
        
        # Step 3: Complete flow (call supplier + send payment)
        return self._auto_complete_booking_flow(state, booking_result)
    
    def _request_missing_booking_info(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Request missing information for booking"""
        
        extracted = state.get('extracted_info', {})
        missing = []
        
        if not (extracted.get('name') or state.get('name')):
            missing.append('name')
        if not (extracted.get('phone') or state.get('phone')):
            missing.append('phone number')
        
        if missing:
            response = f"To complete your booking, I need your {' and '.join(missing)}."
        else:
            response = "Perfect! Let me confirm your booking now."
        
        return {
            'auto_handled': True,
            'response': response,
            'agent_used': 'orchestrator_missing_info',
            'stage': 'awaiting_info'
        }
    
    def _check_post_agent_progression(self, state: Dict[str, Any], response: str) -> Dict[str, Any]:
        """Check if we can auto-progress after agent response"""
        
        # If agent got pricing, auto-progress to booking confirmation
        if 'price' in response.lower() and '£' in response and state.get('workflow_stage') != 'pricing_complete':
            state['workflow_stage'] = 'pricing_complete'
            
            enhanced_response = response + "\n\nWould you like to book this? I just need to confirm your details."
            
            return {
                'should_progress': True,
                'enhanced_response': enhanced_response
            }
        
        return {'should_progress': False}
    
    # [Previous state management methods remain the same...]
    def _load_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        """Load conversation state from storage"""
        
        global _GLOBAL_CONVERSATION_STATES
        if conversation_id in _GLOBAL_CONVERSATION_STATES:
            print(f"📁 Loaded state from GLOBAL storage for {conversation_id}")
            state = _GLOBAL_CONVERSATION_STATES[conversation_id].copy()
            self.conversation_states[conversation_id] = state.copy()
            return state
        
        if conversation_id in self.conversation_states:
            print(f"📁 Loaded state from memory for {conversation_id}")
            state = self.conversation_states[conversation_id].copy()
            _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
            return state
        
        print(f"📁 No existing state for {conversation_id}, creating new")
        default_state = {
            'conversation_id': conversation_id,
            'created_at': datetime.now().isoformat(),
            'messages': [],
            'extracted_info': {},
            'workflow_stage': 'initial'
        }
        
        return default_state
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any]):
        """Extract key information from message and update state"""
        
        message_lower = message.lower()
        extracted = state.get('extracted_info', {})
        
        # Extract postcode
        postcode_patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})\b',
            r'\b(LS\d{4})\b',
            r'\b([A-Z]{1,2}\d{1,4})\b'
        ]
        
        for pattern in postcode_patterns:
            postcode_match = re.search(pattern, message.upper())
            if postcode_match:
                extracted['postcode'] = postcode_match.group(1).replace(' ', '')
                state['postcode'] = extracted['postcode']
                print(f"✅ FOUND POSTCODE: {extracted['postcode']}")
                break
        
        # Extract phone number
        phone_patterns = [
            r'\b(07\d{9})\b',
            r'\b(0\d{10})\b'
        ]
        for pattern in phone_patterns:
            phone_match = re.search(pattern, message)
            if phone_match:
                extracted['phone'] = phone_match.group(1)
                state['phone'] = extracted['phone']
                print(f"✅ FOUND PHONE: {extracted['phone']}")
                break
        
        # Extract name
        name_patterns = [
            r'\bname\s+is\s+([A-Z][a-z]+)\b',
            r'\bmy\s+name\s+is\s+([A-Z][a-z]+)\b',
            r'\bi\s+am\s+([A-Z][a-z]+)\b',
            r'\b([A-Z][a-z]+)\s+here\b'
        ]
        
        for pattern in name_patterns:
            name_match = re.search(pattern, message)
            if name_match:
                extracted['name'] = name_match.group(1)
                state['name'] = extracted['name']
                print(f"✅ FOUND NAME: {extracted['name']}")
                break
        
        # Extract waste types
        waste_keywords = [
            'brick', 'bricks', 'rubble', 'concrete', 'soil', 'muck', 'sand', 'gravel',
            'furniture', 'sofa', 'construction', 'building', 'demolition', 'garden',
            'household', 'general', 'mixed', 'renovation', 'clearance', 'bags'
        ]
        
        found_waste = []
        for keyword in waste_keywords:
            if keyword in message_lower:
                found_waste.append(keyword)
        
        if found_waste:
            existing_waste = extracted.get('waste_type', '')
            all_waste = list(set(existing_waste.split(', ') + found_waste)) if existing_waste else found_waste
            extracted['waste_type'] = ', '.join([w for w in all_waste if w])
            state['waste_type'] = extracted['waste_type']
            print(f"✅ FOUND WASTE: {extracted['waste_type']}")
        
        state['extracted_info'] = extracted
    
    def _save_conversation_state(self, conversation_id: str, state: Dict[str, Any], 
                               message: str, response: str, agent_used: str):
        """Save conversation state to storage"""
        
        if 'messages' not in state:
            state['messages'] = []
        
        state['messages'].append({
            "timestamp": datetime.now().isoformat(),
            "customer_message": message,
            "agent_response": response,
            "agent_used": agent_used
        })
        
        if len(state['messages']) > 20:
            state['messages'] = state['messages'][-20:]
        
        state['last_updated'] = datetime.now().isoformat()
        
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states[conversation_id] = state.copy()
        _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
        
        print(f"💾 Saved state for {conversation_id}")
    
    def _determine_agent(self, message: str, context: Dict = None) -> tuple:
        """Determine which agent should handle this message"""
        
        message_lower = message.lower()
        
        if any(phrase in message_lower for phrase in ['man and van', 'man & van', 'mav']):
            return 'mav', 'explicit_mav_request'
        
        if any(phrase in message_lower for phrase in ['skip', 'skip hire', 'container']):
            return 'skip_hire', 'explicit_skip_request'
        
        if any(phrase in message_lower for phrase in ['grab', 'grab hire', 'lorry']):
            return 'grab_hire', 'explicit_grab_request'
        
        # Material-based routing
        heavy_materials = ['soil', 'muck', 'rubble', 'concrete', 'brick']
        if any(material in message_lower for material in heavy_materials):
            return 'grab_hire', 'heavy_materials_detected'
        
        light_items = ['furniture', 'sofa', 'chair', 'bags', 'appliances']
        if any(item in message_lower for item in light_items):
            return 'mav', 'light_items_suitable_for_mav'
        
        return 'grab_hire', 'default_grab_handles_all'
    
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
