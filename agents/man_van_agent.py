import json 
import re
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory

class ManVanAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Man & Van specialist agent.

BUSINESS RULES:
- Man & Van service includes collection and disposal
- We do all the loading for customers
- Pricing based on volume and item types
- Heavy items (dumbbells, kettlebells) may have surcharges
- Access charges apply for upper floors
- Upholstered furniture requires special disposal (EA regulations)

PARAMETER EXTRACTION - CRITICAL:
When calling smp_api for pricing, extract and pass these parameters:
- postcode: Extract from "postcode LS14ED" format
- waste_type: Extract items mentioned (books, clothes, dumbbells, etc)
- skip_size: Use "8yd" format based on volume estimate
- service_type: Use "mav"

Always collect: name, postcode, items list before pricing. for pricing always call get_pricing, no other word
"""),
            ("human", "{input}"),
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
            memory=self.memory,
            verbose=True,
            max_iterations=3
        )
    
    def extract_data(self, message: str) -> Dict[str, str]:
        data = {}
        
        # Extract postcode - only valid UK postcodes
        postcode_match = re.search(r'postcode\s+([A-Z0-9]+)', message, re.IGNORECASE)
        if postcode_match:
            pc = postcode_match.group(1).upper()
            # Reject invalid postcodes like "LS14EKODELTA"
            if len(pc) <= 8 and not any(word in pc for word in ['DELTA', 'ECO', 'KO']):
                data['postcode'] = pc
        
        # Extract items/waste type
        items = []
        item_keywords = ['books', 'clothes', 'dumbbells', 'kettlebell', 'furniture', 'sofa']
        for item in item_keywords:
            if item in message.lower():
                items.append(item)
        if items:
            data['waste_type'] = ', '.join(items)
        
        # Extract volume and convert to skip size format
        volume_match = re.search(r'(\w+)\s+cubic\s+yards?', message, re.IGNORECASE)
        if volume_match:
            volume_word = volume_match.group(1).lower()
            volume_map = {'one': '4yard', 'two': '6yard', 'three': '8yard', 'four': '12yard'}
            data['skip_size'] = volume_map.get(volume_word, '8yard')
        
        # Extract name
        name_match = re.search(r'name\s+(\w+)', message, re.IGNORECASE)
        if name_match:
            data['name'] = name_match.group(1)
            
        # Extract contact
        contact_match = re.search(r'contact\s+(\d+)', message, re.IGNORECASE)
        if contact_match:
            data['contact'] = contact_match.group(1)
            
        return data
    
    def process_message(self, message: str, context: Dict = None) -> str:
        try:
            # Extract data from message
            extracted = self.extract_data(message)
            
            # Pass context keys as part of the agent input so tools get them
            agent_input = {
                "input": message
            }
    
            if context:
                # flatten context dict into input for tools
                for k, v in context.items():
                    agent_input[k] = v  
            
            # Add extracted data to agent input so tools can access it
            for k, v in extracted.items():
                agent_input[k] = v
    
            response = self.executor.invoke(agent_input)
            return response["output"]
        except Exception as e:
            return "I can help you with Man & Van collection service. Please provide your postcode and tell me what items you need collected."
