import os

import requests


def status():
    return {
        "configured": bool(os.environ.get("LLM_API_KEY")),
        "base_url": os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
        "model": os.environ.get("LLM_MODEL", "gpt-4o-mini"),
    }


def generate(message, contexts, products):
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    base_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    context_text = "\n".join(
        f"- [{item.get('source')}] {item.get('title')}: {item.get('content', '')[:500]}"
        for item in contexts
    )
    product_text = "\n".join(
        f"- #{item.get('id')} {item.get('title')} ({item.get('domain')}), price={item.get('price')}"
        for item in products
    )
    prompt = (
        "Bạn là trợ lý tư vấn sản phẩm. Chỉ sử dụng context được cung cấp, "
        "không tạo HTML, không bịa giá hoặc chính sách. Trả lời tiếng Việt ngắn gọn "
        "và nhắc ID sản phẩm khi đề xuất.\n\n"
        f"Context:\n{context_text}\n\nProducts:\n{product_text}\n\nQuestion: {message}"
    )
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "Use only supplied evidence."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()
