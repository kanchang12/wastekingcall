import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate

class SkipHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
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

EXACT SCRIPTS - Use word for word:
- Heavy materials limit: "For heavy materials such as soil & rubble, the largest skip you can have is 8-yard. Shall I get you the cost of an 8-yard skip?"
- Sofa prohibition: "No, sofa is not allowed in a skip as it's upholstered furniture. We can help with Man & Van service."
- Road placement: "For any skip placed on the road, a council permit is required. We'll arrange this for you and include the cost in your quote."
- MAV suggestion for light materials + 8yard or smaller: "Since you have light materials for an 8-yard skip, our man & van service might be more cost-effective. We do all the loading for you and only charge for what we remove. Shall I quote both the skip and man & van options so you can compare prices?"

QUALIFICATION PROCESS:
1. If missing NAME: "Hello! I'm here to help with your skip hire. What's your name?"
2. If missing POSTCODE: "Lovely! And what's your postcode for delivery?"  
3. If missing WASTE TYPE: "Perfect! What type of waste will you be putting in the skip?"
4. Only AFTER getting all 3, call smp_api with: action="get_pricing", postcode="LS14ED", service="skip-hire", type_="8yard"

WASTE TYPE RULES:
- Heavy (soil, rubble, concrete, bricks) → max 8yard
- Light (household, garden, furniture, general, office) → any size + suggest MAV if ≤8yard
- Sofas → refuse, suggest MAV
- If 10+ yard requested for heavy → use exact script

NEVER skip qualification questions. NEVER call smp_api without name, postcode, waste type.
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
            max_iterations=3
        )
    
    def extract_and_validate_data(self, message: str) -> Dict[str, Any]:
        """Extract customer data and check what's missing"""
        data = {}
        missing = []
        
        # Extract name
        name_patterns = [
            r'name\s+(?:is\s+)?(\w+)',
            r'i\'?m\s+(\w+)',
            r'my\s+name\s+is\s+(\w+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                data['name'] = match.group(1).title()
                print(f"🔍 Extracted name: {data['name']}")
                break
        if 'name' not in data:
            missing.append('name')
        
        # Extract postcode - handle spaces correctly
        postcode_patterns = [
            r'postcode\s+(?:is\s+)?([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})',
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b'
        ]
        for pattern in postcode_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                pc = match.group(1).upper()
                # Ensure proper spacing for UK postcodes
                if len(pc.replace(' ', '')) >= 5:
                    if ' ' not in pc and len(pc) >= 6:
                        # Add space before last 3 chars: LS14ED → LS1 4ED
                        data['postcode'] = pc[:-3] + ' ' + pc[-3:]
                    else:
                        data['postcode'] = pc
                    print(f"🔍 Extracted postcode: {data['postcode']}")
                    break
        if 'postcode' not in data:
            missing.append('postcode')
        
        # Extract waste type
        waste_indicators = {
            'heavy': ['soil', 'rubble', 'concrete', 'bricks', 'stone', 'hardcore', 'building'],
            'light': ['household', 'general', 'office', 'party', 'garden', 'furniture', 'wood', 'cardboard'],
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
            print(f"🔍 Extracted waste: {data['waste_type']} (category: {waste_category})")
        else:
            missing.append('waste_type')
        
        # Extract skip size
        size_patterns = [
            r'(\d+)\s*(?:yard|yd)',
            r'(four|4|six|6|eight|8|ten|10|twelve|12|fourteen|14)\s*(?:yard|yd)'
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
                data['requested_size'] = f"{size_num}yard"
                print(f"🔍 Extracted size: {data['requested_size']}")
                break
        
        if 'requested_size' not in data:
            data['requested_size'] = '8yard'  # Default
        
        data['missing_info'] = missing
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        # Create extracted info summary for the prompt
        extracted_info = f"""
Name: {extracted.get('name', 'NOT PROVIDED')}
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Waste Type: {extracted.get('waste_type', 'NOT PROVIDED')}
Waste Category: {extracted.get('waste_category', 'unknown')}
Requested Size: {extracted.get('requested_size', '8yard')}
Missing Info: {extracted.get('missing_info', [])}
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
