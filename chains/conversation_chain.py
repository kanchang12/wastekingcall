import json
from typing import Dict, Any, List
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import BaseMessage

class ConversationChain:
    def __init__(self, llm):
        self.llm = llm
        self.memory = ConversationBufferWindowMemory(k=10, return_messages=True)
        
        self.prompt = PromptTemplate(
            input_variables=["conversation_history", "current_message", "business_rules", "customer_data"],
            template='''You are the WasteKing AI assistant managing a customer conversation.

BUSINESS RULES TO FOLLOW:
{business_rules}

CONVERSATION HISTORY:
{conversation_history}

CUSTOMER DATA COLLECTED:
{customer_data}

CURRENT MESSAGE: {current_message}

Respond following these rules:
1. Use exact scripts where specified
2. Collect missing mandatory info (name, postcode, waste type)
3. Apply all business rules
4. Be helpful and professional
5. One question at a time

Response:'''
        )
        
        self.chain = LLMChain(
            llm=self.llm,
            prompt=self.prompt,
            memory=self.memory,
            verbose=True
        )
    
    def process_conversation(self, message: str, customer_data: Dict = None, business_rules: str = "") -> str:
        try:
            response = self.chain.run(
                current_message=message,
                customer_data=json.dumps(customer_data or {}),
                business_rules=business_rules,
                conversation_history=self._format_history()
            )
            return response.strip()
        except Exception as e:
            return "I understand. How can I help you today?"
    
    def _format_history(self) -> str:
        messages = self.memory.chat_memory.messages[-6:]
        formatted = []
        for msg in messages:
            if hasattr(msg, 'content'):
                formatted.append(f"{msg.__class__.__name__}: {msg.content}")
        return "\n".join(formatted)
    
    def clear_memory(self):
        self.memory.clear()
    
    def get_conversation_summary(self) -> str:
        messages = self.memory.chat_memory.messages
        if not messages:
            return "No conversation yet"
        
        summary_parts = []
        for msg in messages[-10:]:
            if hasattr(msg, 'content'):
                summary_parts.append(msg.content[:100])
        
        return " | ".join(summary_parts)
