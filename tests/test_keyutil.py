import unittest

import keyutil

KEY_A = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='
KEY_B = 'BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB='

CONF = """[Interface]
PrivateKey = OLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLDOLD=
Address = 10.9.0.2/30
ListenPort = 51821
Jc = 3

[Peer]
PublicKey = OLDPEEROLDPEEROLDPEEROLDPEEROLDPEEROLD=
AllowedIPs = 0.0.0.0/0
Endpoint = 198.51.100.2:51821
PersistentKeepalive = 25
"""


class KeyUtilTests(unittest.TestCase):
    def test_clean_key_accepts_valid_base64(self):
        self.assertEqual(keyutil.clean_key('  ' + KEY_A + '\n'), KEY_A)

    def test_clean_key_rejects_bad_length_and_characters(self):
        for bad in ('', KEY_A[:-1], KEY_A + 'A', '!' * 43 + '=', KEY_A[:20]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                keyutil.clean_key(bad)

    def test_rewrite_private_key_only(self):
        out = keyutil.rewrite_conf(CONF, private=KEY_A)
        self.assertIn('PrivateKey = ' + KEY_A, out)
        self.assertIn('PublicKey = OLDPEER', out)

    def test_rewrite_peer_public_key_only(self):
        out = keyutil.rewrite_conf(CONF, peer_public=KEY_B)
        self.assertIn('PublicKey = ' + KEY_B, out)
        self.assertIn('PrivateKey = OLDOLD', out)

    def test_rewrite_both_keys_preserves_everything_else(self):
        out = keyutil.rewrite_conf(CONF, private=KEY_A, peer_public=KEY_B)
        self.assertIn('Address = 10.9.0.2/30', out)
        self.assertIn('ListenPort = 51821', out)
        self.assertIn('Jc = 3', out)
        self.assertIn('AllowedIPs = 0.0.0.0/0', out)
        self.assertIn('Endpoint = 198.51.100.2:51821', out)
        self.assertEqual(out.count('PrivateKey = '), 1)
        self.assertEqual(out.count('PublicKey = '), 1)

    def test_rewrite_requires_existing_key_line(self):
        with self.assertRaises(ValueError):
            keyutil.rewrite_conf('[Interface]\nAddress = 10.9.0.2/30\n', private=KEY_A)
        with self.assertRaises(ValueError):
            keyutil.rewrite_conf('[Interface]\nPrivateKey = ' + KEY_A + '\n', peer_public=KEY_B)

    def test_obfuscation_lines_from_dict(self):
        data = dict(Jc=3, Jmin=40, Jmax=70, S1=32, S2=48,
                    H1=1, H2=2, H3=3, H4=4)
        out = keyutil.obfuscation_lines(data).splitlines()
        self.assertEqual(len(out), 9)
        self.assertEqual(out[0], 'Jc = 3')
        self.assertEqual(out[-1], 'H4 = 4')

    def test_obfuscation_lines_from_pasted_text(self):
        text = 'Jc=3 Jmin = 40,Jmax=70 S1=32 S2=48 H1=1 H2=2 H3=3 H4=4'
        out = keyutil.obfuscation_lines(text)
        self.assertIn('Jc = 3', out)
        self.assertIn('Jmin = 40', out)
        self.assertTrue(all('=' in line and len(line.split()) == 3
                            for line in out.splitlines()))

    def test_obfuscation_lines_rejects_missing_keys(self):
        with self.assertRaises(ValueError):
            keyutil.obfuscation_lines('Jc=3 H1=1')


if __name__ == '__main__':
    unittest.main()
