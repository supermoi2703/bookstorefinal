from app.crud import upsert_kb_document
from app.database import init_db, session_scope
from app.schemas import KBDocumentInput


SEED_DOCS = [
    KBDocumentInput(
        title="Chính sách giao hàng",
        source="policy:shipping",
        topic="shipping",
        content="Đơn hàng tiêu chuẩn giao trong 3-5 ngày. Giao nhanh 1-2 ngày nội thành.",
    ),
    KBDocumentInput(
        title="Chính sách đổi trả",
        source="policy:return",
        topic="return",
        content="Khách hàng có thể đổi trả trong 7 ngày nếu sản phẩm lỗi hoặc sai mô tả.",
    ),
    KBDocumentInput(
        title="Phương thức thanh toán",
        source="faq:payment",
        topic="payment",
        content="Hệ thống hỗ trợ COD, chuyển khoản ngân hàng và thẻ tín dụng.",
    ),
]


if __name__ == "__main__":
    init_db()
    with session_scope() as db:
        for document in SEED_DOCS:
            upsert_kb_document(db, document)
    print(f"Seeded {len(SEED_DOCS)} KB docs")
