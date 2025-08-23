import re
import json
import os
from typing import Dict, Any, Optional
from datetime import datetime
import requests
import uuid
from utils.rules_processor import RulesProcessor
from utils.state_manager import StateManager

# GLOBAL STATE STORAGE - survives instance recreation
_GLOBAL_CONVERSATION_STATES = {}

class AgentOrchestrator:
    """Intelligent Multi-Agent Router - Uses existing agents and tools properly"""
    
    def __init__(self, llm, agents):
        self.llm = llm
        self.agents = agents  # All existing agents: skip_hire, mav, grab_hire, pricing
        self.koyeb_url = "https://internal-porpoise-onewebonly-1b44fcb9.koyeb.app"
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states = _GLOBAL_CONVERSATION_STATES
        
        # IMPORT RULES FROM PDF
        self.rules_processor = RulesProcessor()
        self.business_rules = self.rules_processor.get_all_rules()
        
        # USE STATE MANAGER
        self.state_manager = StateManager(os.getenv('DATABASE_PATH', 'conversations.db'))
        
        print("✅ PROPER Multi-Agent Orchestrator initialized")
        print("✅ Rules imported from data/rules/all rules.pdf")
        print("✅ Agents available:", list(self.agents.keys()))
        print("✅ Using StateManager for conversation persistence")
        print("✅ Agents will use tools: SMPAPITool, SMSTool, ElevenLabsSupplierCaller")
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """Intelligent routing to appropriate agents who use proper tools"""
        
        # LOAD STATE PROPERLY using StateManager
        conversation_state = self._load_conversation_state_properly(conversation_id)
        
        # Extract basic data from message + context
        self._extract_and_update_state(message, conversation_state, context)
        
        extracted = conversation_state.get('extracted_info', {})
        
        print(f"🎯 ORCHESTRATOR ANALYSIS:")
        print(f"   💬 Message: {message}")
        print(f"   📋 Extracted: {json.dumps(extracted, indent=2)}")
        print(f"   🏪 Available Agents: {list(self.agents.keys())}")
        
        # INTELLIGENT ROUTING LOGIC using PDF rules
        routing_decision = self._determine_routing_with_rules(message, extracted, conversation_state)
        
        print(f"🚦 ROUTING DECISION: {routing_decision}")
        
        # Route to appropriate agent (they will use their tools)
        if routing_decision['agent'] == 'direct_response':
            # Handle simple questions directly
            response = routing_decision['response']
            agent_used = 'orchestrator'
            
        elif routing_decision['agent'] in self.agents:
            # Route to specific agent - THEY will use tools
            agent = self.agents[routing_decision['agent']]
            
            try:
                print(f"🔀 ROUTING TO: {routing_decision['agent']}")
                print(f"🔧 Agent will use tools: SMPAPITool, SMSTool, ElevenLabsSupplierCaller")
                
                # Pass context to agent - agent will use tools for pricing/booking/SMS
                response = agent.process_message(message, context or extracted)
                agent_used = routing_decision['agent']
                
                # Check if agent created booking (they handle supplier calls via tools)
                if 'booking' in response.lower() and 'ref' in response.lower():
                    print("✅ Agent handled booking with tools (auto supplier call)")
                    conversation_state['has_booking'] = True
                
            except Exception as e:
                print(f"❌ Agent {routing_decision['agent']} failed: {str(e)}")
                response = "Let me connect you with our team for immediate assistance."
                agent_used = 'fallback'
        
        else:
            # Fallback - still route to grab_hire (handles most cases)
            try:
                if 'grab_hire' in self.agents:
                    print("🔄 FALLBACK: Routing to grab_hire agent")
                    response = self.agents['grab_hire'].process_message(message, context or extracted)
                    agent_used = 'grab_hire'
                else:
                    response = "How can I help with your waste collection today?"
                    agent_used = 'orchestrator'
            except Exception as e:
                print(f"❌ Fallback failed: {str(e)}")
                response = "How can I help with your waste collection today?"
                agent_used = 'orchestrator'
        
        # Update state using StateManager
        conversation_state['last_agent'] = agent_used
        conversation_state['routing_info'] = routing_decision
        
        self._save_conversation_state_properly(conversation_id, conversation_state, message, response, agent_used)
        
        return {
            "success": True,
            "response": response,
            "conversation_state": conversation_state,
            "conversation_id": conversation_id,
            "routing": routing_decision,
            "agent_used": agent_used,
            "tools_available": ["SMPAPITool", "SMSTool", "DateTimeTool", "ElevenLabsSupplierCaller"],
            "timestamp": datetime.now().isoformat()
        }
    
    def _determine_routing_with_rules(self, message: str, extracted: Dict, state: Dict) -> Dict[str, Any]:
        """Intelligent routing using PDF rules and business logic"""
        
        message_lower = message.lower()
        
        # APPLY PDF RULES for routing decisions
        
        # 1. GENERAL QUESTIONS
        question_words = ['what services', 'what do you', 'help me', 'options', 'types of', 'services available']
        if any(word in message_lower for word in question_words):
            return {
                'agent': 'direct_response',
                'reason': 'general_question',
                'rule_applied': 'general_inquiry_handling',
                'response': """We offer three main services:

🗑️ **Skip Hire** - Traditional skips (4-12yd) for general waste, garden waste, construction
📦 **Man & Van** - House clearances, furniture, light items (NO heavy materials like concrete/soil)
🚛 **Grab Hire** - Heavy materials (soil, rubble, concrete), large volumes, construction waste

What type of waste do you have?"""
            }
        
        # 2. PRICE COMPARISONS - Route to PricingAgent (uses SMPAPITool)
        comparison_phrases = ['compare prices', 'both prices', 'skip vs grab', 'grab vs skip', 'cheaper', 'price difference']
        if any(phrase in message_lower for phrase in comparison_phrases):
            return {
                'agent': 'pricing',
                'reason': 'price_comparison_request',
                'rule_applied': 'multi_service_pricing',
                'intent': 'compare_services'
            }
        
        # 3. SERVICE-SPECIFIC ROUTING based on PDF rules
        
        # SKIP HIRE - Traditional skip services
        skip_indicators = ['skip', 'traditional skip', 'skip hire', 'general waste', 'garden waste']
        if any(word in message_lower for word in skip_indicators):
            # Check for heavy materials (PDF rule: heavy materials need grab hire)
            heavy_materials = ['soil', 'concrete', 'rubble', 'brick', 'sand', 'stone', 'heavy', 'construction debris']
            has_heavy = any(material in message_lower for material in heavy_materials)
            
            if has_heavy and 'skip' in message_lower:
                return {
                    'agent': 'grab_hire',
                    'reason': 'heavy_materials_override_skip',
                    'rule_applied': 'heavy_materials_require_grab',
                    'note': 'Customer said skip but has heavy materials - grab hire required per PDF rules'
                }
            else:
                return {
                    'agent': 'skip_hire',  # Will use SMPAPITool for pricing/booking
                    'reason': 'skip_hire_requested',
                    'rule_applied': 'standard_skip_service'
                }
        
        # MAN & VAN - Light items only (strict PDF rules)
        mav_indicators = ['furniture', 'house clearance', 'man and van', 'mav', 'light items', 'sofa', 'bed', 'table', 'appliance', 'mattress']
        if any(word in message_lower for word in mav_indicators):
            # PDF RULE: MAV cannot handle heavy materials
            heavy_materials = ['soil', 'concrete', 'rubble', 'brick', 'sand', 'stone', 'construction', 'demolition', 'heavy']
            has_heavy = any(material in message_lower for material in heavy_materials)
            
            if has_heavy:
                return {
                    'agent': 'grab_hire',
                    'reason': 'heavy_materials_cannot_use_mav',
                    'rule_applied': 'mav_weight_restrictions',
                    'note': 'Customer mentioned furniture but has heavy materials - grab hire required'
                }
            else:
                return {
                    'agent': 'mav',  # Will use SMPAPITool and check for heavy items
                    'reason': 'light_household_items',
                    'rule_applied': 'mav_suitable_for_light_items'
                }
        
        # GRAB HIRE - Everything else, heavy materials, construction
        grab_indicators = ['grab', 'grab hire', 'heavy', 'soil', 'rubble', 'concrete', 'construction', 'demolition', 'large volume', 'muck', 'sand']
        if any(word in message_lower for word in grab_indicators):
            return {
                'agent': 'grab_hire',  # Will use SMPAPITool, ElevenLabsSupplierCaller
                'reason': 'grab_hire_requested',
                'rule_applied': 'grab_hire_for_heavy_materials'
            }
        
        # 4. BOOKING/CONFIRMATION - Route to last agent or default
        booking_words = ['book', 'confirm', 'yes book', 'go ahead', 'payment link', 'create booking']
        if any(word in message_lower for word in booking_words):
            # Use last agent if available
            if state.get('last_agent') in ['skip_hire', 'mav', 'grab_hire']:
                return {
                    'agent': state['last_agent'],
                    'reason': 'continue_with_last_agent',
                    'rule_applied': 'booking_continuation',
                    'intent': 'create_booking'
                }
            else:
                # Default to grab hire for bookings
                return {
                    'agent': 'grab_hire',
                    'reason': 'booking_default_to_grab',
                    'rule_applied': 'default_booking_service'
                }
        
        # 5. PRICING REQUESTS - Route to appropriate agent or PricingAgent
        if any(word in message_lower for word in ['price', 'cost', 'quote', 'how much']):
            # If specific service mentioned, route to that agent
            if 'skip' in message_lower:
                return {'agent': 'skip_hire', 'reason': 'skip_pricing', 'rule_applied': 'service_specific_pricing'}
            elif any(word in message_lower for word in ['mav', 'man and van', 'furniture']):
                return {'agent': 'mav', 'reason': 'mav_pricing', 'rule_applied': 'service_specific_pricing'}
            elif 'grab' in message_lower:
                return {'agent': 'grab_hire', 'reason': 'grab_pricing', 'rule_applied': 'service_specific_pricing'}
            else:
                return {'agent': 'pricing', 'reason': 'general_pricing', 'rule_applied': 'pricing_agent_handles_general'}
        
        # 6. DEFAULT ROUTING based on extracted data and PDF rules
        
        # Has postcode - route based on waste type using PDF rules
        if extracted.get('postcode'):
            # Heavy materials → Grab Hire (PDF rule)
            heavy_materials = ['soil', 'concrete', 'rubble', 'brick', 'sand', 'stone', 'construction', 'demolition', 'muck']
            if any(material in message_lower for material in heavy_materials):
                return {
                    'agent': 'grab_hire',
                    'reason': 'heavy_materials_with_postcode',
                    'rule_applied': 'postcode_plus_heavy_materials'
                }
            
            # Light household items → Man & Van (PDF rule)
            light_items = ['furniture', 'household', 'appliance', 'mattress', 'sofa', 'chair', 'table', 'bed']
            if any(item in message_lower for item in light_items):
                return {
                    'agent': 'mav',
                    'reason': 'light_items_with_postcode',
                    'rule_applied': 'postcode_plus_light_items'
                }
            
            # General waste → Skip Hire (PDF rule)
            general_waste = ['general waste', 'garden waste', 'household waste', 'mixed waste']
            if any(waste in message_lower for waste in general_waste):
                return {
                    'agent': 'skip_hire',
                    'reason': 'general_waste_with_postcode',
                    'rule_applied': 'postcode_plus_general_waste'
                }
        
        # 7. DEFAULT - Grab Hire handles most cases (PDF rule: grab hire is versatile)
        return {
            'agent': 'grab_hire',
            'reason': 'default_to_grab_hire',
            'rule_applied': 'grab_hire_default_service',
            'note': 'Grab hire handles most waste types per PDF rules'
        }
    
    def _extract_and_update_state(self, message: str, state: Dict[str, Any], context: Dict = None):
        """Extract and update conversation state"""
        
        extracted = state.get('extracted_info', {})
        
        # Include context data first
        if context:
            for key in ['postcode', 'firstName', 'phone', 'emailAddress', 'service', 'type']:
                if context.get(key):
                    extracted[key] = context[key]
        
        # Extract postcode (improved patterns)
        postcode_patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})\b',  # Full UK postcode
            r'(LS\d{4})',  # Leeds specific
            r'(M\d{4})',   # Manchester specific
            r'([A-Z]{1,2}\d{1,2}[A-Z]?)\s*(\d[A-Z]{2})',  # Split format
        ]
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                if isinstance(match, tuple):
                    clean = ''.join(match).replace(' ', '')
                else:
                    clean = match.strip().replace(' ', '')
                if len(clean) >= 5:
                    extracted['postcode'] = clean
                    break
        
        # Extract name (improved patterns)
        name_patterns = [
            r'[Nn]ame\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'[Nn]ame\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'my name is ([A-Z][a-z]+)',
            r'i\'m ([A-Z][a-z]+)',
            r'call me ([A-Z][a-z]+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                extracted['firstName'] = match.group(1).strip().title()
                break
        
        # Extract phone (improved patterns)
        phone_patterns = [
            r'payment link to (\d{11})',
            r'link to (\d{11})',
            r'to (\d{11})',
            r'\b(07\d{9})\b',
            r'\b(\+447\d{9})\b',
            r'\b(\d{11})\b'
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                extracted['phone'] = match.group(1)
                break
        
        # Extract service preference
        if 'skip' in message.lower():
            extracted['preferred_service'] = 'skip'
        elif any(word in message.lower() for word in ['man and van', 'mav', 'furniture']):
            extracted['preferred_service'] = 'mav'
        elif 'grab' in message.lower():
            extracted['preferred_service'] = 'grab'
        
        # Extract waste type categories
        waste_categories = {
            'heavy': ['soil', 'concrete', 'rubble', 'brick', 'sand', 'stone'],
            'construction': ['construction', 'demolition', 'building'],
            'household': ['furniture', 'appliance', 'mattress', 'sofa'],
            'garden': ['garden', 'green', 'leaves', 'branches'],
            'general': ['general', 'mixed', 'household waste']
        }
        
        found_categories = []
        message_lower = message.lower()
        for category, keywords in waste_categories.items():
            if any(keyword in message_lower for keyword in keywords):
                found_categories.append(category)
        
        if found_categories:
            extracted['waste_categories'] = found_categories
        
        state['extracted_info'] = extracted
        
        # Copy to main state for easy access
        for key in extracted:
            state[key] = extracted[key]
    
    def _load_conversation_state_properly(self, conversation_id: str) -> Dict[str, Any]:
        """Load state using StateManager and fallback to global storage"""
        try:
            # Try StateManager first
            state_obj = self.state_manager.get_state(conversation_id)
            if state_obj:
                return {
                    "conversation_id": conversation_id,
                    "messages": getattr(state_obj, 'messages', []),
                    "extracted_info": getattr(state_obj, 'customer_data', {}),
                    "last_agent": getattr(state_obj, 'current_agent', None),
                    "routing_info": {}
                }
        except Exception as e:
            print(f"⚠️ StateManager failed: {e}")
        
        # Fallback to global storage
        global _GLOBAL_CONVERSATION_STATES
        if conversation_id in _GLOBAL_CONVERSATION_STATES:
            return _GLOBAL_CONVERSATION_STATES[conversation_id].copy()
        
        return {
            "conversation_id": conversation_id,
            "messages": [],
            "extracted_info": {},
            "last_agent": None,
            "routing_info": {}
        }
    
    def _save_conversation_state_properly(self, conversation_id: str, state: Dict[str, Any], message: str, response: str, agent_used: str):
        """Save state using StateManager and global storage"""
        
        # Add message to history
        if 'messages' not in state:
            state['messages'] = []
        state['messages'].append({
            "timestamp": datetime.now().isoformat(),
            "customer_message": message,
            "agent_response": response,
            "agent_used": agent_used
        })
        
        # Keep reasonable message history
        if len(state['messages']) > 50:
            state['messages'] = state['messages'][-30:]
        
        state['last_updated'] = datetime.now().isoformat()
        
        # Save to StateManager
        try:
            self.state_manager.update_state(
                conversation_id=conversation_id,
                customer_data=state.get('extracted_info', {}),
                current_agent=agent_used,
                conversation_stage='active'
            )
        except Exception as e:
            print(f"⚠️ StateManager save failed: {e}")
        
        # Save to global storage as backup
        global _GLOBAL_CONVERSATION_STATES
        self.conversation_states[conversation_id] = state.copy()
        _GLOBAL_CONVERSATION_STATES[conversation_id] = state.copy()
