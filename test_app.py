"""
Integration and Unit tests for Remote Employee Equipment Allocation Tracker
Validates:
1. DB initialization and initial seed state.
2. Employee hardware setup request submission.
3. IT operations inventory review and asset tag assignment.
4. Logistics carrier and tracking update.
5. Compliance return agreement logging and returned asset restock.
"""

import os
import unittest
import sqlite3
import app

TEST_DB = os.path.join(os.path.dirname(__file__), "test_equipment.db")

class TestEquipmentTracker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Point app to test database
        app.DB_FILE = TEST_DB
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        app.init_db()

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)

    def test_01_db_seed_and_stats(self):
        stats = app.get_stats()
        self.assertGreater(stats["total_inventory"], 0)
        self.assertGreater(stats["available_inventory"], 0)
        self.assertEqual(stats["pending_requests"], 1)

    def test_02_create_request(self):
        req_data = {
            "employee_name": "David Kim",
            "employee_email": "david.k@company.io",
            "department": "Engineering",
            "role_title": "Full Stack Engineer",
            "shipping_address": "456 Market St, San Francisco, CA 94105",
            "setup_tier": "Engineering",
            "requested_items": "MacBook Pro 16\", Dell 27\" 4K, CalDigit Dock",
            "return_agreement_signed": 1
        }
        req_id = app.create_request(req_data)
        self.assertIsInstance(req_id, int)

        # Verify request exists in list
        requests = app.list_requests("Pending Review")
        matching = [r for r in requests if r["id"] == req_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["employee_name"], "David Kim")
        self.assertEqual(matching[0]["return_agreement_signed"], 1)

    def test_03_review_and_allocate_inventory(self):
        # Find available laptop & monitor
        avail = app.list_inventory(status_filter="Available")
        self.assertTrue(len(avail) >= 2)
        tags_to_assign = [avail[0]["asset_tag"], avail[1]["asset_tag"]]

        # Find our created request
        requests = app.list_requests("Pending Review")
        target_req = [r for r in requests if r["employee_email"] == "david.k@company.io"][0]

        # Review & approve
        success, msg = app.review_request(
            target_req["id"],
            action="approve",
            assigned_tags=tags_to_assign,
            notes="Allocated from West Coast hub."
        )
        self.assertTrue(success)

        # Verify assigned inventory items are now marked 'Allocated'
        all_inv = {item["asset_tag"]: item["status"] for item in app.list_inventory()}
        for tag in tags_to_assign:
            self.assertEqual(all_inv[tag], "Allocated")

    def test_04_update_tracking_logistics(self):
        requests = app.list_requests("Approved")
        target_req = [r for r in requests if r["employee_email"] == "david.k@company.io"][0]

        success, msg = app.update_tracking(
            target_req["id"],
            carrier="FedEx",
            tracking_number="FX-773300192847",
            status="Shipped"
        )
        self.assertTrue(success)

        # Verify state transition
        shipped_list = app.list_requests("Shipped")
        matching = [r for r in shipped_list if r["id"] == target_req["id"]]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["tracking_number"], "FX-773300192847")

    def test_05_return_agreement_and_restock(self):
        # Simulate employee offboarding / return
        shipped_list = app.list_requests("Shipped")
        target_req = [r for r in shipped_list if r["employee_email"] == "david.k@company.io"][0]
        assigned_tags = [t.strip() for t in target_req["assigned_asset_tags"].split(",") if t.strip()]

        # Log return and restock
        success, msg = app.log_return(
            target_req["id"],
            agreement_signed=True,
            return_status="Returned",
            notes="Hardware inspected, zero cosmetic damage, wiped and restocked."
        )
        self.assertTrue(success)

        # Verify items returned to 'Available'
        all_inv = {item["asset_tag"]: item["status"] for item in app.list_inventory()}
        for tag in assigned_tags:
            self.assertEqual(all_inv[tag], "Available")

    def test_06_add_new_inventory(self):
        item_data = {
            "asset_tag": "AST-TEST-99",
            "category": "Laptop",
            "model_name": "Framework Laptop 16",
            "serial_number": "SN-FRM-9988",
            "asset_value": 1999.00,
            "cost_center": "ENG-DEV"
        }
        item_id = app.add_inventory_item(item_data)
        self.assertIsInstance(item_id, int)

        inv = app.list_inventory()
        matching = [i for i in inv if i["asset_tag"] == "AST-TEST-99"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["status"], "Available")

class TestLiveHttpServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        from http.server import HTTPServer
        import urllib.request

        cls.port = 18088
        app.DB_FILE = TEST_DB
        app.init_db()
        cls.server = HTTPServer(("127.0.0.1", cls.port), app.RequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        if os.path.exists(TEST_DB):
            try:
                os.remove(TEST_DB)
            except OSError:
                pass

    def test_07_http_get_index_and_stats(self):
        import urllib.request
        import json

        # Test index page
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("Allocation & Compliance Tracker", content)

        # Test stats endpoint
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/stats") as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("total_inventory", data)
            self.assertIn("pending_requests", data)

    def test_08_http_post_request(self):
        import urllib.request
        import json

        payload = {
            "employee_name": "Taylor Swift",
            "employee_email": "taylor.s@company.io",
            "department": "Marketing & Sales",
            "role_title": "Brand Lead",
            "shipping_address": "13 Cornelia St, New York, NY 10014",
            "setup_tier": "Design",
            "requested_items": "MacBook Air 15\", Studio Display",
            "return_agreement_signed": 1
        }
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/requests",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 201)
            res_data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(res_data["success"])
            self.assertIn("id", res_data)

if __name__ == "__main__":
    unittest.main()
