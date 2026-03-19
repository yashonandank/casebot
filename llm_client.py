import json
import os
from typing import Optional, Dict, Any, List
import streamlit as st


class LLMClient:
    """OpenAI GPT-4o wrapper for JSON generation and chat."""

    def __init__(self):
        self._load_client()

    def _load_client(self):
        try:
            api_key = (
                st.secrets.get("OPENAI_API_KEY")
                if hasattr(st, "secrets")
                else os.getenv("OPENAI_API_KEY")
            )
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in secrets or environment")
            os.environ["OPENAI_API_KEY"] = api_key
            from openai import OpenAI
            self.client = OpenAI(api_key=api_key)
        except Exception as e:
            st.error(f"LLM initialization error: {str(e)}")
            raise

    def generate_json(self, prompt: str) -> Dict[str, Any]:
        """Generate a JSON response from a prompt."""
        response = self.client.chat.completions.create(
            model="gpt-4o",
            max_tokens=4096,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._parse_json(response.choices[0].message.content)

    def chat(
        self,
        system_prompt: str,
        messages: List[Dict],
        temperature: float = 0.5,
    ) -> str:
        """Multi-turn chat, returns raw text."""
        response = self.client.chat.completions.create(
            model="gpt-4o",
            max_tokens=2048,
            temperature=temperature,
            messages=[{"role": "system", "content": system_prompt}] + messages,
        )
        return response.choices[0].message.content

    def chat_json(
        self,
        system_prompt: str,
        messages: List[Dict],
        temperature: float = 0.4,
    ) -> Dict[str, Any]:
        """Multi-turn chat returning JSON."""
        text = self.chat(system_prompt, messages, temperature)
        return self._parse_json(text)

    def embed(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts using text-embedding-3-small."""
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=texts,
        )
        return [item.embedding for item in response.data]

    def _parse_json(self, text: str) -> Dict[str, Any]:
        """Parse JSON from response, stripping markdown fences."""
        text = text.strip()
        for fence in ["```json", "```"]:
            if fence in text:
                start = text.find(fence) + len(fence)
                end = text.find("```", start)
                if end > start:
                    text = text[start:end].strip()
                    break
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Attempt repair
            repair_response = self.client.chat.completions.create(
                model="gpt-4o",
                max_tokens=4096,
                temperature=0,
                messages=[{
                    "role": "user",
                    "content": (
                        "The following should be valid JSON but is malformed. "
                        "Return ONLY the corrected JSON with no explanation:\n\n" + text
                    )
                }],
            )
            try:
                return json.loads(repair_response.choices[0].message.content.strip())
            except json.JSONDecodeError as e:
                raise ValueError(f"Could not parse or repair JSON: {e}")


_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Singleton LLM client factory."""
    global _client
    if _client is None:
        _client = LLMClient()
    return _client
