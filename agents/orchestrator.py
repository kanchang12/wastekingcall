# agents/orchestrator.py - REPLACEMENT FILE
# CHANGES: Updated routing logic - Grab handles ALL except mav and skip

import re
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

class AgentOrchestrator:
    """Orchestrates customer interactions between specialized agents"""
    
    def __init__(self, llm, agents: Dict[str, Any]):
        self.llm = llm
        self.agents = agents
        self.conversation_history = {}
        
        print("✅ AgentOrchestrator initialized")
        print(f"✅ Available agents: {list(agents.keys())}")
        print("🎯 ROUTING LOGIC: Grab handles ALL except mav and skip")
    
    def process_customer_message(self, message: str, conversation_id: str, context: Dict = None) -> Dict[str, Any]:
        """Process customer message and route to appropriate agent"""
        
        print(f"\n🎯 ORCHESTRATOR: Processing message for {conversation_id}")
        print(f"📝 Message: {message}")
        print(f"📋 Context: {context}")
        
        try:
            # Determine which agent should handle this message
            agent_choice, routing_reason = self._determine_agent(message, context)
            
            print(f"🎯 ROUTING TO: {agent_choice.upper()} agent ({routing_reason})")
            
            # Get the appropriate agent
            agent = self.agents.get(agent_choice)
            if not agent:
                print(f"❌ Agent '{agent_choice}' not found, defaulting to grab_hire")
                agent = self.agents.get('grab_hire')
                agent_choice = 'grab_hire'
            
            # Process message with the selected agent
            response = agent.process_message(message, context)
            
            # Update conversation history
            self._update_conversation_history(conversation_id, message, response, agent_choice)
            
            return {
                "success": True,
                "response": response,
                "agent_used": agent_choice,
                "routing": {
                    "agent": agent_choice,
                    "reason": routing_reason,
                    "message_processed": True
                },
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
    
    def _determine_agent(self, message: str, context: Dict = None) -> tuple[str, str]:
        """CHANGE: Updated routing logic - Grab handles ALL except mav and skip"""
        
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
        
        # 2. MATERIAL-BASED ROUTING
        
        materials = self._extract_materials(message)
        
        # Light items that COULD be man & van (but they'll check restrictions)
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
        
        # 3. VOLUME/SIZE INDICATORS
        
        # Large volume indicators = grab
        large_volume_indicators = [
            'loads of', 'lots of', 'large amount', 'truck full', 'lorry load', 
            'big job', 'clearance', 'site clearance', 'full house', 'warehouse'
        ]
        if any(indicator in message_lower for indicator in large_volume_indicators):
            return 'grab_hire', 'large_volume_job'
        
        # 4. HEAVY MATERIALS = GRAB (as per requirement)
        
        heavy_materials = [
            'soil', 'muck', 'rubble', 'concrete', 'brick', 'bricks', 'stone', 
            'sand', 'gravel', 'hardcore', 'mortar', 'cement', 'asphalt'
        ]
        if any(material in materials for material in heavy_materials):
            return 'grab_hire', 'heavy_materials_detected'
        
        # 5. CONTEXT-BASED ROUTING
        
        if context:
            # If previous service was grab, continue with grab
            if context.get('last_service') == 'grab':
                return 'grab_hire', 'continuing_grab_conversation'
            
            # If we have pricing info, check what service it was for
            if context.get('service'):
                service = context['service']
                if service == 'mav':
                    return 'mav', 'continuing_mav_conversation'
                elif service == 'skip':
                    return 'skip_hire', 'continuing_skip_conversation'
                else:
                    return 'grab_hire', 'continuing_grab_conversation'
        
        # 6. PRICING REQUESTS
        
        if any(word in message_lower for word in ['price', 'cost', 'quote', 'pricing']):
            # If materials mentioned, route based on materials
            if materials:
                if any(item in materials for item in light_items):
                    return 'mav', 'pricing_request_light_items'
                else:
                    return 'grab_hire', 'pricing_request_general'
            else:
                return 'grab_hire', 'pricing_request_no_materials'
        
        # 7. DEFAULT FALLBACK - GRAB HANDLES EVERYTHING ELSE
        return 'grab_hire', 'default_grab_handles_all'
    
    def _extract_materials(self, message: str) -> List[str]:
        """Extract materials/items mentioned in message"""
        message_lower = message.lower()
        
        all_materials = [
            # Heavy materials
            'soil', 'muck', 'rubble', 'concrete', 'brick', 'bricks', 'sand', 
            'gravel', 'stone', 'stones', 'hardcore', 'mortar', 'cement',
            'construction', 'building', 'demolition', 'asphalt',
            
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
    
    def _update_conversation_history(self, conversation_id: str, message: str, 
                                   response: str, agent_used: str):
        """Update conversation history"""
        if conversation_id not in self.conversation_history:
            self.conversation_history[conversation_id] = []
        
        self.conversation_history[conversation_id].append({
            "timestamp": datetime.now().isoformat(),
            "customer_message": message,
            "agent_response": response,
            "agent_used": agent_used
        })
        
        # Keep only last 10 messages per conversation
        if len(self.conversation_history[conversation_id]) > 10:
            self.conversation_history[conversation_id] = self.conversation_history[conversation_id][-10:]
    
    def get_conversation_history(self, conversation_id: str) -> List[Dict]:
        """Get conversation history for a specific conversation"""
        return self.conversation_history.get(conversation_id, [])
    
    def get_agent_stats(self) -> Dict[str, Any]:
        """Get statistics about agent usage"""
        agent_usage = {}
        total_messages = 0
        
        for conv_history in self.conversation_history.values():
            for entry in conv_history:
                agent = entry.get('agent_used', 'unknown')
                agent_usage[agent] = agent_usage.get(agent, 0) + 1
                total_messages += 1
        
        return {
            "total_messages_processed": total_messages,
            "agent_usage": agent_usage,
            "active_conversations": len(self.conversation_history)
        }
