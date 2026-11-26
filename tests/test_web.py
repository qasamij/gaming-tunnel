import base64
import unittest

import web


class WebTests(unittest.TestCase):
    def test_totp_rfc_vector(self):
        secret = base64.b32decode("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")
        # RFC 6238 appendix B: 8-digit HOTP is 94287082, TOTP is last 6 digits.
        self.assertEqual(web.totp(secret, 1), "287082")

    def test_shell_contains_csrf_and_no_unformatted_braces(self):
        html = web.shell_html("test-token")
        self.assertIn('content="test-token"', html)
        self.assertIn('value="test-token"', html)
        self.assertNotIn("{token}", html)
        self.assertNotIn("{version}", html)

    def test_login_page_renders(self):
        self.assertIn("ورود امن", web.LOGIN_HTML.format(msg="", version=web.VERSION))


if __name__ == "__main__":
    unittest.main()
