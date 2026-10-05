import json
import os
import unittest
from unittest.mock import patch

from olympus.media.higgsfield import HiggsfieldClient, HiggsfieldConfig, HiggsfieldError


class FakeResponse:
    status = 202

    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class HiggsfieldProviderTests(unittest.TestCase):
    def client(self):
        return HiggsfieldClient(HiggsfieldConfig(
            base_url="https://api.higgsfield.ai",
            key_id="id-test",
            key_secret="secret-test",
            timeout_seconds=10,
        ))

    @patch("olympus.media.higgsfield.urlopen")
    def test_submit_uses_official_key_scheme_and_async_request(self, urlopen):
        urlopen.return_value = FakeResponse({
            "status": "queued",
            "request_id": "d7e6c0f3-6699-4f6c-bb45-2ad7fd9158ff",
        })
        result = self.client().submit(
            "/higgsfield-ai/soul/v2/standard",
            {"prompt": "A quiet lake"},
        )
        request = urlopen.call_args.args[0]
        self.assertEqual(result["status"], "queued")
        self.assertEqual(request.get_header("Authorization"), "Key id-test:secret-test")
        self.assertEqual(request.full_url, "https://api.higgsfield.ai/higgsfield-ai/soul/v2/standard")

    def test_missing_credentials_fails_closed(self):
        client = HiggsfieldClient(HiggsfieldConfig(base_url="https://api.higgsfield.ai"))
        with self.assertRaises(HiggsfieldError):
            client.submit("/higgsfield-ai/soul/v2/standard", {"prompt": "test"})

    def test_invalid_path_and_request_id_are_rejected_before_network(self):
        client = self.client()
        with self.assertRaises(HiggsfieldError):
            client.submit("https://evil.example/steal", {"prompt": "test"})
        with self.assertRaises(HiggsfieldError):
            client.status("../../secret")


if __name__ == "__main__":
    unittest.main()
