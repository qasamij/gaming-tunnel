import unittest

import passwords


class PasswordTests(unittest.TestCase):
    def test_hash_is_salted_and_verifiable(self):
        first = passwords.hash_password('GamingTunnel123')
        second = passwords.hash_password('GamingTunnel123')
        self.assertNotEqual(first, second)
        self.assertTrue(passwords.verify('GamingTunnel123', first))
        self.assertTrue(passwords.verify('GamingTunnel123', second))
        self.assertFalse(passwords.verify('wrong-password', first))

    def test_hash_is_not_plaintext(self):
        encoded = passwords.hash_password('GamingTunnel123')
        self.assertNotIn('GamingTunnel123', encoded)
        self.assertTrue(encoded.startswith(('argon2id$', 'scrypt$')))
        self.assertFalse(passwords.needs_upgrade(encoded))

    def test_legacy_plaintext_still_verifies_and_needs_upgrade(self):
        self.assertTrue(passwords.verify('GamingTunnel123', 'GamingTunnel123'))
        self.assertTrue(passwords.needs_upgrade('GamingTunnel123'))


if __name__ == '__main__':
    unittest.main()
