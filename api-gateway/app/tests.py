from unittest.mock import Mock, patch

from django.test import Client, TestCase
from django.urls import reverse


class GatewayFlowTests(TestCase):
    def setUp(self):
        self.client = Client()
        session = self.client.session
        session["customer_id"] = 11
        session["email"] = "user@test.local"
        session.save()

    @patch("app.views.requests.post")
    @patch("app.views.requests.get")
    def test_place_order_success(self, mock_get, mock_post):
        cart_response = Mock(status_code=200)
        cart_response.json.return_value = [{"product_id": 1, "quantity": 1}]
        mock_get.return_value = cart_response

        order_response = Mock(status_code=201)
        order_response.json.return_value = {"id": 99, "total_amount": "12.99", "status": "pending"}

        event_response = Mock(status_code=201)
        mock_post.side_effect = [order_response, event_response]

        resp = self.client.post(
            reverse("place_order"),
            data={
                "payment_method": "cod",
                "shipping_method": "standard",
                "address": "HN",
                "phone": "0123",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Đặt hàng")

    @patch("app.views.requests.post")
    def test_chat_proxy_route(self, mock_post):
        upstream = Mock(status_code=200)
        upstream.content = b'{"answer":"ok"}'
        upstream.headers = {"Content-Type": "application/json"}
        mock_post.return_value = upstream

        resp = self.client.post(
            reverse("api_chat_advice"),
            data='{"message":"hello"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
