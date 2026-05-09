from src.core.matching.llm_review import call_local_llm
from src.core.matching.llm_prompts import CHAT_SYSTEM_PROMPT


def chat_about_report(report_text: str, user_question: str) -> str:
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"--- BÁO CÁO ---\n{report_text}\n--- HẾT BÁO CÁO ---\n\nCâu hỏi: {user_question}",
        },
    ]
    return call_local_llm(messages)
