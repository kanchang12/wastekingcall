# agents/streamlined_agent.py - Works with automated orchestrator
import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

class StreamlinedWasteAgent:
    """Streamlined agent that works with automated orchestrator - no repeat questions"""
    
    def __init__(self, llm, tools: List[BaseTool], service_type: str = "grab"):
        self.llm = llm
        self.tools = tools
        self.service_type = service_type
        
        # Simple, direct prompt that doesn't ask repeat questions
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are a WasteKing {service_type} specialist. Be DIRECT and EFFICIENT.

CRITICAL RULES:
1. NEVER ask for information that's already provided in the context
2. If you have postcode + waste type: IMMEDIATELY call smp_api for pricing
3. If pricing fails: give a helpful response anyway
4. Be friendly but FAST
5. ALWAYS log your tool calls completely

YOUR CONTEXT CONTAINS:
- Customer's previous answers
- Extracted information (postcode, waste type, name, phone)
- Conversation history

API CALL FORMAT - ALWAYS USE EXACT PARAMETERS:
smp_api(action="get_pricing", postcode="LS14ED", service="{service_type}", type="8yd")

NEVER ASK AGAIN for data that's in your context!

PRICING GUIDELINES (from PDF rules):
- Skip Hire: £85-150 depending on size and location
- Man & Van: £120-180 depending on items and distance  
- Grab Hire: £180-250 depending on load size
- Always add "plus VAT" to quoted prices
- Include delivery and collection in price"""),
            ("human", """Customer message: {input}

AVAILABLE CONTEXT:
Postcode: {postcode}
Waste type: {waste_type}  
Name: {name}
Phone: {phone}
Previous conversation: {conversation_history}

INSTRUCTION: Use this context. Don't ask for data you already have! Call smp_api if you have postcode and waste type!"""),
            ("placeholder", "{agent_scratchpad}")
        ])
        
        self.agent = create_openai_functions_agent(
            llm=self.llm,
            tools=self.tools,
            prompt=self.prompt
        )
        
        self.executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=True,
            max_iterations=3,
            handle_parsing_errors=True
        )
    
    def process_message(self, message: str, context: Dict = None) -> str:
        """Process message using context to avoid repeat questions"""
        
        if not context:
            context = {}
        
        # Extract all available data
        extracted = context.get('extracted_info', {})
        
        postcode = (context.get('postcode') or 
                   extracted.get('postcode') or 
                   self._extract_postcode(message) or 
                   "NOT PROVIDED")
        
        waste_type = (context.get('waste_type') or 
                     extracted.get('waste_type') or 
                     self._extract_waste_type(message) or 
                     "NOT PROVIDED")
        
        name = (context.get('name') or 
               extracted.get('name') or 
               self._extract_name(message) or 
               "NOT PROVIDED")
        
        phone = (context.get('phone') or 
                extracted.get('phone') or 
                self._extract_phone(message) or 
                "NOT PROVIDED")
        
        # Get conversation history
        messages = context.get('messages', [])
        conversation_history = self._format_conversation_history(messages)
        
        print(f"🔧 STREAMLINED {self.service_type.upper()} AGENT DATA:")
        print(f"   📍 Postcode: {postcode}")
        print(f"   🗑️ Waste: {waste_type}")
        print(f"   👤 Name: {name}")
        print(f"   📞 Phone: {phone}")
        print(f"   📜 Has Conversation History: {'Yes' if conversation_history != 'No previous conversation' else 'No'}")
        
        # Check if we can get pricing immediately
        if (postcode != "NOT PROVIDED" and 
            waste_type != "NOT PROVIDED" and 
            self._is_pricing_request(message, conversation_history)):
            
            print(f"🔧 READY FOR PRICING API CALL")
            print(f"🔧 TOOL CALL WILL BE: smp_api(action='get_pricing', postcode='{postcode.replace(' ', '')}', service='{self.service_type}', type='8yd')")
            
            # Call API directly without asking questions
            try:
                agent_input = {
                    "input": message,
                    "postcode": postcode.replace(' ', ''),
                    "waste_type": waste_type,
                    "name": name,
                    "phone": phone,
                    "conversation_history": conversation_history,
                    "api_action": "get_pricing",
                    "service": self.service_type,
                    "type": "8yd"
                }
                
                print(f"🔧 CALLING AGENT EXECUTOR WITH: {agent_input}")
                response = self.executor.invoke(agent_input)
                print(f"🔧 AGENT EXECUTOR RESPONSE: {response}")
                return response["output"]
                
            except Exception as e:
                print(f"❌ API call failed: {e}")
                return self._fallback_response(postcode, waste_type, name)
        
        # If we're missing critical data, ask for it ONCE
        missing = []
        if postcode == "NOT PROVIDED":
            missing.append("postcode")
        if waste_type == "NOT PROVIDED":
            missing.append("what type of waste you have")
        
        if missing:
            if len(missing) == 1:
                return f"I just need your {missing[0]} to give you a price."
            else:
                return f"I need your {' and '.join(missing)} to get you a quote."
        
        # Handle general questions
        return self._handle_general_question(message, context)
    
    def _is_pricing_request(self, message: str, history: str) -> bool:
        """Check if this is a pricing request or continuation"""
        
        message_lower = message.lower()
        
        # Explicit pricing requests
        pricing_keywords = [
            'price', 'cost', 'quote', 'much', 'how much', 'pricing',
            'collection', 'hire', 'book', 'want', 'need'
        ]
        
        if any(keyword in message_lower for keyword in pricing_keywords):
            return True
        
        # Check if we've already been discussing this service
        if any(word in history.lower() for word in [self.service_type, 'waste', 'collection']):
            return True
        
        # Default to yes if we have the data
        return True
    
    def _extract_postcode(self, message: str) -> str:
        """Extract postcode from message"""
        patterns = [
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\d[A-Z]{2})\b',
            r'\b(LS\d{4})\b',
            r'\b([A-Z]{1,2}\d{1,4})\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message.upper())
            if match:
                return match.group(1).replace(' ', '')
        
        return ""
    
    def _extract_waste_type(self, message: str) -> str:
        """Extract waste type from message"""
        message_lower = message.lower()
        
        waste_types = [
            'soil', 'muck', 'rubble', 'concrete', 'brick', 'bricks',
            'furniture', 'sofa', 'construction', 'building', 'garden',
            'household', 'general', 'mixed', 'bags', 'clearance'
        ]
        
        found = []
        for waste in waste_types:
            if waste in message_lower:
                found.append(waste)
        
        return ', '.join(found) if found else ""
    
    def _extract_name(self, message: str) -> str:
        """Extract name from message"""
        patterns = [
            r'\bname\s+is\s+([A-Z][a-z]+)\b',
            r'\bmy\s+name\s+is\s+([A-Z][a-z]+)\b',
            r'\bi\s+am\s+([A-Z][a-z]+)\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)
        
        return ""
    
    def _extract_phone(self, message: str) -> str:
        """Extract phone from message"""
        patterns = [
            r'\b(07\d{9})\b',
            r'\b(0\d{10})\b'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)
        
        return ""
    
    def _format_conversation_history(self, messages: List[Dict]) -> str:
        """Format conversation history for context"""
        
        if not messages:
            return "No previous conversation"
        
        # Get last 3 messages
        recent = messages[-3:] if len(messages) > 3 else messages
        
        formatted = []
        for msg in recent:
            customer = msg.get('customer_message', '')
            agent = msg.get('agent_response', '')
            
            if customer:
                formatted.append(f"Customer: {customer}")
            if agent:
                formatted.append(f"Agent: {agent[:100]}...")
        
        return '\n'.join(formatted)
    
    def _fallback_response(self, postcode: str, waste_type: str, name: str) -> str:
        """Provide helpful response when API fails"""
        
        service_name = self.service_type.replace('_', ' ').title()
        
        if name != "NOT PROVIDED":
            greeting = f"Hi {name}! "
        else:
            greeting = "Right then! "
        
        response = f"""{greeting}I can help you with {service_name} in {postcode} for {waste_type}.

Our typical prices are:
• Skip Hire: £85-150 (depending on size)
• Man & Van: £120-180 (depending on items)  
• Grab Hire: £180-250 (depending on load)

I'll get you exact pricing and can arrange collection. Would you like to proceed?"""
        
        return response
    
    def _handle_general_question(self, message: str, context: Dict) -> str:
        """Handle general questions about the service"""
        
        message_lower = message.lower()
        
        if any(word in message_lower for word in ['what', 'how', 'when', 'where']):
            
            if 'size' in message_lower or 'big' in message_lower:
                return f"Our {self.service_type} service typically handles 6-8 cubic yards. Perfect for most household and commercial waste."
            
            elif 'when' in message_lower or 'time' in message_lower:
                return "We can usually arrange collection within 1-2 days. Same day available for urgent jobs."
            
            elif 'what' in message_lower and 'accept' in message_lower:
                if self.service_type == 'mav':
                    return "Man & Van can handle: furniture, appliances, household items, office clearance. NOT heavy materials like bricks or soil."
                elif self.service_type == 'grab':
                    return "Grab Hire handles: soil, rubble, concrete, heavy construction waste, large volumes."
                else:
                    return "Skip Hire handles: mixed waste, construction debris, garden waste, household clearance."
            
            elif 'how' in message_lower and 'work' in message_lower:
                return f"Simple! Give me your postcode and waste type, I'll quote you instantly, then we arrange collection that suits you."
        
        # Default response
        return f"I'm here to help with {self.service_type.replace('_', ' ').title()}. What would you like to know?"

# Factory function to create service-specific agents
def create_service_agent(llm, tools: List[BaseTool], service_type: str) -> StreamlinedWasteAgent:
    """Create a streamlined agent for specific service type"""
    return StreamlinedWasteAgent(llm, tools, service_type)

# Replace the existing agents with these:
def SkipHireAgent(llm, tools):
    return create_service_agent(llm, tools, "skip")

def ManVanAgent(llm, tools):  
    return create_service_agent(llm, tools, "mav")

def GrabHireAgent(llm, tools):
    return create_service_agent(llm, tools, "grab")
