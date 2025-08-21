import json 
from typing import Dict, Any, List
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain.tools import BaseTool
from langchain.prompts import ChatPromptTemplate
from langchain.memory import ConversationBufferWindowMemory

class GrabHireAgent:
    def __init__(self, llm, tools: List[BaseTool]):
        self.llm = llm
        self.tools = tools
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the WasteKing Grab Hire specialist agent.

EXACT TERMINOLOGY - Use word for word:
- 6-wheeler = 12-tonne capacity: "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."
- 8-wheeler = 16-tonne capacity: "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry."

BUSINESS RULES:
- Office hours transfers: £300+ to specialist
- Out of hours: NEVER transfer, take callback
- Always confirm grab terminology exactly as above
- Check postcode for access
- Suitable for heavy materials (soil, concrete, muck)

Transfer at £300+ during office hours only. for pricing always call get_pricing, no other word
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
    
    def process_message(self, message: str, context: Dict = None) -> str:
        try:
            response = self.executor.invoke({
                "input": message,
                "context": json.dumps(context) if context else "{}"
            })
            return response["output"]
        except Exception as e:
            return "I understand you need grab hire. What size grab lorry do you need - 6-wheeler or 8-wheeler?"
    
    def get_grab_terminology(self, grab_type: str) -> str:
        if "6" in grab_type or "six" in grab_type.lower():
            return "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry."
        elif "8" in grab_type or "eight" in grab_type.lower():
            return "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry."
        else:
            return "We have 6-wheeler (12-tonne) and 8-wheeler (16-tonne) grab lorries available. Which would suit your needs?"
