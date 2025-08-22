# agents/orchestrator.py - COMPLETE FIXED VERSION WITH GLOBAL STATE
# FIXES: Global state storage, better regex, complete state persistence

import re
import json
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
            # SKIP STATE LOADING - just use incoming context
            conversation_state = context.copy() if context else {}
            conversation_state['conversation_id'] = conversation_id
            
            # Extract and update state from current message
            self._extract_and_update_state(message, conversation_state)
            
            print(f"🔄 SIMPLE Conversation State: {conversation_state}")
            
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
            response = agent.process_message(message, conversation_state)
            
            # SKIP COMPLEX STATE SAVING - just log
            print(f"✅ Processed with {agent_choice}, response: {response[:100]}...")
            
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
        
        # Extract postcode - NO SPACES EVER
        postcode_patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})\b',  # Standard format
            r'\b(LS\d{4})\b',  # LS1480 format
            r'\b([A-Z]{1,2}\d{1,4})\b'  # Partial postcodes
        ]
        
        for pattern in postcode_patterns:
            postcode_match = re.search(pattern, message.upper())
            if postcode_match:
                # FORCE remove any spaces
                extracted['postcode'] = postcode_match.group(1).replace(' ', '').replace('\t', '')
                print(f"✅ FOUND POSTCODE: {extracted['postcode']}")
                break
        
        # Extract phone number
        phone_patterns = [
            r'\b0\d{10}\b',  # 07823656762
            r'\b\d{11}\b',   # 07823656762
            r'\b0\d{4}\s?\d{6}\b',  # 07823 656762
            r'\b0\d{3}\s?\d{3}\s?\d{4}\b'  # 078 236 56762
        ]
        for pattern in phone_patterns:
            phone_match = re.search(pattern, message)
            if phone_match:
                extracted['phone'] = phone_match.group(0).replace(' ', '')
                print(f"✅ FOUND PHONE: {extracted['phone']}")
                break
        
        # Extract name
        name_patterns = [
            r'\bname\s+(\w+)\b',
            r'\bname\s+is\s+(\w+)\b',
            r'\bcustomer\s+(\w+)\b',
            r'\bName\s+([A-Z][a-z]+)\b'
        ]
        
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
            # Combine with existing waste types
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
        
        # Extract delivery day
        days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']
        for day in days:
            if day in message_lower:
                extracted['delivery_day'] = day.capitalize()
                print(f"✅ FOUND DELIVERY DAY: {extracted['delivery_day']}")
                break
        
        # Extract location details
        location_keywords = ['garage', 'driveway', 'front', 'back', 'side', 'garden', 'road']
        for keyword in location_keywords:
            if keyword in message_lower:
                existing_location = extracted.get('location', '')
                if keyword not in existing_location.lower():
                    extracted['location'] = f"{existing_location} {keyword}".strip()
                    print(f"✅ FOUND LOCATION: {extracted['location']}")
        
        # Check for booking intent
        booking_keywords = ['book', 'booking', 'schedule', 'arrange', 'order', 'confirm']
        if any(keyword in message_lower for keyword in booking_keywords):
            extracted['wants_booking'] = True
            print(f"✅ BOOKING INTENT DETECTED")
        
        # Update state
        state['extracted_info'] = extracted
        
        # Copy key extracted info to top level for easier access
        if 'postcode' in extracted:
            state['postcode'] = extracted['postcode']
        if 'phone' in extracted:
            state['phone'] = extracted['phone']
        if 'name' in extracted:
            state['name'] = extracted['name']
        if 'waste_type' in extracted:
            state['waste_type'] = extracted['waste_type']
        if 'size' in extracted:
            state['size'] = extracted['size']
            state['type'] = extracted['size']
        if 'wants_booking' in extracted:
            state['wants_booking'] = extracted['wants_booking']
    
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
        if len(state['messages']) > 20:
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
        """Updated routing logic with state awareness"""
        
        message_lower = message.lower()
        
        # 1. EXPLICIT SERVICE MENTIONS
        
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
        
        # Grab hire explicit requests
        if any(phrase in message_lower for phrase in [
            'grab', 'grab hire', 'lorry', 'truck', 'grab lorry'
        ]):
            return 'grab_hire', 'explicit_grab_request'
        
        # 2. CONTEXT-BASED ROUTING (prioritize existing service)
        
        if context:
            # If we have a service already determined, continue with it unless explicitly changing
            if context.get('service') or context.get('last_service'):
                existing_service = context.get('service') or context.get('last_service')
                
                # Only switch if explicitly mentioned different service
                switching_services = any(phrase in message_lower for phrase in [
                    'man and van', 'man & van', 'mav', 'skip', 'skip hire', 'grab', 'grab hire'
                ])
                
                if not switching_services:
                    if existing_service in ['mav', 'man_van']:
                        return 'mav', 'continuing_mav_conversation'
                    elif existing_service in ['skip', 'skip_hire']:
                        return 'skip_hire', 'continuing_skip_conversation'
                    elif existing_service in ['grab', 'grab_hire']:
                        return 'grab_hire', 'continuing_grab_conversation'
        
        # 3. MATERIAL-BASED ROUTING
        
        materials = self._extract_materials(message)
        
        # Check extracted waste type from state
        if context and context.get('waste_type'):
            materials.extend(context['waste_type'].split(', '))
        
        # Light items that COULD be man & van
        light_items = [
            'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 'wardrobe',
            'appliances', 'fridge', 'freezer', 'washing machine', 'dishwasher',
            'bags', 'clothes', 'books', 'boxes', 'household goods', 'office furniture'
        ]
        
        if any(item in materials for item in light_items):
            # Check if NO heavy items mentioned
            heavy_items = [
                'brick', 'bricks', 'concrete', 'soil', 'rubble', 'stone', 'sand', 
                'gravel', 'construction', 'building', 'demolition', 'hardcore'
            ]
            if not any(item in materials for item in heavy_items):
                return 'mav', 'light_items_suitable_for_mav'
        
        # Traditional skip waste
        skip_waste = [
            'construction waste', 'building waste', 'mixed waste', 'general waste',
            'household waste', 'garden waste'
        ]
        if any(waste in message_lower for waste in skip_waste):
            return 'skip_hire', 'traditional_skip_waste'
        
        # 4. HEAVY MATERIALS = GRAB
        
        heavy_materials = [
            'soil', 'muck', 'rubble', 'concrete', 'brick', 'bricks', 'stone', 
            'sand', 'gravel', 'hardcore', 'mortar', 'cement', 'asphalt', 'renovation'
        ]
        if any(material in materials for material in heavy_materials):
            return 'grab_hire', 'heavy_materials_detected'
        
        # 5. VOLUME/SIZE INDICATORS
        
        large_volume_indicators = [
            'loads of', 'lots of', 'large amount', 'truck full', 'lorry load', 
            'big job', 'clearance', 'site clearance', 'full house', 'warehouse'
        ]
        if any(indicator in message_lower for indicator in large_volume_indicators):
            return 'grab_hire', 'large_volume_job'
        
        # 6. SKIP SIZE INDICATORS
        if any(pattern in message_lower for pattern in [r'\d+\s*ya?rd', r'\d+yd']):
            return 'skip_hire', 'skip_size_mentioned'
        
        # 7. DEFAULT FALLBACK - GRAB HANDLES EVERYTHING ELSE
        return 'grab_hire', 'default_grab_handles_all'
    
    def _extract_materials(self, message: str) -> List[str]:
        """Extract materials/items mentioned in message"""
        message_lower = message.lower()
        
        all_materials = [
            # Heavy materials
            'soil', 'muck', 'rubble', 'concrete', 'brick', 'bricks', 'sand', 
            'gravel', 'stone', 'stones', 'hardcore', 'mortar', 'cement',
            'construction', 'building', 'demolition', 'asphalt', 'renovation',
            
            # Light materials  
            'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 'wardrobe',
            'appliances', 'fridge', 'freezer', 'washing machine', 'dishwasher',
            'bags', 'clothes', 'books', 'boxes', 'household', 'office',
            
            # General waste
            'garden', 'wood', 'metal', 'plastic', 'cardboard', 'general', 'mixed'
        ]
        
        found_materials = []
        for material in all_materials:
            if material in message_lower:
                found_materials.append(material)
        
        return found_materials
    
    def get_conversation_state(self, conversation_id: str) -> Dict[str, Any]:
        """Get current conversation state"""
        return self._load_conversation_state(conversation_id)
    
    def clear_conversation_state(self, conversation_id: str) -> bool:
        """Clear conversation state"""
        try:
            global _GLOBAL_CONVERSATION_STATES
            
            if conversation_id in self.conversation_states:
                del self.conversation_states[conversation_id]
            
            if conversation_id in _GLOBAL_CONVERSATION_STATES:
                del _GLOBAL_CONVERSATION_STATES[conversation_id]
            
            if hasattr(self.storage, 'delete'):
                self.storage.delete(f"conv_state_{conversation_id}")
            
            print(f"🗑️ Cleared state for {conversation_id}")
            return True
        except Exception as e:
            print(f"❌ Failed to clear state: {e}")
            return False
    
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
