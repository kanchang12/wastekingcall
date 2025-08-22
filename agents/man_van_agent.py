import json 
import re
import os
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from utils.rules_processor import RulesProcessor

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        
        # Load rules from PDF properly - CORRECT PATH
        try:
            # PDF path: data/rules/all rules.pdf (data and agents are same level)
            pdf_path = os.path.join(os.path.dirname(__file__), "..", "data", "rules", "all rules.pdf")
            print(f"Loading Man & Van rules from: {pdf_path}")
            self.rules_processor = RulesProcessor(pdf_path=pdf_path)
            # Get rules specifically for man_and_van
            man_van_rules = self.rules_processor.get_rules_for_agent("man_and_van")
            rule_text = json.dumps(man_van_rules, indent=2)
            rule_text = rule_text.replace("{", "{{").replace("}", "}}")
            print(f"Loaded Man & Van rules: {len(rule_text)} characters")
        except Exception as e:
            print(f"Warning: Could not load rules from PDF: {e}")
            # Fallback rules if PDF loading fails
            rule_text = """
            CRITICAL MAN & VAN RULES:
            - CANNOT handle: bricks, concrete, soil, tiles, heavy construction waste, rubble, stones
            - CANNOT handle: items over 25kg per person
            - CANNOT handle: hazardous materials, asbestos, chemicals
            - CAN handle: furniture, household items, light garden waste, boxes, bags
            - IF customer has heavy/restricted items: DECLINE and suggest Skip Hire
            """
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", f"""You are the WasteKing Man and Van specialist - friendly, British, and NO HARDCODED DATA!

RULES FROM PDF - MUST FOLLOW:
{rule_text}

HEAVY ITEMS RULE - MANDATORY ENFORCEMENT:
- BRICKS, MORTAR, CONCRETE, SOIL, TILES = TOO HEAVY FOR MAN & VAN
- IF customer mentions these items: DECLINE and suggest Skip Hire
- Say: "Sorry mate, bricks/concrete/soil are too heavy for our Man & Van service. You'll need a Skip Hire for that type of waste. Let me connect you with our skip team!"

API PARAMETERS (only if items are suitable):
- service: "mav" 
- type: "4yd" or "6yd" or "8yd" or "12yd"
- postcode: no spaces

MANDATORY RULE - NO HARDCODED DATA:
- ONLY use data from customer message
- NEVER use example postcodes
- NEVER use fallback data
- IF missing postcode: ASK FOR IT
- IF missing items: ASK FOR THEM

WORKFLOW:
1. CHECK ITEMS FIRST - Are they suitable for Man & Van?
2. If TOO HEAVY: DECLINE and suggest Skip Hire
3. If SUITABLE but missing data: ASK for missing info
4. If SUITABLE and Ready for Pricing = True: Call smp_api
5. NEVER get pricing for heavy items or missing data

PERSONALITY:
- Start with: "Alright love!" or "Right then!"
- Be helpful but enforce rules strictly

MANDATORY: Only use REAL user data - no examples or hardcoded values!
"""),
            ("human", """Customer: {{input}}

Extracted data: {{extracted_info}}

INSTRUCTION: 
1. Check if items are suitable for Man & Van first
2. If unsuitable (heavy/restricted): DECLINE and suggest Skip Hire
3. If suitable and Ready for Pricing = True: Call smp_api with service="mav"
4. If suitable but missing data: ASK for missing info
"""),
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
    
    def check_item_suitability(self, items_text: str) -> Dict[str, Any]:
        """Check if items are suitable for Man & Van based on rules"""
        items_lower = items_text.lower()
        
        # Heavy/restricted items that Man & Van CANNOT handle
        restricted_items = [
            'brick', 'bricks', 'mortar', 'concrete', 'cement', 'soil', 'dirt', 'earth',
            'tile', 'tiles', 'stone', 'stones', 'rubble', 'hardcore', 'aggregate',
            'sand', 'gravel', 'plaster', 'plasterboard', 'drywall', 'asbestos',
            'industrial waste', 'construction waste', 'building waste', 'demolition'
        ]
        
        found_restricted = []
        for item in restricted_items:
            if item in items_lower:
                found_restricted.append(item)
        
        if found_restricted:
            return {
                "suitable": False,
                "reason": f"Man & Van cannot handle: {', '.join(found_restricted)}",
                "restricted_items": found_restricted,
                "suggestion": "Skip Hire recommended for heavy construction materials"
            }
        
        return {
            "suitable": True,
            "reason": "Items are suitable for Man & Van service"
        }
    
    def extract_and_validate_data(self, message: str) -> Dict[str, Any]:
        """Extract customer data and check item suitability - NO HARDCODED DATA"""
        data = {}
        missing = []
        
        # Extract postcode - NO SPACES, NO HARDCODED FALLBACKS
        postcode_found = False
        postcode_patterns = [
            r'postcode\s*:?\s*([A-Z0-9\s]+)',
            r'([A-Z]{1,2}\d{1,4}[A-Z]?\d?[A-Z]{0,2})',
            r'at\s+([A-Z0-9\s]{4,8})',
            r'in\s+([A-Z0-9\s]{4,8})',
        ]
        
        for pattern in postcode_patterns:
            matches = re.findall(pattern, message.upper())
            for match in matches:
                clean_match = match.strip().replace(' ', '')
                if len(clean_match) >= 4 and any(c.isdigit() for c in clean_match) and any(c.isalpha() for c in clean_match):
                    data['postcode'] = clean_match
                    postcode_found = True
                    print(f"🔧 POSTCODE EXTRACTED: '{match}' → '{clean_match}'")
                    break
            if postcode_found:
                break
        
        if not postcode_found:
            missing.append('postcode')
            print("❌ NO POSTCODE FOUND in message")
        
        # Extract items
        common_items = [
            'bags', 'furniture', 'sofa', 'chair', 'table', 'bed', 'mattress', 
            'books', 'clothes', 'boxes', 'appliances', 'fridge', 'freezer',
            'brick', 'bricks', 'mortar', 'concrete', 'soil', 'tiles', 'industrial'
        ]
        
        found_items = []
        message_lower = message.lower()
        
        for item in common_items:
            if item in message_lower:
                found_items.append(item)
        
        if found_items:
            data['items'] = ', '.join(found_items)
            print(f"🔧 ITEMS EXTRACTED: {data['items']}")
            
            # CHECK ITEM SUITABILITY
            suitability = self.check_item_suitability(data['items'])
            data['item_suitability'] = suitability
            
            if not suitability['suitable']:
                data['service_declined'] = True
                data['decline_reason'] = suitability['reason']
                data['alternative_service'] = 'Skip Hire'
                print(f"❌ ITEMS NOT SUITABLE: {suitability['reason']}")
                return data
        else:
            missing.append('items')
            print("❌ NO ITEMS FOUND in message")
        
        # Estimate volume (only if items are suitable)
        if 'items' in data and data.get('item_suitability', {}).get('suitable', False):
            volume_score = 0
            items_text = data['items'].lower()
            bag_matches = re.findall(r'(\d+)', items_text)
            for match in bag_matches:
                volume_score += int(match) if match.isdigit() else 3
            
            furniture_items = ['sofa', 'chair', 'table', 'bed', 'mattress']
            for item in furniture_items:
                if item in items_text:
                    volume_score += 5
            
            # Convert to size
            if volume_score <= 3:
                data['type'] = '4yd'
            elif volume_score <= 8:
                data['type'] = '6yd'
            elif volume_score <= 15:
                data['type'] = '8yd'
            else:
                data['type'] = '12yd'
        
        data['service'] = 'mav'
        data['missing_info'] = missing
        
        # Ready for pricing only if items are suitable AND we have real data
        has_postcode = 'postcode' in data
        has_suitable_items = 'items' in data and data.get('item_suitability', {}).get('suitable', False)
        data['ready_for_pricing'] = has_postcode and has_suitable_items and not data.get('service_declined', False)
        
        print(f"🔧 READY FOR PRICING: {data['ready_for_pricing']}")
        print(f"🔧 MISSING INFO: {missing}")
        
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        extracted = self.extract_and_validate_data(message)
        
        # If service is declined due to unsuitable items
        if extracted.get('service_declined', False):
            extracted_info = f"""
ITEMS NOT SUITABLE FOR MAN & VAN!
Items Found: {extracted.get('items', 'N/A')}
Decline Reason: {extracted.get('decline_reason', 'Heavy items detected')}
Alternative: {extracted.get('alternative_service', 'Skip Hire')}
Action Required: DECLINE and suggest Skip Hire
"""
        else:
            extracted_info = f"""
Postcode: {extracted.get('postcode', 'NOT PROVIDED')}
Items: {extracted.get('items', 'NOT PROVIDED')}
Item Suitability: {extracted.get('item_suitability', {}).get('suitable', 'Unknown')}
Estimated Size: {extracted.get('type', 'N/A')}
Service: mav
Ready for Pricing: {extracted.get('ready_for_pricing', False)}
Missing: {[x for x in extracted.get('missing_info', []) if x in ['postcode', 'items']]}
"""
        
        agent_input = {
            "input": message,
            "extracted_info": extracted_info
        }
        
        if context:
            for k, v in context.items():
                agent_input[k] = v
                
        agent_input.update(extracted)
        response = self.executor.invoke(agent_input)
        return response["output"]
