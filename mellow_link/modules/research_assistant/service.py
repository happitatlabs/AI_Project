from __future__ import annotations


class ResearchAssistantService:
    def build_prompt(self, question: str, context_note: str = "") -> str:
        prompt = f"[research_assistant]\nQuestion: {question.strip()}"
        if context_note.strip():
            prompt += f"\nContext: {context_note.strip()}"
        return prompt
