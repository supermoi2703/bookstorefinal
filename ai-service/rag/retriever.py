from graph.service import (
    get_recommended_products,
    get_user_behavior_summary,
    graph_search,
)


def get_similar_users(user_id, limit=5):
    # Kept for API compatibility. Recommendations now query peers directly.
    del user_id, limit
    return []


def get_product_stats(product_id):
    from graph.service import get_driver

    try:
        with get_driver().session() as session:
            row = session.run(
                """
                MATCH (:User)-[r]->(p:Product {catalog_id: $pid})
                RETURN count(CASE WHEN type(r) = 'VIEWED' THEN 1 END) AS views,
                       count(CASE WHEN type(r) = 'CLICKED' THEN 1 END) AS clicks,
                       count(CASE WHEN type(r) = 'ADDED_TO_CART' THEN 1 END) AS carts,
                       count(DISTINCT startNode(r)) AS unique_users
                """,
                pid=product_id,
            ).single()
        return dict(row) if row else None
    except Exception:
        return None
