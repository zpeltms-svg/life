import json
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class ProjectRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.services = json.loads((ROOT / "data/services.json").read_text(encoding="utf-8"))["services"]
        cls.centers = json.loads((ROOT / "data/welfare-centers.json").read_text(encoding="utf-8"))["centers"]
        cls.app = (ROOT / "app.js").read_text(encoding="utf-8")
        cls.route = (ROOT / "api/route.py").read_text(encoding="utf-8")
        cls.vercel = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))

    def test_01_services_exist(self):
        self.assertGreaterEqual(len(self.services), 7)

    def test_02_service_ids_unique(self):
        ids = [item["id"] for item in self.services]
        self.assertEqual(len(ids), len(set(ids)))

    def test_03_all_services_have_sources(self):
        self.assertTrue(all(item.get("source_url") and item.get("source_checked") for item in self.services))

    def test_04_online_services_have_https_links(self):
        links = [item["online_application"]["url"] for item in self.services if item.get("online_application")]
        self.assertTrue(links and all(link.startswith("https://") for link in links))

    def test_05_centers_cover_all_areas(self):
        self.assertEqual(len(self.centers), 29)
        self.assertEqual(len({item["area"] for item in self.centers}), 29)

    def test_06_centers_have_road_addresses(self):
        self.assertTrue(all(item["name"].endswith("행정복지센터") and item["address"].startswith("화성시") for item in self.centers))

    def test_07_jurisdiction_services_marked(self):
        modes = {item["id"]: item.get("office_mode") for item in self.services}
        self.assertEqual(modes["MOVE-001"], "jurisdiction")
        self.assertEqual(modes["BIRTH-002"], "jurisdiction")

    def test_08_nationwide_service_marked(self):
        birth = next(item for item in self.services if item["id"] == "BIRTH-001")
        self.assertEqual(birth.get("office_mode"), "nationwide_nearest")

    def test_09_partial_area_matching_present(self):
        self.assertIn("startsWith(normalized)", self.app)
        self.assertIn("includes(normalized)", self.app)

    def test_10_nearest_center_calculation_present(self):
        self.assertIn("findNearestWelfareCenter", self.app)
        self.assertIn("distanceBetween", self.app)

    def test_11_current_location_address_present(self):
        self.assertIn("/api/address", self.app)
        self.assertIn("current-address-btn", self.app)

    def test_12_route_uses_supported_option(self):
        self.assertIn('"option": "trafast"', self.route)
        self.assertNotIn("trafast,tracomfort", self.route)

    def test_13_current_naver_endpoints_used(self):
        self.assertIn("https://maps.apigw.ntruss.com/map-geocode/v2/geocode", self.route)
        self.assertIn("https://maps.apigw.ntruss.com/map-direction/v1/driving", self.route)

    def test_14_all_api_rewrites_exist(self):
        sources = {item["source"] for item in self.vercel["rewrites"]}
        self.assertTrue({"/api/guide", "/api/route", "/api/address", "/api/map-config"}.issubset(sources))

    def test_15_no_plaintext_secret_in_tracked_sources(self):
        suspicious = re.compile(r"(?:CLIENT_SECRET|SERVICE_KEY)\s*[=:]\s*['\"]?[A-Za-z0-9_-]{16,}")
        for path in ROOT.rglob("*"):
            if path.is_file() and ".git" not in path.parts and path.suffix in {".py", ".js", ".json", ".md", ".html", ".css"}:
                self.assertIsNone(suspicious.search(path.read_text(encoding="utf-8", errors="ignore")), str(path))

    def test_16_reverse_geocode_uses_administrative_dong(self):
        source = (ROOT / "api/address.py").read_text(encoding="utf-8")
        self.assertIn('item.get("name") == "admcode"', source)

if __name__ == "__main__":
    unittest.main(verbosity=2)
