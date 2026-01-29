import json
import os
from typing import Optional, Dict, Any, List
import streamlit as st

class LLMClient:
    """Provider-agnostic LLM wrapper for JSON generation and chat."""
    
    def __init__(self, provider: str = "anthropic"):
        """Initialize with provider ('anthropic' or 'openai')."""
        self.provider = provider
        self._load_secrets()
    
    def _load_secrets(self):
        """Load API keys from environment or Streamlit secrets."""
        try:
            # Try to get provider from secrets, default to openai
            provider = st.secrets.get("LLM_PROVIDER", "openai") if hasattr(st, 'secrets') else os.getenv("LLM_PROVIDER", "openai")
            self.provider = provider
            
            if self.provider == "anthropic":
                self.api_key = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
                if not self.api_key:
                    raise ValueError("ANTHROPIC_API_KEY not found in secrets or environment")
                from anthropic import Anthropic
                self.client = Anthropic(api_key=self.api_key)
            elif self.provider == "openai":
                self.api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
                if not self.api_key:
                    raise ValueError("OPENAI_API_KEY not found in secrets or environment")
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            else:
                raise ValueError(f"Unknown provider: {self.provider}")
        except Exception as e:
            st.error(f"LLM initialization error: {str(e)}")
            raise
    
    def generate_json(self, prompt: str, schema_hint: str = "") -> Dict[str, Any]:
        """Generate JSON from a prompt."""
        full_prompt = f"{prompt}\n\nReturn ONLY valid JSON matching this structure:\n{schema_hint}"
        
        if self.provider == "anthropic":
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": full_prompt
                    }
                ]
            )
            text = response.content[0].text
        else:  # openai
            response = self.client.chat.completions.create(
                model="gpt-4o",
                max_tokens=4096,
                temperature=1,
                messages=[
                    {
                        "role": "user",
                        "content": full_prompt
                    }
                ]
            )
            text = response.choices[0].message.content
        
        return self._parse_json(text)
    
    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7
    ) -> Dict[str, Any]:
        """Chat completion returning JSON."""
        if self.provider == "anthropic":
            messages = [{"role": "user", "content": user_message}]
            response = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=4096,
                system=system_prompt,
                temperature=temperature,
                messages=messages
            )
            text = response.content[0].text
        else:  # openai
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
            response = self.client.chat.completions.create(
                model="gpt-4o",
                max_tokens=4096,
                temperature=temperature,
                messages=messages
            )
            text = response.choices[0].message.content
        
        return self._parse_json(text)
    
    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Parse JSON from response, with fallback repair."""
        try:
            # Try direct parse
            return json.loads(text)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code blocks
            if "```json" in text:
                start = text.find("```json") + 7
                end = text.find("```", start)
                if end > start:
                    try:
                        return json.loads(text[start:end].strip())
                    except json.JSONDecodeError:
                        pass
            elif "```" in text:
                start = text.find("```") + 3
                end = text.find("```", start)
                if end > start:
                    try:
                        return json.loads(text[start:end].strip())
                    except json.JSONDecodeError:
                        pass
            
            # Try repair prompt
            repair_prompt = f"""The following text should be valid JSON but is not. 
Please repair it to be valid JSON and return ONLY the corrected JSON:

{text}"""
            
            if self.provider == "anthropic":
                repair_response = self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=4096,
                    messages=[{"role": "user", "content": repair_prompt}]
                )
                repaired_text = repair_response.content[0].text
            else:
                repair_response = self.client.chat.completions.create(
                    model="gpt-4o",
                    max_tokens=4096,
                    temperature=1,
                    messages=[{"role": "user", "content": repair_prompt}]
                )
                repaired_text = repair_response.choices[0].message.content
            
            try:
                return json.loads(repaired_text)
            except json.JSONDecodeError as e:
                raise ValueError(f"Could not parse or repair JSON: {str(e)}")


def get_llm_client(provider: str = "openai") -> LLMClient:
    """Factory function to get LLM client. Defaults to OpenAI."""
    return LLMClient(provider)
