from __future__ import annotations


class ResearchAssistantService:
    MAX_DOCUMENT_CHARS = 4000

    def build_prompt(self, question: str, context_note: str = "", document_context: str = "") -> str:
        prompt = f"[research_assistant]\nQuestion: {question.strip()}"
        if context_note.strip():
            prompt += f"\nContext: {context_note.strip()}"
        if document_context.strip():
            clipped = document_context.strip()[: self.MAX_DOCUMENT_CHARS]
            if len(document_context.strip()) > self.MAX_DOCUMENT_CHARS:
                clipped += "\n...(문서 내용이 길어 일부만 사용됨)..."
            prompt += f"\n\nDocument Context:\n{clipped}"
        prompt += "\n\nInstruction: Answer based on the uploaded documents first. If the document does not contain the answer, say so clearly."
        return prompt
