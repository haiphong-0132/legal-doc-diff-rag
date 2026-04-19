from src.core.matching.llm_review import call_ollama


def chat_about_report(report_text: str, user_question: str) -> str:
    prompt = f"""Bạn là trợ lý pháp lý. Dưới đây là báo cáo so sánh hai văn bản pháp luật.
Hãy trả lời câu hỏi của người dùng dựa trên nội dung báo cáo.
Trả lời bằng tiếng Việt, ngắn gọn, chính xác.

--- BÁO CÁO ---
{report_text}
--- HẾT BÁO CÁO ---

Câu hỏi: {user_question}
"""
    return call_ollama(prompt)
