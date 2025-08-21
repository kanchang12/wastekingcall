import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from rules_processor import RulesProcessor 
from langchain.prompts import ChatPromptTemplate

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.rules_processor = RulesProcessor()
        rule_text = "\n".join(json.dumps(self.rules_processor.get_rules_for_agent(agent), indent=2) for agent in ["skip_hire", "man_and_van", "grab_hire"])
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are the WasteKing Man & Van specialist - friendly, British, and RULE-FOLLOWING!

PERSONALITY - CRITICAL:
- Start with: "Alright love!" or "Hello there!" or "Right then!" 
- Use British phrases: "Brilliant!", "Lovely!", "Smashing!", "Perfect!"
- Be chatty: "How's your day going?", "Lovely to hear from you!"
- Sound human and warm, not robotic

BUSINESS RULES - FOLLOW EXACTLY:
1. ALWAYS collect NAME, POSTCODE, ITEMS LIST before pricing
2. Man & Van includes collection AND disposal
3. We do ALL the loading for customers
4. Heavy items (dumbbells, kettlebells) may have surcharges
5. Access charges for upper floors
6. Upholstered furniture requires special disposal (EA regulations)
Follow all relevant rules from the team:\n{rule_text}
QUALIFICATION PROCESS:
1. If missing NAME: "Hello! I'm here to help with Man & Van. What's your name?"
2. If missing POSTCODE: "Lovely! And what's your postcode for collection?"
3. If missing ITEMS: "Perfect! What items do you need collected?"
4. Only AFTER getting all 3, call smp_api with: action="get_pricing", postcode="{postcode}", service="mav", type="{type}yd"

VOLUME ESTIMATION:
- Few items (1-3 bags, small furniture) → 4yd
- Medium load (3-6 bags, some furniture) → 6yd  
- Large load (6+ bags, multiple furniture) → 8yd
- Very large (house clearance) → 12yd

WORKFLOW:
1. Get pricing with smp_api action="get_pricing"
2. If customer wants to book, call smp_api action="create_booking_quote"
3. For payment, call smp_api action="take_payment"

RESPONSES:
- Always confirm: "We'll do all the loading and disposal for you"
- Mention surcharges upfront if heavy items
- Explain EA regulations for upholstered furniture
- Give clear next steps for booking

NEVER skip qualification questions. NEVER call smp_api without name, postcode, items.
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
                data['firstName'] = match.group(1).title()
                break
        if 'firstName' not in data:
            missing.append('name')
        
        # Extract postcode
        postcode_patterns = [
            r'postcode\s+(?:is\s+)?([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})',
            r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b'
        ]
        for pattern in postcode_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                pc = match.group(1).upper()
                if len(pc.replace(' ', '')) >= 5:
                    if ' ' not in pc and len(pc) >= 6:
                        data['postcode'] = pc[:-3] + ' ' + pc[-3:]
                    else:
                        data['postcode'] = pc
                    break
        if 'postcode' not in data:
            missing.append('postcode')
        
        # Extract items
        common_items = [
            'bags', 'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 
            'books', 'clothes', 'dumbbells', 'kettlebell', 'boxes', 'appliances',
            'fridge', 'freezer'
        ]
        
        found_items = []
        extra_items = []
        message_lower = message.lower()
        
        # Check for extra items that incur surcharges
        surcharge_items = ['fridge', 'freezer', 'mattress', 'sofa', 'furniture']
        for item in surcharge_items:
            if item in message_lower:
                extra_items.append(item)
        
        for item in common_items:
            if item in message_lower:
                found_items.append(item)
        
        # Extract quantity indicators
        quantity_indicators = []
        quantity_patterns = [
            r'(\d+)\s*(?:bags?|boxes?|items?)',
            r'(few|several|many)\s*(?:bags?|boxes?|items?)',
            r'(one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:bags?|boxes?|items?)'
        ]
        
        for pattern in quantity_patterns:
            matches = re.findall(pattern, message_lower)
            quantity_indicators.extend(matches)
        
        if found_items or quantity_indicators:
            items_desc = []
            if quantity_indicators:
                items_desc.extend(quantity_indicators)
            if found_items:
                items_desc.extend(found_items)
            data['items'] = ', '.join(items_desc)
        else:
            missing.append('items')
        
        if extra_items:
            data['extra_items'] = ','.join(extra_items)
        
        # Estimate volume based on items
        volume_score = 0
        if 'items' in data:
            items_text = data['items'].lower()
            # Count bags/boxes
            bag_matches = re.findall(r'(\d+).*?bags?', items_text)
            for match in bag_matches:
                volume_score += int(match) if match.isdigit() else 3
            
            # Add for furniture
            furniture_items = ['sofa', 'chair', 'table', 'bed', 'mattress', 'appliances']
            for item in furniture_items:
                if item in items_text:
                    volume_score += 5
            
            # Add for heavy items
            heavy_items = ['dumbbells', 'kettlebell', 'weights']
            for item in heavy_items:
                if item in items_text:
                    volume_score += 2
                    data['has_heavy_items'] = True
        
        # Convert volume score to size
        if volume_score <= 3:
            data['type'] = '4yd'
        elif volume_score <= 8:
            data['type'] = '6yd'
        elif volume_score <= 15:
            data['type'] = '8yd'
        else:
            data['type'] = '12yd'
        
        # Extract access information
        access_keywords = ['floor', 'stairs', 'lift', 'ground', 'first', 'second', 'third']
        access_info = []
        for keyword in access_keywords:
            if keyword in message_lower:
                access_info.append(keyword)
        
        if access_info:
            data['access_info'] = ', '.join(access_info)
            # Check for upper floor charges
            upper_floors = ['first', 'second', 'third', 'fourth', 'fifth']
            if any(floor in message_lower for floor in upper_floors):
                data['upper_floor_charge'] = True
        
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
        data['service'] = 'mav'
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        # Create extracted info summary for the prompt
        extracted_info = f"""
Name: {extracted.get('firstName', 'NOT PROVIDED')}
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Items: {extracted.get('items', 'NOT PROVIDED')}
Estimated Size: {extracted.get('type', '8yd')}
Extra Items: {extracted.get('extra_items', 'none')}
Heavy Items: {extracted.get('has_heavy_items', False)}
Upper Floor: {extracted.get('upper_floor_charge', False)}
Access Info: {extracted.get('access_info', 'none')}
Phone: {extracted.get('phone', 'NOT PROVIDED')}
Email: {extracted.get('emailAddress', 'NOT PROVIDED')}
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
