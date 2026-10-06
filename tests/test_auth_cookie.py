import unittest

from auth_cookie import create_auth_cookie, verify_auth_cookie


class AuthCookieTests(unittest.TestCase):
    def setUp(self):
        self.password_hash = "pbkdf2_sha256$600000$test-salt$test-digest"
        self.accounts = {
            "admin": {
                "password": self.password_hash,
                "role": "admin",
                "label": "مدير النظام",
            }
        }
        self.now = 1_800_000_000

    def test_cookie_is_valid_for_active_account(self):
        token, expires_at = create_auth_cookie(
            "admin", self.password_hash, self.now, 1800
        )

        self.assertEqual(
            verify_auth_cookie(token, self.accounts, self.now + 10, 1800),
            ("admin", expires_at),
        )

    def test_cookie_expiry_is_enforced(self):
        token, _ = create_auth_cookie("admin", self.password_hash, self.now, 1800)

        self.assertIsNone(
            verify_auth_cookie(token, self.accounts, self.now + 1800, 1800)
        )

    def test_tampered_cookie_is_rejected(self):
        token, _ = create_auth_cookie("admin", self.password_hash, self.now, 1800)
        encoded_payload, signature = token.split(".", 1)
        tampered_token = f"{encoded_payload[:-1]}A.{signature}"

        self.assertIsNone(
            verify_auth_cookie(tampered_token, self.accounts, self.now + 10, 1800)
        )

    def test_password_change_invalidates_cookie(self):
        token, _ = create_auth_cookie("admin", self.password_hash, self.now, 1800)
        self.accounts["admin"]["password"] = "pbkdf2_sha256$600000$new-salt$new-digest"

        self.assertIsNone(
            verify_auth_cookie(token, self.accounts, self.now + 10, 1800)
        )

    def test_removed_account_invalidates_cookie(self):
        token, _ = create_auth_cookie("admin", self.password_hash, self.now, 1800)
        del self.accounts["admin"]

        self.assertIsNone(
            verify_auth_cookie(token, self.accounts, self.now + 10, 1800)
        )


if __name__ == "__main__":
    unittest.main()
