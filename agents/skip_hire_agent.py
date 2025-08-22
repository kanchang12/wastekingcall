import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.rules_processor = RulesProcessor()
        
        # Get rules and escape curly braces for template
        raw_rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        rule_text = raw_rule_text.replace("{", "{{").replace("}", "}}")

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Skip Hire specialist - friendly, British, and RULE-FOLLOWING!

PERSONALITY - CRITICAL:
- Start with: "Alright love!" or "Hello there!" or "Right then!"
- Use British phrases: "Brilliant!", "Lovely!", "Smashing!", "Perfect!"
- Be chatty: "How's your day going?", "Lovely to hear from you!"
- Sound human and warm, not robotic

BUSINESS RULES - FOLLOW EXACTLY:
1. ALWAYS collect NAME, POSTCODE, WASTE TYPE before pricing
2. For heavy materials (soil, rubble, concrete, bricks): MAX 8-yard skip
3. 12-yard skips ONLY for light materials (household, garden, furniture)
4. Sunday deliveries have surcharge
5. Check the time and never transfer during out of office hours

QUALIFICATION PROCESS - SMART WORKFLOW:
1. FIRST: Check what info customer has already provided
2. If customer provides postcode + waste type + size: GET PRICING IMMEDIATELY (even without name)
3. If missing critical info: Ask for it quickly, then get pricing
4. Name can be collected during booking, not required for pricing

PRICING FLOW - IMMEDIATE:
- If you have postcode, waste type, and size: Call smp_api immediately
- Give price first: "Right then! For an 8-yard skip for construction waste in LS14ED, that will be £[price]."
- THEN ask: "What's your name so I can prepare the booking?"

EXACT SCRIPTS - Use word for word:
- Heavy materials limit: "For heavy materials such as soil and rubble, the largest skip you can have is 8-yard. Shall I get you the cost of an 8-yard skip?"
- Sofa prohibition: "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service."
- Road placement: "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote."
- MAV suggestion for light materials + 8yard or smaller: "Since you have light materials for an 8-yard skip, our man and van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man and van options so you can compare prices?"

WASTE TYPE RULES:
- Heavy (soil, rubble, concrete, bricks, construction) = max 8yd
- Light (household, garden, furniture, general, office) = any size + suggest MAV if 8yd or smaller
- Sofas = refuse, suggest MAV
- If 10+ yard requested for heavy = use exact script

CRITICAL: If customer provides enough info for pricing, GET PRICING IMMEDIATELY. Don't ask for name first.

Follow all relevant rules from the team:
""" + rule_text + """

WORKFLOW:
1. Extract all available data immediately
2. If have postcode + waste type + size: Call smp_api for pricing NOW
3. Give price immediately
4. Collect missing details (like name) for booking
5. Complete booking when ready

NEVER delay pricing if you have the core info. ALWAYS prioritize getting the price quickly.
"""),
            ("human", "Customer: {input}\n\nExtracted data: {extracted_info}"),
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
            max_iterations=5
        )
    
    def extract_and_validate_data(self, message: str) -> Dict[str, Any]:
        """Extract customer data and check what's missing"""
        data = {}
        missing = []
        
        # Extract name - more flexible patterns
        name_patterns = [
            r'name\s+(?:is\s+)?(\w+)',
            r'i\'?m\s+(\w+)',
            r'my\s+name\s+is\s+(\w+)',
            r'call\s+me\s+(\w+)',
            r'this\s+is\s+(\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['firstName'] = match.group(1).title()
                break
        if 'firstName' not in data:
            missing.append('name')
        
        # Extract postcode - improved patterns
        postcode_patterns = [
            r'postcode\s+(?:is\s+)?([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})',
            r'in\s+([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})',
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b',
            r'([A-Z]{2}\d{1,2}\s*\d[A-Z]{2})'  # More flexible for formats like LS14ED
        ]
        for pattern in postcode_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                pc = match.group(1).upper()
                if len(pc.replace(' ', '')) >= 5:
                    if ' ' not in pc and len(pc) >= 6:
                        # Format postcode with space: LS14ED -> LS1 4ED
                        data['postcode'] = pc[:-3] + ' ' + pc[-3:]
                    else:
                        data['postcode'] = pc
                    break
        if 'postcode' not in data:
            missing.append('postcode')
        
        # Extract waste type - expanded patterns
        waste_indicators = {
            'heavy': ['soil', 'rubble', 'concrete', 'bricks', 'stone', 'hardcore', 'building', 'construction', 'demolition'],
            'light': ['household', 'general', 'office', 'party', 'garden', 'furniture', 'wood', 'cardboard', 'rubbish'],
            'prohibited': ['sofa', 'sofas', 'mattress', 'upholstered']
        }
        
        found_waste = []
        waste_category = None
        
        message_lower = message.lower()
        for category, keywords in waste_indicators.items():
            for keyword in keywords:
                if keyword in message_lower:
                    found_waste.append(keyword)
                    waste_category = category
                    break
        
        if found_waste:
            data['waste_type'] = ', '.join(found_waste)
            data['waste_category'] = waste_category
        else:
            missing.append('waste_type')
        
        # Extract skip size - improved patterns
        size_patterns = [
            r'(\d+)\s*(?:yard|yd|y)',
            r'(four|4|six|6|eight|8|ten|10|twelve|12|fourteen|14)\s*(?:yard|yd|y)',
            r'(four|4|six|6|eight|8|ten|10|twelve|12|fourteen|14)\s*(?:yard|yd|y)?\s*skip'
        ]
        size_map = {
            'four': '4', '4': '4', 'six': '6', '6': '6', 'eight': '8', '8': '8',
            'ten': '10', '10': '10', 'twelve': '12', '12': '12', 'fourteen': '14', '14': '14'
        }
        
        for pattern in size_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                size_word = match.group(1).lower()
                size_num = size_map.get(size_word, size_word)
                data['type'] = f"{size_num}yd"
                break

        if 'type' not in data:
            data['type'] = '8yd'  # Default
        
        # Extract additional details
        # Check for day/date mentions
        day_patterns = [
            r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            r'next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            r'this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
        ]
        for pattern in day_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['requested_day'] = match.group(1).lower()
                break
        
        # Check for location (driveway/road)
        if 'driveway' in message_lower:
            data['placement'] = 'driveway'
        elif 'road' in message_lower:
            data['placement'] = 'road'
            
        # Extract phone
        phone_patterns = [
            r'phone\s+(?:is\s+)?(\d{11})',
            r'mobile\s+(?:is\s+)?(\d{11})',
            r'\b(\d{11})\b'
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                data['phone'] = match.group(1)
                break
        
        # Extract email
        email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        email_match = re.search(email_pattern, message)
        if email_match:
            data['emailAddress'] = email_match.group()
        
        data['missing_info'] = missing
        data['service'] = 'skip'
        
        # Check if we have enough for pricing
        has_core_info = 'postcode' in data and 'waste_type' in data and 'type' in data
        data['ready_for_pricing'] = has_core_info
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        # Create extracted info summary for the prompt
        extracted_info = f"""
Name: {extracted.get('firstName', 'NOT PROVIDED')}
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Waste Type: {extracted.get('waste_type', 'NOT PROVIDED')}
Waste Category: {extracted.get('waste_category', 'unknown')}
Skip Size: {extracted.get('type', '8yd')}
Placement: {extracted.get('placement', 'not specified')}
Requested Day: {extracted.get('requested_day', 'not specified')}
Phone: {extracted.get('phone', 'NOT PROVIDED')}
Email: {extracted.get('emailAddress', 'NOT PROVIDED')}
Missing Info: {extracted.get('missing_info', [])}
Ready for Pricing: {extracted.get('ready_for_pricing', False)}
"""
        
        agent_input = {
            "input": message,
            "extracted_info": extracted_info
        }
        
        if context:
            for k, v in context.items():
                agent_input[k] = v
                
        # Add extracted data for tools
        agent_input.update(extracted)

        response = self.executor.invoke(agent_input)
        return response["output"]
